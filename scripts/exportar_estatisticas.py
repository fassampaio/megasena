"""Exporta estatísticas do banco da Mega-Sena em JSON para o dashboard.

Uso: python scripts/exportar_estatisticas.py [--db data/megasena.db] [--saida data/dashboard]

Gera dois arquivos no formato {rows, meta}:
  - concursos.json: uma linha por concurso (dezenas, soma, pares, prêmios, arrecadação)
  - dezenas.json:   uma linha por dezena 1..60 (frequência, atrasos)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def concursos(conn: sqlite3.Connection) -> list[dict]:
    dez: dict[int, list[int]] = {}
    for c, d in conn.execute(
            "SELECT concurso, dezena FROM dezenas ORDER BY concurso, posicao_crescente"):
        dez.setdefault(c, []).append(d)
    rat: dict[int, dict[int, tuple[int, float]]] = {}
    for c, f, g, v in conn.execute(
            "SELECT concurso, faixa, ganhadores, valor_premio FROM rateio"):
        rat.setdefault(c, {})[f] = (g, v)
    linhas = []
    for n, data, acum, arrec, estim in conn.execute(
            "SELECT numero, data_sorteio, acumulado, valor_arrecadado, valor_estimado_proximo "
            "FROM concursos ORDER BY numero"):
        d = dez.get(n, [])
        r = rat.get(n, {})
        sena, quina, quadra = r.get(1, (0, 0.0)), r.get(2, (0, 0.0)), r.get(3, (0, 0.0))
        linhas.append({
            "concurso": n,
            "data": data,
            "ano": int(data[:4]),
            **{f"d{i}": v for i, v in enumerate(d, 1)},
            "soma": sum(d),
            "pares": sum(1 for x in d if x % 2 == 0),
            "acumulado": bool(acum),
            "arrecadado": arrec or 0.0,
            "estimado_proximo": estim or 0.0,
            "ganhadores_sena": sena[0],
            "premio_sena": sena[1],
            "ganhadores_quina": quina[0],
            "premio_quina": quina[1],
            "ganhadores_quadra": quadra[0],
            "premio_quadra": quadra[1],
        })
    return linhas


def dezenas(linhas: list[dict], recentes: int = 100) -> list[dict]:
    ultimo = linhas[-1]["concurso"]
    corte = ultimo - recentes
    stats = {d: {"dezena": d, "frequencia": 0, "frequencia_recente": 0,
                 "ultimo_concurso": None, "maior_atraso": 0} for d in range(1, 61)}
    anterior = {d: 0 for d in range(1, 61)}  # concurso 0 = antes do primeiro
    for l in linhas:
        n = l["concurso"]
        for i in range(1, 7):
            d = l.get(f"d{i}")
            if d is None:
                continue
            s = stats[d]
            s["frequencia"] += 1
            if n > corte:
                s["frequencia_recente"] += 1
            s["maior_atraso"] = max(s["maior_atraso"], n - anterior[d] - 1)
            anterior[d] = n
            s["ultimo_concurso"] = n
    for d, s in stats.items():
        s["atraso_atual"] = ultimo - anterior[d]
        s["maior_atraso"] = max(s["maior_atraso"], s["atraso_atual"])
    return list(stats.values())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", type=Path, default=Path("data/megasena.db"))
    p.add_argument("--saida", type=Path, default=Path("data/dashboard"))
    a = p.parse_args()
    conn = sqlite3.connect(a.db)
    linhas = concursos(conn)
    codigo = Path(__file__).read_text(encoding="utf-8")
    meta = [{"label": Path(__file__).name, "value": codigo, "type": "code", "lang": "python"},
            {"label": "Entrada", "value": "data/megasena.db (coletado da API da CAIXA)"}]
    a.saida.mkdir(parents=True, exist_ok=True)
    for nome, rows in (("concursos", linhas), ("dezenas", dezenas(linhas))):
        destino = a.saida / f"{nome}.json"
        destino.write_text(json.dumps({"rows": rows, "meta": meta}, ensure_ascii=False,
                                      separators=(",", ":")), encoding="utf-8")
        print(f"{destino}: {len(rows)} linhas, {destino.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
