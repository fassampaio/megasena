"""Orquestra a coleta: descobre ausentes, baixa, valida e grava."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import db
from .api import ClienteCaixa, ErroAPI
from .validacao import Concurso, ErroValidacao, validar

log = logging.getLogger(__name__)


@dataclass
class Resumo:
    ultimo_oficial: int = 0
    ausentes: int = 0
    baixados: int = 0
    do_cache: int = 0
    falhas: dict[int, str] = field(default_factory=dict)


class Coletor:
    def __init__(self, conn: sqlite3.Connection, cliente: ClienteCaixa,
                 dir_raw: Path, pausa: float = 0.5):
        self.conn = conn
        self.cliente = cliente
        self.dir_raw = dir_raw
        self.pausa = pausa
        self.resumo = Resumo()
        self.dir_raw.mkdir(parents=True, exist_ok=True)

    # ---------- JSON original ----------
    def caminho_raw(self, numero: int) -> Path:
        return self.dir_raw / f"{numero:06d}.json"

    def _salvar_raw(self, numero: int, conteudo: bytes) -> None:
        """Grava os bytes exatamente como vieram da API (escrita atômica)."""
        destino = self.caminho_raw(numero)
        tmp = destino.with_suffix(".json.tmp")
        with open(tmp, "wb") as f:
            f.write(conteudo)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, destino)

    def _baixar(self, numero: int) -> bytes:
        conteudo = self.cliente.concurso(numero)
        self._salvar_raw(numero, conteudo)
        if self.pausa:
            time.sleep(self.pausa)
        return conteudo

    # ---------- processamento ----------
    def _validar_e_gravar(self, numero: int, conteudo: bytes) -> Concurso:
        c = validar(json.loads(conteudo), numero_esperado=numero)
        anterior, posterior = db.datas_vizinhas(self.conn, numero)
        if anterior and c.data < anterior:
            raise ErroValidacao(f"data {c.data} anterior à do concurso anterior ({anterior})")
        if posterior and c.data > posterior:
            raise ErroValidacao(f"data {c.data} posterior à do concurso seguinte ({posterior})")
        sha = hashlib.sha256(conteudo).hexdigest()
        caminho = self.caminho_raw(numero)
        try:
            rel = caminho.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            rel = caminho.resolve().as_posix()
        db.gravar_concurso(self.conn, c, rel, sha)
        for aviso in c.avisos:
            log.info("concurso %d: aviso — %s", numero, aviso)
        return c

    def processar(self, numero: int, forcar_download: bool = False) -> Concurso:
        """Processa um concurso. Reaproveita o JSON em disco se existir."""
        caminho = self.caminho_raw(numero)
        if caminho.exists() and not forcar_download:
            try:
                c = self._validar_e_gravar(numero, caminho.read_bytes())
                self.resumo.do_cache += 1
                return c
            except (ValueError, ErroValidacao) as e:  # JSON corrompido/desatualizado
                log.warning("concurso %d: arquivo local rejeitado (%s); baixando de novo",
                            numero, e)
        c = self._validar_e_gravar(numero, self._baixar(numero))
        self.resumo.baixados += 1
        return c

    def coletar(self, ate: int | None = None, refazer: list[int] | None = None) -> Resumo:
        if refazer:
            alvos = sorted(set(refazer))
            forcar = True
        else:
            ultimo = self.cliente.ultimo_concurso()
            self.resumo.ultimo_oficial = ultimo
            limite = min(ultimo, ate) if ate else ultimo
            alvos = sorted(set(range(1, limite + 1)) - db.numeros_existentes(self.conn))
            forcar = False
            log.info("último concurso oficial: %d — ausentes no banco: %d", ultimo, len(alvos))
        self.resumo.ausentes = len(alvos)

        for i, numero in enumerate(alvos, 1):
            try:
                c = self.processar(numero, forcar_download=forcar)
                log.info("[%d/%d] concurso %d (%s): %s", i, len(alvos), numero,
                         c.data.strftime("%d/%m/%Y"),
                         " ".join(f"{d:02d}" for d in c.dezenas_crescente))
            except (ErroAPI, ErroValidacao, ValueError) as e:
                msg = f"{type(e).__name__}: {e}"
                self.resumo.falhas[numero] = msg
                db.registrar_erro(self.conn, numero, msg)
                log.error("[%d/%d] concurso %d falhou — %s", i, len(alvos), numero, msg)
        return self.resumo


def revalidar(conn: sqlite3.Connection, dir_raw: Path) -> list[str]:
    """Confere banco x JSON original, sem acessar a rede. Devolve a lista de problemas."""
    problemas: list[str] = []
    linhas = conn.execute(
        "SELECT numero, data_sorteio, json_sha256 FROM concursos ORDER BY numero").fetchall()
    data_anterior = None
    for numero, data_iso, sha in linhas:
        caminho = dir_raw / f"{numero:06d}.json"
        if not caminho.exists():
            problemas.append(f"{numero}: JSON original ausente ({caminho})")
            continue
        conteudo = caminho.read_bytes()
        if hashlib.sha256(conteudo).hexdigest() != sha:
            problemas.append(f"{numero}: SHA-256 do JSON difere do registrado no banco")
        try:
            c = validar(json.loads(conteudo), numero_esperado=numero)
        except (ValueError, ErroValidacao) as e:
            problemas.append(f"{numero}: {e}")
            continue
        if c.data.isoformat() != data_iso:
            problemas.append(f"{numero}: data no banco {data_iso} != JSON {c.data}")
        crescente, sorteio = db.dezenas_gravadas(conn, numero)
        if crescente != c.dezenas_crescente:
            problemas.append(f"{numero}: dezenas no banco {crescente} != JSON {c.dezenas_crescente}")
        if sorteio != (c.dezenas_sorteio or []):
            problemas.append(f"{numero}: ordem de sorteio no banco {sorteio} != JSON {c.dezenas_sorteio}")
        if data_anterior and c.data < data_anterior:
            problemas.append(f"{numero}: data {c.data} anterior à do concurso anterior")
        data_anterior = c.data

    if linhas:
        existentes = {r[0] for r in linhas}
        buracos = sorted(set(range(1, max(existentes) + 1)) - existentes)
        if buracos:
            problemas.append(f"concursos ausentes no banco: {_faixas(buracos)}")
    return problemas


def _faixas(nums: list[int]) -> str:
    partes, ini, ant = [], nums[0], nums[0]
    for n in nums[1:] + [None]:
        if n is not None and n == ant + 1:
            ant = n
            continue
        partes.append(str(ini) if ini == ant else f"{ini}-{ant}")
        if n is not None:
            ini = ant = n
    return ", ".join(partes)
