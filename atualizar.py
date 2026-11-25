"""Ponto único de atualização: base de sorteios, análises (analises/) e painéis.

Uso: python atualizar.py [--sem-coleta | --listar | --publicado]
Detalhes: python atualizar.py --help
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from megasena.atualizar import main  # noqa: E402

sys.exit(main(raiz=RAIZ))
