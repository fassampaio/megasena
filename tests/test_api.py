import pytest
import requests

from megasena import api
from megasena.api import ClienteCaixa, ErroAPI


class Resposta:
    def __init__(self, status, conteudo=b'{"numero": 7}'):
        self.status_code = status
        self.content = conteudo


def cliente_com_respostas(monkeypatch, respostas):
    monkeypatch.setattr(api.time, "sleep", lambda s: None)
    c = ClienteCaixa(tentativas=3)
    fila = list(respostas)

    def get(url, timeout):
        r = fila.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(c.session, "get", get)
    return c


def test_tenta_de_novo_e_devolve_bytes_originais(monkeypatch):
    c = cliente_com_respostas(monkeypatch, [
        Resposta(503), requests.ConnectionError("caiu"), Resposta(200, b'{"numero": 7}'),
    ])
    assert c.concurso(7) == b'{"numero": 7}'


def test_desiste_apos_esgotar_tentativas(monkeypatch):
    c = cliente_com_respostas(monkeypatch, [Resposta(503)] * 3)
    with pytest.raises(ErroAPI, match="3 tentativas"):
        c.concurso(7)


def test_nao_insiste_em_erro_definitivo(monkeypatch):
    c = cliente_com_respostas(monkeypatch, [Resposta(404)])
    with pytest.raises(ErroAPI, match="404"):
        c.concurso(7)


def test_resposta_nao_json_e_repetida(monkeypatch):
    c = cliente_com_respostas(monkeypatch, [Resposta(200, b"<html>"), Resposta(200)])
    assert c.concurso(7) == b'{"numero": 7}'


def test_ultimo_concurso(monkeypatch):
    c = cliente_com_respostas(monkeypatch, [Resposta(200, b'{"numero": 3083}')])
    assert c.ultimo_concurso() == 3083
