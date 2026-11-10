import json
from datetime import date, timedelta

import pytest

from megasena import db
from megasena.api import ErroAPI

PRIMEIRA_DATA = date(1996, 3, 11)


def json_concurso(numero: int, **alterar) -> dict:
    """JSON no formato da API da CAIXA para um concurso fictício."""
    base = 1 + (numero * 7) % 50
    sorteio = [base + 9, base + 1, base, base + 5, base + 3, base + 7]
    j = {
        "tipoJogo": "MEGA_SENA",
        "numero": numero,
        "dataApuracao": (PRIMEIRA_DATA + timedelta(weeks=numero - 1)).strftime("%d/%m/%Y"),
        "acumulado": numero % 2 == 0,
        "listaDezenas": [f"{d:02d}" for d in sorted(sorteio)],
        "dezenasSorteadasOrdemSorteio": [f"{d:02d}" for d in sorteio],
        "listaRateioPremio": [
            {"descricaoFaixa": "6 acertos", "faixa": 1, "numeroDeGanhadores": 0, "valorPremio": 0.0},
            {"descricaoFaixa": "5 acertos", "faixa": 2, "numeroDeGanhadores": 17, "valorPremio": 39158.92},
            {"descricaoFaixa": "4 acertos", "faixa": 3, "numeroDeGanhadores": 2016, "valorPremio": 330.21},
        ],
        "valorArrecadado": 1000.0 * numero,
        "valorEstimadoProximoConcurso": 3_000_000.0,
        "localSorteio": "Auditório",
        "nomeMunicipioUFSorteio": "Brasília, DF",
    }
    j.update(alterar)
    return j


class ClienteFalso:
    """Substitui a API: devolve JSONs fictícios e pode falhar em concursos escolhidos."""

    def __init__(self, ultimo: int, falhar_em: set[int] | None = None):
        self.ultimo = ultimo
        self.falhar_em = set(falhar_em or ())
        self.pedidos: list[int] = []

    def ultimo_concurso(self) -> int:
        return self.ultimo

    def concurso(self, numero: int) -> bytes:
        self.pedidos.append(numero)
        if numero in self.falhar_em:
            raise ErroAPI(f"falha simulada no concurso {numero}")
        return json.dumps(json_concurso(numero), ensure_ascii=False, indent=2).encode("utf-8")


@pytest.fixture
def conn(tmp_path):
    c = db.conectar(tmp_path / "teste.db")
    yield c
    c.close()
