"""Gera um SVG: sorteio como "átomo" num mostrador de 60 minutos.

Uso: python analises/gerar_atomo.py [CONCURSO]
     sem argumento: gera todos os concursos que ainda não têm desenho
     CONCURSO:      (re)gera só esse concurso
Lê a base ativa (MEGASENA_DB, definida pelo atualizar.py) e grava em data/analises/.
"""
import math
import os
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


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

W = H = 800
CX = CY = 400
R_MOSTRADOR = 340          # aro externo (60 posições)
R_ORBITAS = [95, 130, 165, 200, 235, 270]   # camada 1 (1ª bola) .. camada 6
CORES = ["#f94144", "#f3722c", "#f9c74f", "#43aa8b", "#277da1", "#7b2cbf"]


def ponto(n, r):
    """Posição do número n (1..60) no raio r; 60 fica no topo, sentido horário."""
    ang = math.radians(n * 6)
    return CX + r * math.sin(ang), CY - r * math.cos(ang)


def espiral(n1, r1, n2, r2, passos=48):
    """Caminho SVG de (n1, r1) a (n2, r2) interpolando ângulo e raio."""
    delta = ((n2 - n1 + 30) % 60) - 30        # menor caminho, em "minutos" (-30..29)
    pts = []
    for k in range(passos + 1):
        t = k / passos
        s = t * t * (3 - 2 * t)                # suaviza a troca de raio
        pts.append(ponto(n1 + delta * t, r1 + (r2 - r1) * s))
    return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)


def svg(concurso, data, ordem):
    p = []
    a = p.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      'font-family="Segoe UI, Arial, sans-serif">')
    a('<defs><radialGradient id="nucleo"><stop offset="0" stop-color="#ffffff"/>'
      '<stop offset="1" stop-color="#cfd8e3"/></radialGradient>'
      '<filter id="brilho"><feGaussianBlur stdDeviation="3" result="b"/>'
      '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>')
    a(f'<rect width="{W}" height="{H}" fill="#0f1724"/>')

    # Mostrador: aro + 60 marcas, rótulos a cada posição (maiores nos múltiplos de 5)
    a(f'<circle cx="{CX}" cy="{CY}" r="{R_MOSTRADOR}" fill="none" stroke="#3a4a63" stroke-width="2"/>')
    sorteados = set(ordem)
    for n in range(1, 61):
        cinco = n % 5 == 0
        x1, y1 = ponto(n, R_MOSTRADOR)
        x2, y2 = ponto(n, R_MOSTRADOR - (16 if cinco else 8))
        cor = "#8da2c0" if cinco else "#4a5b75"
        a(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{cor}" '
          f'stroke-width="{2.5 if cinco else 1.2}"/>')
        lx, ly = ponto(n, R_MOSTRADOR + 22)
        destaque = n in sorteados
        fill = "#ffffff" if destaque else ("#8da2c0" if cinco else "#4f617d")
        peso = "700" if destaque or cinco else "400"
        tam = 15 if destaque or cinco else 10
        a(f'<text x="{lx:.1f}" y="{ly:.1f}" fill="{fill}" font-size="{tam}" font-weight="{peso}" '
          f'text-anchor="middle" dominant-baseline="central">{n:02d}</text>')

    # Órbitas (camadas)
    for i, r in enumerate(R_ORBITAS):
        a(f'<circle cx="{CX}" cy="{CY}" r="{r}" fill="none" stroke="{CORES[i]}" '
          'stroke-opacity="0.22" stroke-width="1.2" stroke-dasharray="3 5"/>')

    pts = [ponto(n, R_ORBITAS[i]) for i, n in enumerate(ordem)]

    # Raios-guia: do elétron até a marca correspondente no mostrador
    for i, n in enumerate(ordem):
        x1, y1 = pts[i]
        x2, y2 = ponto(n, R_MOSTRADOR - 18)
        a(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{CORES[i]}" '
          'stroke-opacity="0.35" stroke-width="1" stroke-dasharray="2 3"/>')

    # Ligações na ordem do sorteio: espiral que gira pelo menor caminho angular
    # enquanto troca de órbita (como um elétron saltando de camada)
    for i in range(len(ordem) - 1):
        a(f'<path d="{espiral(ordem[i], R_ORBITAS[i], ordem[i + 1], R_ORBITAS[i + 1])}" '
          f'fill="none" stroke="{CORES[i]}" stroke-width="3" stroke-linecap="round" '
          'stroke-opacity="0.9"/>')

    # Núcleo
    a(f'<circle cx="{CX}" cy="{CY}" r="52" fill="url(#nucleo)"/>')
    a(f'<text x="{CX}" y="{CY - 8}" text-anchor="middle" font-size="22" font-weight="700" '
      f'fill="#0f1724">{concurso}</text>')
    a(f'<text x="{CX}" y="{CY + 16}" text-anchor="middle" font-size="12" fill="#3a4a63">{data}</text>')

    # Elétrons (bolas sorteadas)
    for i, n in enumerate(ordem):
        x, y = pts[i]
        a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="17" fill="{CORES[i]}" filter="url(#brilho)"/>')
        a(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" dominant-baseline="central" '
          f'font-size="14" font-weight="700" fill="#fff">{n:02d}</text>')
        # índice da ordem, pequeno, ao lado
        bx, by = ponto(n + 1.6, R_ORBITAS[i] + 14)
        a(f'<text x="{bx:.1f}" y="{by:.1f}" text-anchor="middle" dominant-baseline="central" '
          f'font-size="10" fill="{CORES[i]}">{i + 1}ª</text>')

    # Legenda
    a(f'<text x="20" y="30" fill="#cfd8e3" font-size="16" font-weight="700">Mega-Sena · concurso {concurso}</text>')
    a(f'<text x="20" y="50" fill="#8da2c0" font-size="12">ordem do sorteio: '
      + " → ".join(f"{n:02d}" for n in ordem) + '</text>')
    a('</svg>')
    return "\n".join(p)


def gerar(conn, concurso):
    """Grava o SVG de um concurso e devolve o caminho."""
    data = conn.execute("SELECT data_sorteio FROM concursos WHERE numero=?", (concurso,)).fetchone()[0]
    linhas = conn.execute(
        "SELECT dezena, posicao_sorteio FROM dezenas WHERE concurso=? "
        "ORDER BY COALESCE(posicao_sorteio, posicao_crescente)", (concurso,)).fetchall()
    ordem = [d for d, _ in linhas]
    d = "/".join(reversed(data.split("-")))
    SAIDA.mkdir(parents=True, exist_ok=True)
    saida = SAIDA / f"sorteio_{concurso}.svg"
    saida.write_text(svg(concurso, d, ordem), encoding="utf-8")
    return saida


def main():
    conn = sqlite3.connect(DB)
    args = [a for a in sys.argv[1:] if a != "--faltantes"]
    if args:
        print(gerar(conn, int(args[0])))
        return
    existentes = {int(f.stem.split("_")[1]) for f in SAIDA.glob("sorteio_*.svg")}
    todos = [r[0] for r in conn.execute("SELECT DISTINCT concurso FROM dezenas ORDER BY concurso")]
    faltam = [c for c in todos if c not in existentes]
    for c in faltam:
        gerar(conn, c)
    print(f"{len(faltam)} desenho(s) gerado(s) em {SAIDA}")


if __name__ == "__main__":
    main()
