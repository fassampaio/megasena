"""Distância entre dezenas consecutivas, na ordem do sorteio, no círculo de 60 posições.

O círculo é o mesmo do desenho em átomo (gerar_atomo.py): 60 no topo, sentido horário.
Para cada passo (1ª→2ª, 2ª→3ª, ... 5ª→6ª):
  distancia     menor número de posições entre as duas dezenas (0 a 30)
  deslocamento  mesma distância com sinal: + horário, - anti-horário (-30 a 29),
                o mesmo caminho que a espiral do desenho percorre
  sentido       "horário" ou "anti-horário"

Perfil de deslocamento: a sequência dos 5 deslocamentos (ex.: -17|-10|+23|+17|+1).
Perfis exatos nunca se repetem, então os deslocamentos são agrupados em faixas de
N posições (margem). A margem padrão é 15, que divide o círculo em 4 faixas:
  -30..-16 longo anti-horário   -15..-1 curto anti-horário
   +0..+14 curto horário        +15..+29 longo horário
Use --margem N para outra (divisores de 60: 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30);
o resumo mostra o quadro de repetições de todas as margens para comparar.

Uso: python analises/distancias_circulo.py [CONCURSO] [--margem N]
     sem argumento: grava os CSVs em data/analises/ e mostra o resumo dos perfis
     CONCURSO:      mostra a tabela desse concurso no terminal (não grava nada)

Arquivos: distancias_circulo.csv (um passo por linha), distancias_perfis.csv
(um sorteio por linha, com seu perfil) e distancias_perfis_contagem.csv
(um perfil por linha, com quantas vezes aconteceu e em quais concursos).
"""
from collections import Counter
import csv
import os
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
POSICOES = 60


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


def deslocamento(de: int, para: int) -> int:
    """Menor caminho no círculo, com sinal (+ horário). Igual à espiral do desenho."""
    return ((para - de + POSICOES // 2) % POSICOES) - POSICOES // 2


def passos(ordem: list[int]) -> list[dict]:
    linhas = []
    for i in range(len(ordem) - 1):
        d = deslocamento(ordem[i], ordem[i + 1])
        linhas.append({
            "passo": i + 1,
            "de": ordem[i],
            "para": ordem[i + 1],
            "distancia": abs(d),
            "deslocamento": d,
            "sentido": "horário" if d > 0 else "anti-horário",
        })
    return linhas


MARGENS = [1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30]
MARGEM_PADRAO = 15


def faixa(d: int, margem: int) -> str:
    """Rótulo da faixa de largura `margem` que contém o deslocamento d (-30..29)."""
    if margem == 1:
        return f"{d:+d}"
    lo = -POSICOES // 2 + ((d + POSICOES // 2) // margem) * margem
    return f"{lo:+d}..{lo + margem - 1:+d}"


def perfil_deslocamento(desl: list[int], margem: int) -> str:
    return "|".join(faixa(d, margem) for d in desl)


def todos_deslocamentos(conn) -> list[tuple[int, str, list[int]]]:
    concursos = conn.execute("SELECT numero, data_sorteio FROM concursos ORDER BY numero").fetchall()
    return [(n, d, [l["deslocamento"] for l in passos(ordem_sorteio(conn, n))])
            for n, d in concursos]


def escolher_margem(dados, fixa: int | None = None) -> tuple[int, list[tuple]]:
    """Margem fixa ou a menor de MARGENS com algum perfil repetido; devolve também o quadro."""
    quadro = []
    escolhida = fixa
    for m in MARGENS if fixa is None else sorted(set(MARGENS) | {fixa}):
        cont = Counter(perfil_deslocamento(ds, m) for _, _, ds in dados)
        repetidos = [q for q in cont.values() if q > 1]
        quadro.append((m, len(cont), len(repetidos), sum(repetidos), max(cont.values())))
        if escolhida is None and repetidos:
            escolhida = m
    return (escolhida or MARGENS[-1]), quadro


def ordem_sorteio(conn, concurso: int) -> list[int]:
    return [r[0] for r in conn.execute(
        "SELECT dezena FROM dezenas WHERE concurso=? "
        "ORDER BY COALESCE(posicao_sorteio, posicao_crescente)", (concurso,))]


def mostrar(conn, concurso: int, margem_fixa: int | None = None) -> None:
    data = conn.execute("SELECT data_sorteio FROM concursos WHERE numero=?", (concurso,)).fetchone()
    if not data:
        sys.exit(f"Concurso {concurso} não está na base.")
    ordem = ordem_sorteio(conn, concurso)
    linhas = passos(ordem)
    print(f"Concurso {concurso} ({'/'.join(reversed(data[0].split('-')))})")
    print("Ordem do sorteio: " + " → ".join(f"{n:02d}" for n in ordem) + "\n")
    print(f"{'passo':>5}  {'de':>2} → {'para':<4} {'distância':>9}  {'desloc.':>7}  sentido")
    for l in linhas:
        print(f"{l['passo']:>4}ª  {l['de']:02d} → {l['para']:02d}   {l['distancia']:>9}  "
              f"{l['deslocamento']:>+7}  {l['sentido']}")
    soma = sum(l["distancia"] for l in linhas)
    liquido = sum(l["deslocamento"] for l in linhas)
    print(f"\nPercurso total: {soma} posições (média {soma / len(linhas):.1f} por passo)")
    print(f"Giro líquido:   {liquido:+d} posições "
          f"({abs(liquido) * 6}° no sentido {'horário' if liquido > 0 else 'anti-horário'})")

    dados = todos_deslocamentos(conn)
    margem, _ = escolher_margem(dados, margem_fixa)
    meu = perfil_deslocamento([l["deslocamento"] for l in linhas], margem)
    iguais = [n for n, _, ds in dados if perfil_deslocamento(ds, margem) == meu]
    print(f"\nPerfil de deslocamento (margem {margem}): {meu}")
    print(f"aconteceu {len(iguais)}× na base: concursos {' '.join(map(str, iguais))}")


def gravar_perfis(conn, margem_fixa: int | None = None) -> None:
    dados = todos_deslocamentos(conn)
    margem, quadro = escolher_margem(dados, margem_fixa)
    perfis = [(n, d, ds, perfil_deslocamento(ds, margem)) for n, d, ds in dados]
    vezes = Counter(p for *_, p in perfis)
    concursos_do: dict[str, list[int]] = {}
    for n, _, _, p in perfis:
        concursos_do.setdefault(p, []).append(n)

    with (SAIDA / "distancias_perfis.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["concurso", "data", "deslocamentos", "margem", "perfil", "vezes_perfil"])
        for n, d, ds, p in perfis:
            w.writerow([n, d, "|".join(f"{x:+d}" for x in ds), margem, p, vezes[p]])
    with (SAIDA / "distancias_perfis_contagem.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["perfil", "margem", "vezes", "pct_sorteios", "concursos"])
        for p, q in sorted(vezes.items(), key=lambda x: (-x[1], x[0])):
            w.writerow([p, margem, q, f"{100 * q / len(perfis):.3f}",
                        " ".join(map(str, concursos_do[p]))])

    print("\nPERFIS DE DESLOCAMENTO POR MARGEM")
    print(" margem  perfis diferentes  perfis repetidos  sorteios neles  máx. repetição")
    for m, dif, rep, sort_rep, mx in quadro:
        marca = "  ← usada" if m == margem else ""
        print(f" {m:>6}  {dif:>17}  {rep:>16}  {sort_rep:>14}  {mx:>14}{marca}")
    print(f"\nMargem {margem}: {len(vezes)} perfis em {len(perfis)} sorteios")
    distrib = Counter(vezes.values())
    for q in sorted(distrib):
        print(f"  {distrib[q]:>5} perfil(is) aconteceram {q}×")
    print("  mais repetidos:")
    for p, q in sorted(vezes.items(), key=lambda x: (-x[1], x[0]))[:10]:
        if q < 2:
            break
        print(f"    {p}  {q}×  concursos {' '.join(map(str, concursos_do[p]))}")


def gravar_todos(conn) -> Path:
    SAIDA.mkdir(parents=True, exist_ok=True)
    arq = SAIDA / "distancias_circulo.csv"
    concursos = conn.execute("SELECT numero, data_sorteio FROM concursos ORDER BY numero").fetchall()
    campos = ["concurso", "data", "passo", "de", "para", "distancia", "deslocamento", "sentido"]
    with arq.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for numero, data in concursos:
            for l in passos(ordem_sorteio(conn, numero)):
                w.writerow({"concurso": numero, "data": data, **l})
    print(f"{len(concursos)} concurso(s) gravado(s) em {arq}")
    return arq


def main():
    conn = sqlite3.connect(DB)
    args = sys.argv[1:]
    margem = MARGEM_PADRAO
    if "--margem" in args:
        i = args.index("--margem")
        margem = int(args[i + 1])
        if margem < 1 or POSICOES % margem:
            sys.exit(f"--margem precisa dividir 60 ({', '.join(map(str, MARGENS))}).")
        del args[i:i + 2]
    if args:
        mostrar(conn, int(args[0]), margem)
    else:
        gravar_todos(conn)
        gravar_perfis(conn, margem)


if __name__ == "__main__":
    main()
