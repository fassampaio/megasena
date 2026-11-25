"""Atualiza tudo de um só ponto: base de sorteios, análises e painéis.

Etapas, nesta ordem:
  1. coleta    — baixa os concursos que faltam na base ativa (megasena)
  2. validação — confere a base contra os JSON originais (megasena --validar)
  3. análises  — roda cada script .py da pasta analises/, em ordem alfabética
  4. painéis   — compara os arquivos de cada painel (paineis.json) com o último
                 envio e lista os que precisam ser republicados

Uso (na raiz do projeto):
    python atualizar.py                 # tudo
    python atualizar.py --sem-coleta    # só refaz as análises com a base atual
    python atualizar.py --listar        # mostra as análises e painéis registrados
    python atualizar.py --publicado     # registra que os painéis pendentes foram enviados

Para incluir uma análise nova, basta salvar o script em analises/ (nomes que
começam com "_" são ignorados). Cada script roda com a raiz do projeto como
pasta atual e recebe nas variáveis de ambiente:
    MEGASENA_DB     caminho da base ativa
    MEGASENA_DADOS  pasta data/
    MEGASENA_SAIDA  pasta sugerida para os resultados (data/analises/)

O resumo da última execução fica em data/atualizacao.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import bases

PASTA_ANALISES = "analises"
ARQUIVO_PAINEIS = "paineis.json"
ARQUIVO_PUBLICADOS = "paineis_publicados.json"   # dentro de data/
ARQUIVO_RESUMO = "atualizacao.json"              # dentro de data/

# Códigos de saída do megasena que não impedem as análises
COLETA_TOLERADA = {0: "ok", 1: "com falhas", 2: "API inacessível"}


@dataclass
class Etapa:
    nome: str
    status: str = "pendente"   # ok | aviso | erro | pulada
    codigo: int | None = None
    segundos: float = 0.0
    detalhe: str = ""


@dataclass
class Pendencia:
    painel: str
    url: str
    dataset: str
    arquivo: str
    sha256: str


@dataclass
class Resumo:
    inicio: str
    base: str
    concursos: int | None = None
    ultimo_concurso: int | None = None
    etapas: list[Etapa] = field(default_factory=list)
    paineis_pendentes: list[Pendencia] = field(default_factory=list)


def descobrir_analises(raiz: Path) -> list[Path]:
    pasta = raiz / PASTA_ANALISES
    if not pasta.is_dir():
        return []
    return sorted(p for p in pasta.glob("*.py") if not p.name.startswith("_"))


def ler_paineis(raiz: Path) -> list[dict]:
    arq = raiz / ARQUIVO_PAINEIS
    if not arq.exists():
        return []
    return json.loads(arq.read_text(encoding="utf-8")).get("paineis", [])


def _sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _ler_publicados(dados: Path) -> dict:
    try:
        return json.loads((dados / ARQUIVO_PUBLICADOS).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def paineis_pendentes(raiz: Path) -> tuple[list[Pendencia], list[str]]:
    """Arquivos de painel que mudaram desde o último envio, e arquivos que faltam."""
    publicados = _ler_publicados(raiz / bases.DIR_DADOS)
    pendentes, faltando = [], []
    for painel in ler_paineis(raiz):
        for dataset, arquivo in painel.get("datasets", {}).items():
            caminho = raiz / arquivo
            if not caminho.exists():
                faltando.append(arquivo)
                continue
            h = _sha256(caminho)
            if publicados.get(painel["url"], {}).get(dataset) != h:
                pendentes.append(Pendencia(painel.get("nome", painel["url"]), painel["url"],
                                           dataset, arquivo, h))
    return pendentes, faltando


def marcar_publicado(raiz: Path) -> list[Pendencia]:
    pendentes, _ = paineis_pendentes(raiz)
    dados = raiz / bases.DIR_DADOS
    publicados = _ler_publicados(dados)
    for p in pendentes:
        publicados.setdefault(p.url, {})[p.dataset] = p.sha256
    dados.mkdir(parents=True, exist_ok=True)
    (dados / ARQUIVO_PUBLICADOS).write_text(
        json.dumps(publicados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pendentes


def _ambiente(raiz: Path, base: Path) -> dict[str, str]:
    env = dict(os.environ)
    src = str(raiz / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["MEGASENA_DB"] = str((raiz / base).resolve())
    env["MEGASENA_DADOS"] = str((raiz / bases.DIR_DADOS).resolve())
    env["MEGASENA_SAIDA"] = str((raiz / bases.DIR_DADOS / "analises").resolve())
    return env


def _rodar(nome: str, cmd: list[str], raiz: Path, env: dict) -> Etapa:
    print(f"\n=== {nome} ===", flush=True)
    t = time.monotonic()
    try:
        codigo = subprocess.run(cmd, cwd=raiz, env=env).returncode
    except KeyboardInterrupt:
        codigo = 130
    e = Etapa(nome, codigo=codigo, segundos=round(time.monotonic() - t, 1))
    e.status = "ok" if codigo == 0 else "erro"
    return e


def _titulo(e: Etapa) -> str:
    marca = {"ok": "OK  ", "aviso": "AVISO", "erro": "ERRO", "pulada": "--  "}[e.status]
    extra = f" ({e.detalhe})" if e.detalhe else ""
    return f"  [{marca}] {e.nome}{extra} — {e.segundos}s"


def atualizar(raiz: Path, coletar: bool = True, extra_coleta: list[str] | None = None) -> Resumo:
    base = bases.base_ativa(raiz / bases.DIR_DADOS)
    env = _ambiente(raiz, base)
    py = sys.executable
    r = Resumo(inicio=datetime.now().isoformat(timespec="seconds"), base=str(base))
    print(f"Base ativa: {base}")

    # 1. coleta
    if coletar:
        e = _rodar("coleta", [py, "-m", "megasena", *(extra_coleta or [])], raiz, env)
        if e.codigo in COLETA_TOLERADA and e.codigo != 0:
            e.status, e.detalhe = "aviso", COLETA_TOLERADA[e.codigo]
        r.etapas.append(e)
        if e.codigo == 130:
            print("\nInterrompido. Rode de novo para continuar.")
            return _finalizar(raiz, r)
    else:
        r.etapas.append(Etapa("coleta", "pulada", detalhe="--sem-coleta"))

    # 2. validação
    if (raiz / base).exists():
        e = _rodar("validação", [py, "-m", "megasena", "--validar"], raiz, env)
        if e.status == "erro":
            e.detalhe = "base com problemas (veja data/megasena.log)"
        r.etapas.append(e)
    else:
        r.etapas.append(Etapa("validação", "erro", detalhe=f"base {base} não existe"))
        return _finalizar(raiz, r)

    # 3. análises
    for script in descobrir_analises(raiz):
        e = _rodar(f"análise {script.name}", [py, str(script)], raiz, env)
        r.etapas.append(e)
        if e.codigo == 130:
            break

    return _finalizar(raiz, r)


def _finalizar(raiz: Path, r: Resumo) -> Resumo:
    r.concursos, r.ultimo_concurso = bases.contar(raiz / r.base)
    r.paineis_pendentes, faltando = paineis_pendentes(raiz)
    for arq in faltando:
        r.etapas.append(Etapa(f"painel: {arq}", "erro", detalhe="arquivo não gerado"))
    dados = raiz / bases.DIR_DADOS
    dados.mkdir(parents=True, exist_ok=True)
    (dados / ARQUIVO_RESUMO).write_text(
        json.dumps(asdict(r), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"RESUMO — base {r.base}: {r.concursos} concursos, último {r.ultimo_concurso}")
    for e in r.etapas:
        print(_titulo(e))
    if r.paineis_pendentes:
        print("\nPainéis a republicar (peça no chat: \"publique os painéis\"):")
        for p in r.paineis_pendentes:
            print(f"  - {p.painel} / {p.dataset}: {p.arquivo}")
    else:
        print("\nPainéis: todos em dia.")
    return r


def codigo_saida(r: Resumo) -> int:
    if any(e.codigo == 130 for e in r.etapas):
        return 130
    return 1 if any(e.status == "erro" for e in r.etapas) else 0


def listar(raiz: Path) -> int:
    print(f"Base ativa: {bases.base_ativa(raiz / bases.DIR_DADOS)}")
    print(f"\nAnálises ({PASTA_ANALISES}/):")
    for s in descobrir_analises(raiz) or []:
        print(f"  - {s.name}")
    if not descobrir_analises(raiz):
        print("  (nenhuma)")
    print(f"\nPainéis ({ARQUIVO_PAINEIS}):")
    pendentes, faltando = paineis_pendentes(raiz)
    chaves = {(p.url, p.dataset) for p in pendentes}
    for painel in ler_paineis(raiz):
        print(f"  - {painel.get('nome')}  {painel['url']}")
        for ds, arq in painel.get("datasets", {}).items():
            st = ("falta o arquivo" if arq in faltando
                  else "a republicar" if (painel["url"], ds) in chaves else "em dia")
            print(f"      {ds}: {arq} [{st}]")
    return 0


def main(argv: list[str] | None = None, raiz: Path | None = None) -> int:
    p = argparse.ArgumentParser(prog="atualizar", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--sem-coleta", action="store_true",
                   help="não baixa concursos; só valida e refaz as análises")
    g.add_argument("--listar", action="store_true", help="lista análises e painéis registrados")
    g.add_argument("--publicado", action="store_true",
                   help="registra que os arquivos de painel atuais já foram enviados")
    p.add_argument("--insecure", action="store_true", help="repassado à coleta")
    a = p.parse_args(argv)
    raiz = (raiz or Path.cwd()).resolve()
    os.chdir(raiz)

    if a.listar:
        return listar(raiz)
    if a.publicado:
        feitos = marcar_publicado(raiz)
        print(f"{len(feitos)} arquivo(s) de painel registrados como publicados."
              if feitos else "Nada pendente.")
        return 0
    r = atualizar(raiz, coletar=not a.sem_coleta,
                  extra_coleta=["--insecure"] if a.insecure else None)
    return codigo_saida(r)


if __name__ == "__main__":
    sys.exit(main())
