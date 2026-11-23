import logging
from pathlib import Path

import pytest

from conftest import ClienteFalso
from megasena import bases, cli, db


@pytest.fixture(autouse=True)
def em_pasta_temporaria(tmp_path, monkeypatch):
    """Roda cada teste com ./data dentro de uma pasta temporária."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "ClienteCaixa", lambda **kw: ClienteFalso(ultimo=3))
    raiz = logging.getLogger()
    antes = list(raiz.handlers)
    yield
    for h in list(raiz.handlers):
        if h not in antes:
            h.close()
            raiz.removeHandler(h)


def concursos(caminho: Path) -> int:
    return bases.contar(caminho)[0]


def test_resolver_nome_e_caminho():
    assert bases.resolver("teste") == Path("data/teste.db")
    assert bases.resolver("outra/pasta/x.db") == Path("outra/pasta/x.db")
    assert bases.resolver("x.sqlite") == Path("x.sqlite")


def test_base_ativa_padrao_e_escolhida():
    assert bases.base_ativa() == Path("data/megasena.db")
    assert cli.main(["--usar-base", "teste"]) == 0
    assert bases.base_ativa() == Path("data/teste.db")


def test_coleta_vai_para_a_base_ativa():
    cli.main(["--usar-base", "teste"])
    assert cli.main(["--pausa", "0", "--raw", "raw"]) == 0
    assert concursos(Path("data/teste.db")) == 3
    assert not Path("data/megasena.db").exists()


def test_db_vale_so_para_a_execucao():
    cli.main(["--usar-base", "teste"])
    assert cli.main(["--db", "outra", "--pausa", "0", "--raw", "raw"]) == 0
    assert concursos(Path("data/outra.db")) == 3
    assert bases.base_ativa() == Path("data/teste.db")


def test_listar_bases_marca_a_ativa(capsys):
    cli.main(["--db", "a", "--pausa", "0", "--raw", "raw"])
    cli.main(["--usar-base", "b"])
    capsys.readouterr()
    assert cli.main(["--listar-bases"]) == 0
    saida = capsys.readouterr().out
    assert "  " + str(Path("data/a.db")) + "  (3 concursos, último 3)" in saida
    assert "* " + str(Path("data/b.db")) + "  (ainda não existe)" in saida


def test_zerar_com_sim_apaga_tudo_e_mantem_raw():
    cli.main(["--pausa", "0", "--raw", "raw"])
    assert concursos(Path("data/megasena.db")) == 3
    assert cli.main(["--zerar", "--sim"]) == 0
    conn = db.conectar(Path("data/megasena.db"))
    try:
        for tabela in ("concursos", "dezenas", "rateio", "coleta_log"):
            assert conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0] == 0
    finally:
        conn.close()
    assert len(list(Path("raw").glob("*.json"))) == 3
    # a próxima coleta reaproveita os JSON locais
    assert cli.main(["--pausa", "0", "--raw", "raw"]) == 0
    assert concursos(Path("data/megasena.db")) == 3


def test_zerar_so_afeta_a_base_escolhida():
    cli.main(["--db", "a", "--pausa", "0", "--raw", "raw"])
    cli.main(["--db", "b", "--pausa", "0", "--raw", "raw"])
    assert cli.main(["--db", "a", "--zerar", "--sim"]) == 0
    assert concursos(Path("data/a.db")) == 0
    assert concursos(Path("data/b.db")) == 3


def test_zerar_pede_confirmacao(monkeypatch):
    cli.main(["--pausa", "0", "--raw", "raw"])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _: "nao")
    assert cli.main(["--zerar"]) == 1
    assert concursos(Path("data/megasena.db")) == 3
    monkeypatch.setattr("builtins.input", lambda _: "zerar")
    assert cli.main(["--zerar"]) == 0
    assert concursos(Path("data/megasena.db")) == 0


def test_zerar_sem_terminal_e_sem_sim_nao_apaga(monkeypatch):
    cli.main(["--pausa", "0", "--raw", "raw"])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False, raising=False)
    assert cli.main(["--zerar"]) == 1
    assert concursos(Path("data/megasena.db")) == 3


def test_zerar_base_inexistente_nao_cria_arquivo():
    assert cli.main(["--db", "nada", "--zerar", "--sim"]) == 0
    assert not Path("data/nada.db").exists()
