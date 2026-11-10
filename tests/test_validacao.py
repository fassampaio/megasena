from datetime import date

import pytest

from conftest import json_concurso
from megasena.validacao import ErroValidacao, validar

CONCURSO_1 = {
    "tipoJogo": "MEGA_SENA", "numero": 1, "dataApuracao": "11/03/1996", "acumulado": True,
    "listaDezenas": ["04", "05", "30", "33", "41", "52"],
    "dezenasSorteadasOrdemSorteio": ["41", "05", "04", "52", "30", "33"],
    "listaRateioPremio": [
        {"descricaoFaixa": "6 acertos", "faixa": 1, "numeroDeGanhadores": 0, "valorPremio": 0.0},
    ],
}


def test_concurso_valido():
    c = validar(CONCURSO_1, numero_esperado=1)
    assert c.numero == 1
    assert c.data == date(1996, 3, 11)
    assert c.dezenas_crescente == [4, 5, 30, 33, 41, 52]
    assert c.dezenas_sorteio == [41, 5, 4, 52, 30, 33]
    assert c.rateio[0].descricao == "6 acertos"
    assert c.avisos == []


@pytest.mark.parametrize("campo, valor", [
    ("numero", 2),
    ("numero", "1"),
    ("tipoJogo", "QUINA"),
    ("dataApuracao", "31/02/2000"),
    ("dataApuracao", "1996-03-11"),
    ("dataApuracao", "10/03/1996"),
    ("dataApuracao", "01/01/2999"),
    ("dataApuracao", None),
    ("listaDezenas", ["04", "05", "30", "33", "41"]),
    ("listaDezenas", ["04", "05", "30", "33", "41", "52", "60"]),
    ("listaDezenas", ["04", "05", "30", "33", "41", "61"]),
    ("listaDezenas", ["00", "05", "30", "33", "41", "52"]),
    ("listaDezenas", ["04", "04", "30", "33", "41", "52"]),
    ("listaDezenas", ["04", "xx", "30", "33", "41", "52"]),
    ("listaDezenas", None),
    ("dezenasSorteadasOrdemSorteio", ["41", "05", "04", "52", "30", "34"]),
    ("listaRateioPremio", [{"faixa": 1, "numeroDeGanhadores": -1, "valorPremio": 0}]),
    ("listaRateioPremio", [{"faixa": 1}, {"faixa": 1}]),
])
def test_rejeita_json_invalido(campo, valor):
    with pytest.raises(ErroValidacao):
        validar({**CONCURSO_1, campo: valor}, numero_esperado=1)


def test_sem_ordem_de_sorteio_gera_aviso():
    c = validar({**CONCURSO_1, "dezenasSorteadasOrdemSorteio": []}, numero_esperado=1)
    assert c.dezenas_sorteio is None
    assert any("ordem de sorteio" in a for a in c.avisos)


def test_lista_fora_de_ordem_e_reordenada_com_aviso():
    j = {**CONCURSO_1, "listaDezenas": ["52", "05", "30", "33", "41", "04"]}
    c = validar(j, numero_esperado=1)
    assert c.dezenas_crescente == [4, 5, 30, 33, 41, 52]
    assert c.avisos


def test_dezenas_inteiras_sao_aceitas():
    c = validar({**CONCURSO_1, "listaDezenas": [4, 5, 30, 33, 41, 52]}, numero_esperado=1)
    assert c.dezenas_crescente == [4, 5, 30, 33, 41, 52]


def test_fixture_de_teste_e_valida():
    for n in range(1, 60):
        validar(json_concurso(n), numero_esperado=n)
