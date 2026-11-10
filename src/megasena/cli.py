"""Coleta os resultados oficiais da Mega-Sena na API da CAIXA e grava em SQLite.

Exemplos:
    megasena                  # baixa todos os concursos ausentes
    megasena --ate 2500       # só até o concurso 2500
    megasena --refazer 2800   # baixa de novo e regrava o 2800
    megasena --validar        # confere banco x JSON originais (offline)

Pode ser interrompido a qualquer momento (Ctrl+C): na próxima execução
a coleta continua a partir do que ainda não está no banco.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__, db
from .api import ClienteCaixa, ErroAPI
from .coletor import Coletor, revalidar

DIR_DADOS = Path("data")


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
    p.add_argument("--db", type=Path, default=DIR_DADOS / "megasena.db",
                   help="arquivo SQLite (padrão: data/megasena.db)")
    p.add_argument("--raw", type=Path, default=DIR_DADOS / "raw" / "megasena",
                   help="pasta dos JSON originais (padrão: data/raw/megasena)")
    p.add_argument("--ate", type=int, metavar="N", help="coleta só até o concurso N")
    p.add_argument("--refazer", type=int, nargs="+", metavar="N",
                   help="baixa de novo e regrava os concursos indicados")
    p.add_argument("--validar", action="store_true",
                   help="revalida banco x JSON originais, sem acessar a rede")
    p.add_argument("--pausa", type=float, default=0.5,
                   help="segundos entre requisições (padrão: 0.5)")
    p.add_argument("--timeout", type=float, default=30, help="timeout HTTP em segundos")
    p.add_argument("--tentativas", type=int, default=5, help="tentativas por requisição")
    p.add_argument("--insecure", action="store_true",
                   help="não verifica o certificado SSL (use só se a CAIXA estiver com SSL quebrado)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = criar_parser().parse_args(argv)
    configurar_log(args.db.parent / "megasena.log", args.verbose)
    log = logging.getLogger("megasena")
    conn = db.conectar(args.db)

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
