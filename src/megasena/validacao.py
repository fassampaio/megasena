"""Validação e normalização do JSON de um concurso da Mega-Sena."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

DATA_PRIMEIRO_CONCURSO = date(1996, 3, 11)
QTD_DEZENAS = 6
DEZENA_MIN, DEZENA_MAX = 1, 60


class ErroValidacao(ValueError):
    """O JSON do concurso não passou na validação."""


@dataclass
class Faixa:
    faixa: int
    descricao: str
    ganhadores: int
    valor_premio: float


@dataclass
class Concurso:
    numero: int
    data: date
    dezenas_crescente: list[int]
    dezenas_sorteio: list[int] | None  # None quando a CAIXA não publica a ordem
    acumulado: bool | None
    valor_arrecadado: float | None
    valor_estimado_proximo: float | None
    local_sorteio: str | None
    municipio_uf: str | None
    rateio: list[Faixa] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def parse_data(valor, hoje: date | None = None) -> date:
    if not isinstance(valor, str) or not valor.strip():
        raise ErroValidacao(f"dataApuracao ausente ou inválida: {valor!r}")
    try:
        d = datetime.strptime(valor.strip(), "%d/%m/%Y").date()
    except ValueError as e:
        raise ErroValidacao(f"dataApuracao não é uma data dd/mm/aaaa válida: {valor!r}") from e
    hoje = hoje or date.today()
    if d < DATA_PRIMEIRO_CONCURSO:
        raise ErroValidacao(f"data {d} anterior ao 1º concurso ({DATA_PRIMEIRO_CONCURSO})")
    if d > hoje:
        raise ErroValidacao(f"data {d} está no futuro")
    return d


def _para_dezena(v, campo: str) -> int:
    if isinstance(v, bool):
        raise ErroValidacao(f"{campo}: valor não numérico {v!r}")
    if isinstance(v, int):
        n = v
    elif isinstance(v, str) and v.strip().isdigit():
        n = int(v.strip())
    else:
        raise ErroValidacao(f"{campo}: valor não numérico {v!r}")
    if not DEZENA_MIN <= n <= DEZENA_MAX:
        raise ErroValidacao(f"{campo}: dezena {n} fora de {DEZENA_MIN}..{DEZENA_MAX}")
    return n


def parse_dezenas(lista, campo: str) -> list[int]:
    if not isinstance(lista, list):
        raise ErroValidacao(f"{campo} ausente ou não é lista: {lista!r}")
    if len(lista) != QTD_DEZENAS:
        raise ErroValidacao(f"{campo}: esperadas {QTD_DEZENAS} dezenas, vieram {len(lista)}")
    dezenas = [_para_dezena(v, campo) for v in lista]
    if len(set(dezenas)) != QTD_DEZENAS:
        raise ErroValidacao(f"{campo}: dezenas repetidas {dezenas}")
    return dezenas


def _float_ou_none(v):
    return None if v is None else float(v)


def _parse_rateio(lista, avisos: list[str]) -> list[Faixa]:
    if not lista:
        avisos.append("listaRateioPremio ausente/vazia")
        return []
    if not isinstance(lista, list):
        raise ErroValidacao(f"listaRateioPremio não é lista: {lista!r}")
    faixas: list[Faixa] = []
    vistos: set[int] = set()
    for item in lista:
        try:
            f = Faixa(
                faixa=int(item["faixa"]),
                descricao=str(item.get("descricaoFaixa") or "").strip(),
                ganhadores=int(item.get("numeroDeGanhadores") or 0),
                valor_premio=float(item.get("valorPremio") or 0.0),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ErroValidacao(f"faixa de rateio inválida: {item!r}") from e
        if f.ganhadores < 0 or f.valor_premio < 0:
            raise ErroValidacao(f"rateio com valor negativo: {item!r}")
        if f.faixa in vistos:
            raise ErroValidacao(f"faixa de rateio repetida: {f.faixa}")
        vistos.add(f.faixa)
        faixas.append(f)
    return faixas


def validar(j: dict, numero_esperado: int | None = None, hoje: date | None = None) -> Concurso:
    """Valida o JSON bruto da API e devolve um Concurso normalizado."""
    if not isinstance(j, dict):
        raise ErroValidacao("JSON não é um objeto")

    tipo = j.get("tipoJogo")
    if tipo is not None and tipo != "MEGA_SENA":
        raise ErroValidacao(f"tipoJogo inesperado: {tipo!r}")

    numero = j.get("numero")
    if not isinstance(numero, int) or isinstance(numero, bool) or numero < 1:
        raise ErroValidacao(f"numero inválido: {numero!r}")
    if numero_esperado is not None and numero != numero_esperado:
        raise ErroValidacao(f"pedido concurso {numero_esperado}, API devolveu {numero}")

    avisos: list[str] = []
    data = parse_data(j.get("dataApuracao"), hoje)

    lista = parse_dezenas(j.get("listaDezenas"), "listaDezenas")
    crescente = sorted(lista)
    if lista != crescente:
        avisos.append(f"listaDezenas não veio em ordem crescente: {lista}")

    bruto_sorteio = j.get("dezenasSorteadasOrdemSorteio")
    if not bruto_sorteio:
        sorteio = None
        avisos.append("ordem de sorteio não publicada")
    else:
        sorteio = parse_dezenas(bruto_sorteio, "dezenasSorteadasOrdemSorteio")
        if set(sorteio) != set(crescente):
            raise ErroValidacao(
                f"ordem de sorteio {sorteio} difere de listaDezenas {crescente}"
            )

    try:
        valor_arrecadado = _float_ou_none(j.get("valorArrecadado"))
        valor_estimado = _float_ou_none(j.get("valorEstimadoProximoConcurso"))
    except (TypeError, ValueError) as e:
        raise ErroValidacao(f"valor monetário inválido: {e}") from e

    acumulado = j.get("acumulado")
    return Concurso(
        numero=numero,
        data=data,
        dezenas_crescente=crescente,
        dezenas_sorteio=sorteio,
        acumulado=None if acumulado is None else bool(acumulado),
        valor_arrecadado=valor_arrecadado,
        valor_estimado_proximo=valor_estimado,
        local_sorteio=(j.get("localSorteio") or None),
        municipio_uf=(j.get("nomeMunicipioUFSorteio") or None),
        rateio=_parse_rateio(j.get("listaRateioPremio"), avisos),
        avisos=avisos,
    )
