"""Coleta os resultados oficiais da Mega-Sena na API da CAIXA e grava em SQLite.

Exemplos:
    megasena                  # baixa todos os concursos ausentes
    megasena --ate 2500       # só até o concurso 2500
    megasena --refazer 2800   # baixa de novo e regrava o 2800
    megasena --validar        # confere banco x JSON originais (offline)

Bases de dados:
    megasena --listar-bases   # mostra as bases e qual está ativa
    megasena --usar-base teste  # passa a usar data/teste.db em todos os comandos
    megasena --zerar          # apaga todos os concursos da base ativa (pede confirmação)

Pode ser interrompido a qualquer momento (Ctrl+C): na próxima execução
a coleta continua a partir do que ainda não está no banco.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__, bases, db
from .api import ClienteCaixa, ErroAPI
from .coletor import Coletor, revalidar

DIR_DADOS = bases.DIR_DADOS


def configurar_log(arquivo: Path, verboso: bool) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    em_arquivo = logging.FileHandler(arquivo, encoding="utf-8")
    em_arquivo.setFormatter(fmt)
    raiz = logging.getLogger()
    raiz.setLevel(logging.DEBUG if verboso else logging.INFO)
    raiz.addHandler(console)
    raiz.addHandler(em_arquivo)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def criar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="megasena", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", metavar="BASE",
                   help="base a usar só nesta execução: nome (vira data/NOME.db) ou caminho "
                        "(padrão: a base ativa, ou data/megasena.db)")
    p.add_argument("--raw", type=Path, default=DIR_DADOS / "raw" / "megasena",
                   help="pasta dos JSON originais (padrão: data/raw/megasena)")
    p.add_argument("--ate", type=int, metavar="N", help="coleta só até o concurso N")
    p.add_argument("--refazer", type=int, nargs="+", metavar="N",
                   help="baixa de novo e regrava os concursos indicados")
    cmd = p.add_mutually_exclusive_group()
    cmd.add_argument("--validar", action="store_true",
                     help="revalida banco x JSON originais, sem acessar a rede")
    cmd.add_argument("--listar-bases", action="store_true",
                     help="lista as bases em data/ e indica a ativa")
    cmd.add_argument("--usar-base", metavar="BASE",
                     help="define a base ativa: nome (vira data/NOME.db) ou caminho")
    cmd.add_argument("--zerar", action="store_true",
                     help="apaga todos os concursos da base (a ativa, ou a de --db); "
                          "os JSON originais são mantidos")
    p.add_argument("--sim", action="store_true", help="confirma o --zerar sem perguntar")
    p.add_argument("--pausa", type=float, default=0.5,
                   help="segundos entre requisições (padrão: 0.5)")
    p.add_argument("--timeout", type=float, default=30, help="timeout HTTP em segundos")
    p.add_argument("--tentativas", type=int, default=5, help="tentativas por requisição")
    p.add_argument("--insecure", action="store_true",
                   help="não verifica o certificado SSL (use só se a CAIXA estiver com SSL quebrado)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _descrever(caminho: Path) -> str:
    n, ultimo = bases.contar(caminho)
    if n is None:
        return "ainda não existe" if not caminho.exists() else "não é uma base do megasena"
    return f"{n} concursos" + (f", último {ultimo}" if ultimo else "")


def listar_bases() -> int:
    for b in bases.listar(DIR_DADOS):
        marca = "*" if b.ativa else " "
        print(f"{marca} {b.caminho}  ({_descrever(b.caminho)})")
    print("\n* = base ativa. Troque com: megasena --usar-base NOME")
    return 0


def usar_base(nome: str) -> int:
    caminho = bases.resolver(nome, DIR_DADOS)
    bases.definir_base_ativa(caminho, DIR_DADOS)
    print(f"Base ativa: {caminho} ({_descrever(caminho)})")
    if not caminho.exists():
        print("Ela será criada na próxima coleta (rode: megasena).")
    return 0


def confirmar_zerar(caminho: Path, total: int) -> bool:
    if not sys.stdin.isatty():
        print("Sem terminal para confirmar. Use --sim para zerar sem perguntar.", file=sys.stderr)
        return False
    resposta = input(f"Apagar os {total} concursos de {caminho}? Isso não pode ser desfeito. "
                     "Digite 'zerar' para confirmar: ")
    return resposta.strip().lower() == "zerar"


def zerar(caminho: Path, sim: bool) -> int:
    n, _ = bases.contar(caminho)
    if n is None:
        print(f"Nada a zerar: {caminho} ({_descrever(caminho)}).")
        return 0 if not caminho.exists() else 1
    if not sim and not confirmar_zerar(caminho, n):
        print("Cancelado. Nada foi apagado.")
        return 1
    conn = db.conectar(caminho)
    try:
        apagados = db.zerar(conn)
    finally:
        conn.close()
    logging.getLogger("megasena").info("base %s zerada: %d concursos apagados", caminho, apagados)
    print(f"Base {caminho} zerada: {apagados} concursos apagados. "
          "Os JSON originais foram mantidos; a próxima coleta os reaproveita.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = criar_parser().parse_args(argv)

    if args.listar_bases:
        return listar_bases()
    if args.usar_base:
        return usar_base(args.usar_base)

    caminho = bases.resolver(args.db, DIR_DADOS) if args.db else bases.base_ativa(DIR_DADOS)
    configurar_log(caminho.parent / "megasena.log", args.verbose)
    log = logging.getLogger("megasena")

    if args.zerar:
        return zerar(caminho, args.sim)

    log.info("base: %s", caminho)
    conn = db.conectar(caminho)
    try:
        if args.validar:
            problemas = revalidar(conn, args.raw)
            total = conn.execute("SELECT COUNT(*) FROM concursos").fetchone()[0]
            for prob in problemas:
                log.error(prob)
            log.info("revalidação: %d concursos no banco, %d problema(s)", total, len(problemas))
            return 1 if problemas else 0

        cliente = ClienteCaixa(timeout=args.timeout, tentativas=args.tentativas,
                               verificar_ssl=not args.insecure)
        coletor = Coletor(conn, cliente, args.raw, pausa=args.pausa)
        interrompido = False
        try:
            coletor.coletar(ate=args.ate, refazer=args.refazer)
        except KeyboardInterrupt:
            interrompido = True
            log.warning("interrompido pelo usuário — rode novamente para continuar")
        except ErroAPI as e:
            log.error("não foi possível consultar a API: %s", e)
            return 2

        r = coletor.resumo
        log.info("resumo: %d a processar | %d baixados | %d do JSON local | %d falhas%s",
                 r.ausentes, r.baixados, r.do_cache, len(r.falhas),
                 " | INTERROMPIDO" if interrompido else "")
        if r.falhas:
            log.info("concursos com falha (serão tentados de novo na próxima execução): %s",
                     ", ".join(map(str, sorted(r.falhas))))
        return 130 if interrompido else (1 if r.falhas else 0)
    finally:
        conn.close()
