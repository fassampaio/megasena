"""Escolha da base de dados ativa (arquivo SQLite) e listagem das bases."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DIR_DADOS = Path("data")
NOME_PADRAO = "megasena"
ARQUIVO_CONFIG = "config.json"


def resolver(nome_ou_caminho: str | Path, dir_dados: Path = DIR_DADOS) -> Path:
    """Um nome simples ("teste") vira data/teste.db; um caminho é usado como está."""
    texto = str(nome_ou_caminho)
    p = Path(texto)
    if p.suffix or "/" in texto or "\\" in texto:
        return p
    return dir_dados / f"{texto}.db"


def _config(dir_dados: Path) -> Path:
    return dir_dados / ARQUIVO_CONFIG


def base_ativa(dir_dados: Path = DIR_DADOS) -> Path:
    """Base escolhida com --usar-base, ou data/megasena.db se nenhuma foi escolhida."""
    try:
        dados = json.loads(_config(dir_dados).read_text(encoding="utf-8"))
        return Path(dados["base"])
    except (FileNotFoundError, KeyError, ValueError, TypeError):
        return dir_dados / f"{NOME_PADRAO}.db"


def definir_base_ativa(caminho: Path, dir_dados: Path = DIR_DADOS) -> None:
    arq = _config(dir_dados)
    arq.parent.mkdir(parents=True, exist_ok=True)
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
        if not isinstance(dados, dict):
            dados = {}
    except (FileNotFoundError, ValueError):
        dados = {}
    dados["base"] = str(caminho)
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass
class InfoBase:
    caminho: Path
    concursos: int | None  # None se o arquivo não existe ou não é uma base do megasena
    ultimo: int | None
    ativa: bool


def contar(caminho: Path) -> tuple[int | None, int | None]:
    """(nº de concursos, último concurso) sem criar o arquivo nem as tabelas."""
    if not caminho.exists():
        return None, None
    try:
        conn = sqlite3.connect(f"file:{caminho.as_posix()}?mode=ro", uri=True)
        try:
            return conn.execute("SELECT COUNT(*), MAX(numero) FROM concursos").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None, None


def listar(dir_dados: Path = DIR_DADOS) -> list[InfoBase]:
    """Bases .db em dir_dados, mais a ativa se estiver em outro lugar."""
    ativa = base_ativa(dir_dados)
    caminhos = sorted(dir_dados.glob("*.db")) if dir_dados.exists() else []
    if not any(_mesmo(c, ativa) for c in caminhos):
        caminhos.append(ativa)
    saida = []
    for c in caminhos:
        n, ultimo = contar(c)
        saida.append(InfoBase(c, n, ultimo, _mesmo(c, ativa)))
    return saida


def _mesmo(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve()
