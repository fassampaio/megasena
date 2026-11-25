"""Grupos de frequência: as 60 dezenas em 10 grupos de 6, do mais ao menos sorteado.

Grupo 1  = as 6 dezenas mais sorteadas em toda a história da base
Grupo 10 = as 6 menos sorteadas (empates: a dezena menor fica no grupo de cima)

Depois cada sorteio ganha um perfil: quantas das suas 6 dezenas caíram em cada grupo.
  perfil        contagem por grupo, g1..g10 (ex.: 1010200110)
  formato       as contagens não nulas em ordem decrescente (ex.: 2-1-1-1-1)
  grupos        quantos grupos diferentes o sorteio tocou (1 a 6)
  media_grupo   média dos grupos das 6 dezenas (1 = só quentes, 10 = só frias; 5,5 = neutro)
  tendencia     quente (média < 4,5), equilibrado (4,5 a 6,5) ou frio (> 6,5)
  vezes_perfil  quantos sorteios da base tiveram exatamente o mesmo perfil

Arquivos em data/analises/: grupos_frequencia.csv (dezenas por grupo),
grupos_perfis.csv (um sorteio por linha) e grupos_perfis_contagem.csv
(um perfil por linha, com quantas vezes aconteceu e em quais concursos).

Atenção: os grupos usam a frequência de toda a base, inclusive do próprio sorteio
comparado. É um retrato do histórico, não uma previsão.

Uso: python analises/grupos_frequencia.py [CONCURSO]
     sem argumento: grava os CSVs em data/analises/ e mostra o resumo
     CONCURSO:      mostra só o perfil desse concurso (não grava nada)
"""
import csv
import os
import sqlite3
import sys
from collections import Counter
from math import comb
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GRUPOS = 10
POR_GRUPO = 6


def _base() -> Path:
    if os.environ.get("MEGASENA_DB"):
        return Path(os.environ["MEGASENA_DB"])
    try:
        sys.path.insert(0, str(RAIZ / "src"))
        from megasena.bases import base_ativa
        return RAIZ / base_ativa(RAIZ / "data")
    except ImportError:
        return RAIZ / "data" / "megasena.db"


DB = _base()
SAIDA = Path(os.environ.get("MEGASENA_SAIDA", RAIZ / "data" / "analises"))


# ---------------------------------------------------------------- dados

def frequencias(conn) -> dict[int, int]:
    freq = {n: 0 for n in range(1, 61)}
    for n, q in conn.execute("SELECT dezena, COUNT(*) FROM dezenas GROUP BY dezena"):
        freq[n] = q
    return freq


def montar_grupos(freq: dict[int, int]) -> dict[int, int]:
    """dezena -> grupo (1..10)."""
    ordem = sorted(freq, key=lambda n: (-freq[n], n))
    return {n: i // POR_GRUPO + 1 for i, n in enumerate(ordem)}


def sorteios(conn) -> list[tuple[int, str, list[int]]]:
    datas = dict(conn.execute("SELECT numero, data_sorteio FROM concursos"))
    dez: dict[int, list] = {}
    for c, d, ps, pc in conn.execute(
            "SELECT concurso, dezena, posicao_sorteio, posicao_crescente FROM dezenas"):
        dez.setdefault(c, []).append((ps if ps is not None else pc, d))
    return [(c, datas[c], [d for _, d in sorted(v)]) for c, v in sorted(dez.items())]


def perfil(ordem: list[int], grupo: dict[int, int]) -> dict:
    cont = [0] * GRUPOS
    for n in ordem:
        cont[grupo[n] - 1] += 1
    media = sum(grupo[n] for n in ordem) / len(ordem)
    return {
        "contagem": cont,
        "perfil": "".join(str(c) for c in cont),
        "formato": "-".join(str(c) for c in sorted((c for c in cont if c), reverse=True)),
        "grupos": sum(1 for c in cont if c),
        "media_grupo": media,
        "tendencia": "quente" if media < 4.5 else "frio" if media > 6.5 else "equilibrado",
    }


# ------------------------------------------------- esperado num sorteio ao acaso

def esperado_grupos_distintos() -> dict[int, float]:
    """P(sorteio aleatório tocar exatamente k grupos), por inclusão-exclusão."""
    total = comb(60, 6)
    res = {}
    for k in range(1, 7):
        exatos = sum((-1) ** (k - j) * comb(k, j) * comb(POR_GRUPO * j, 6) for j in range(k + 1))
        res[k] = comb(GRUPOS, k) * exatos / total
    return res


def esperado_ao_menos_um() -> float:
    """P(sorteio aleatório ter ao menos 1 dezena de um grupo específico)."""
    return 1 - comb(60 - POR_GRUPO, 6) / comb(60, 6)


# ---------------------------------------------------------------- saída

def fmt_data(iso: str) -> str:
    return "/".join(reversed(iso.split("-")))


def mostrar_concurso(conn, concurso: int) -> None:
    freq = frequencias(conn)
    grupo = montar_grupos(freq)
    s_lista = sorteios(conn)
    s = {c: (d, o) for c, d, o in s_lista}
    if concurso not in s:
        sys.exit(f"Concurso {concurso} não está na base.")
    data, ordem = s[concurso]
    p = perfil(ordem, grupo)
    print(f"Concurso {concurso} ({fmt_data(data)})\n")
    print("ordem  dezena  grupo  vezes sorteada")
    for i, n in enumerate(ordem, 1):
        print(f"{i:>4}ª    {n:02d}     {grupo[n]:>2}       {freq[n]}")
    print("\ngrupo   " + " ".join(f"{g:>2}" for g in range(1, 11)))
    print("dezenas " + " ".join(f"{c:>2}" for c in p["contagem"]))
    print(f"\nperfil {p['perfil']} · formato {p['formato']} · {p['grupos']} grupos · "
          f"média {p['media_grupo']:.2f} · {p['tendencia']}")
    iguais = [c for c, _, o in s_lista if perfil(o, grupo)["perfil"] == p["perfil"]]
    print(f"este perfil aconteceu {len(iguais)}× na base: concursos {' '.join(map(str, iguais))}")


def resumo(conn) -> None:
    freq = frequencias(conn)
    grupo = montar_grupos(freq)
    todos = sorteios(conn)
    n_sort = len(todos)
    perfis = [(c, d, o, perfil(o, grupo)) for c, d, o in todos]
    membros = {g: sorted((n for n in grupo if grupo[n] == g), key=lambda n: (-freq[n], n))
               for g in range(1, GRUPOS + 1)}
    SAIDA.mkdir(parents=True, exist_ok=True)

    # 1. grupos
    with (SAIDA / "grupos_frequencia.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["grupo", "dezena", "vezes", "pct_sorteios"])
        for g, ns in membros.items():
            for n in ns:
                w.writerow([g, n, freq[n], f"{100 * freq[n] / n_sort:.2f}"])

    vezes_perfil = Counter(p["perfil"] for *_, p in perfis)

    # 2. perfis por sorteio
    with (SAIDA / "grupos_perfis.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["concurso", "data", *[f"g{g}" for g in range(1, 11)], "perfil",
                    "vezes_perfil", "formato", "grupos", "media_grupo", "tendencia",
                    "grupos_na_ordem"])
        for c, d, o, p in perfis:
            w.writerow([c, d, *p["contagem"], p["perfil"], vezes_perfil[p["perfil"]],
                        p["formato"], p["grupos"], f"{p['media_grupo']:.2f}", p["tendencia"],
                        "-".join(str(grupo[n]) for n in o)])

    # 3. quantas vezes cada perfil aconteceu
    concursos_do_perfil: dict[str, list[int]] = {}
    for c, _, _, p in perfis:
        concursos_do_perfil.setdefault(p["perfil"], []).append(c)
    exemplo = {p["perfil"]: p for *_, p in perfis}
    with (SAIDA / "grupos_perfis_contagem.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["perfil", "vezes", "pct_sorteios", "formato", "grupos", "media_grupo",
                    "tendencia", "concursos"])
        for pr, q in sorted(vezes_perfil.items(), key=lambda x: (-x[1], x[0])):
            e = exemplo[pr]
            w.writerow([pr, q, f"{100 * q / n_sort:.3f}", e["formato"], e["grupos"],
                        f"{e['media_grupo']:.2f}", e["tendencia"],
                        " ".join(str(c) for c in concursos_do_perfil[pr])])

    # ---- terminal
    esperado_media = 6 / GRUPOS
    p1 = esperado_ao_menos_um()
    print(f"Base: {n_sort} sorteios · {sum(freq.values())} dezenas sorteadas\n")
    print("GRUPOS (por frequência em toda a base)")
    print("grupo  dezenas                  vezes (faixa)  por sorteio  esperado  com ≥1  esperado")
    for g, ns in membros.items():
        aparicoes = sum(p["contagem"][g - 1] for *_, p in perfis)
        com1 = sum(1 for *_, p in perfis if p["contagem"][g - 1])
        faixa = f"{freq[ns[-1]]}–{freq[ns[0]]}"
        print(f"{g:>4}   {' '.join(f'{n:02d}' for n in ns)}   {faixa:>13}  "
              f"{aparicoes / n_sort:>11.3f}  {esperado_media:>8.3f}  "
              f"{100 * com1 / n_sort:>5.1f}%  {100 * p1:>7.1f}%")

    print("\nGRUPOS DIFERENTES TOCADOS POR SORTEIO (observado × esperado ao acaso)")
    obs = Counter(p["grupos"] for *_, p in perfis)
    for k, pk in esperado_grupos_distintos().items():
        print(f"  {k} grupos: {obs.get(k, 0):>5} ({100 * obs.get(k, 0) / n_sort:5.1f}%)   "
              f"esperado {100 * pk:5.1f}%")

    print("\nFORMATOS MAIS COMUNS (como as 6 dezenas se espalham pelos grupos)")
    for fmt, q in Counter(p["formato"] for *_, p in perfis).most_common(8):
        print(f"  {fmt:<12} {q:>5} ({100 * q / n_sort:5.1f}%)")

    print("\nTENDÊNCIA (média do grupo das 6 dezenas)")
    tend = Counter(p["tendencia"] for *_, p in perfis)
    for t in ("quente", "equilibrado", "frio"):
        print(f"  {t:<12} {tend.get(t, 0):>5} ({100 * tend.get(t, 0) / n_sort:5.1f}%)")
    medias = sorted(perfis, key=lambda x: x[3]["media_grupo"])
    (cq, dq, _, pq), (cf, df, _, pf) = medias[0], medias[-1]
    print(f"  mais quente: concurso {cq} ({fmt_data(dq)}) média {pq['media_grupo']:.2f} perfil {pq['perfil']}")
    print(f"  mais frio:   concurso {cf} ({fmt_data(df)}) média {pf['media_grupo']:.2f} perfil {pf['perfil']}")

    print("\nQUANTAS VEZES CADA PERFIL ACONTECEU (g1..g10)")
    print(f"  {len(vezes_perfil)} perfis diferentes em {n_sort} sorteios")
    distrib = Counter(vezes_perfil.values())
    for q in sorted(distrib):
        print(f"  {distrib[q]:>5} perfil(is) aconteceram {q}×")
    print("  mais repetidos:")
    for pr, q in sorted(vezes_perfil.items(), key=lambda x: (-x[1], x[0]))[:10]:
        print(f"    {pr}  {q}×  concursos {' '.join(str(c) for c in concursos_do_perfil[pr])}")

    print("\nGRUPO MÉDIO POR POSIÇÃO NO SORTEIO (1ª a 6ª bola)")
    for i in range(6):
        m = sum(grupo[o[i]] for _, _, o, _ in perfis if len(o) > i) / n_sort
        print(f"  {i + 1}ª bola: {m:.2f}")

    print(f"\nArquivos: {SAIDA / 'grupos_frequencia.csv'}\n          {SAIDA / 'grupos_perfis.csv'}"
          f"\n          {SAIDA / 'grupos_perfis_contagem.csv'}")


def main():
    conn = sqlite3.connect(DB)
    if len(sys.argv) > 1:
        mostrar_concurso(conn, int(sys.argv[1]))
    else:
        resumo(conn)


if __name__ == "__main__":
    main()
