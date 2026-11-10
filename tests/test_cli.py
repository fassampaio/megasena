import logging

import pytest

from conftest import ClienteFalso
from megasena import cli


@pytest.fixture(autouse=True)
def limpar_logging():
    """Remove os handlers que cli.main adiciona (libera o arquivo de log no Windows)."""
    raiz = logging.getLogger()
    antes = list(raiz.handlers)
    yield
    for h in list(raiz.handlers):
        if h not in antes:
            h.close()
            raiz.removeHandler(h)


def test_coleta_e_valida_pela_linha_de_comando(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ClienteCaixa", lambda **kw: ClienteFalso(ultimo=4))
    args = ["--db", str(tmp_path / "m.db"), "--raw", str(tmp_path / "raw"), "--pausa", "0"]
    assert cli.main(args) == 0
    assert cli.main(args + ["--validar"]) == 0
    assert (tmp_path / "megasena.log").exists()


def test_codigo_de_saida_com_falhas(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ClienteCaixa", lambda **kw: ClienteFalso(ultimo=3, falhar_em={2}))
    args = ["--db", str(tmp_path / "m.db"), "--raw", str(tmp_path / "raw"), "--pausa", "0"]
    assert cli.main(args) == 1
