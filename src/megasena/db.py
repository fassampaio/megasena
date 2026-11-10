"""Persistência em SQLite."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from .validacao import Concurso

ESQUEMA = """
CREATE TABLE IF NOT EXISTS concursos (
    numero                  INTEGER PRIMARY KEY,
    data_sorteio            TEXT    NOT NULL,          -- ISO AAAA-MM-DD
    acumulado               INTEGER,                   -- 0/1
    valor_arrecadado        REAL,
    valor_estimado_proximo  REAL,
    local_sorteio           TEXT,
    municipio_uf            TEXT,
    arquivo_raw             TEXT    NOT NULL,
    json_sha256             TEXT    NOT NULL,
    coletado_em             TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_concursos_data ON concursos(data_sorteio);

CREATE TABLE IF NOT EXISTS dezenas (
    concurso           INTEGER NOT NULL REFERENCES concursos(numero) ON DELETE CASCADE,
    dezena             INTEGER NOT NULL CHECK (dezena BETWEEN 1 AND 60),
    posicao_crescente  INTEGER NOT NULL CHECK (posicao_crescente BETWEEN 1 AND 6),
    posicao_sorteio    INTEGER          CHECK (posicao_sorteio BETWEEN 1 AND 6), -- NULL se não publicada
    PRIMARY KEY (concurso, posicao_crescente),
    UNIQUE (concurso, dezena),
    UNIQUE (concurso, posicao_sorteio)
);
CREATE INDEX IF NOT EXISTS ix_dezenas_dezena ON dezenas(dezena);

CREATE TABLE IF NOT EXISTS rateio (
    concurso      INTEGER NOT NULL REFERENCES concursos(numero) ON DELETE CASCADE,
    faixa         INTEGER NOT NULL,
    descricao     TEXT,
    ganhadores    INTEGER NOT NULL CHECK (ganhadores >= 0),
    valor_premio  REAL    NOT NULL CHECK (valor_premio >= 0),
    PRIMARY KEY (concurso, faixa)
);

CREATE TABLE IF NOT EXISTS coleta_log (
    concurso       INTEGER PRIMARY KEY,
    status         TEXT    NOT NULL CHECK (status IN ('ok', 'erro')),
    tentativas     INTEGER NOT NULL DEFAULT 0,
    ultimo_erro    TEXT,
    avisos         TEXT,
    atualizado_em  TEXT    NOT NULL
);
"""


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def conectar(caminho: Path) -> sqlite3.Connection:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(ESQUEMA)
    return conn


def numeros_existentes(conn: sqlite3.Connection) -> set[int]:
    return {r[0] for r in conn.execute("SELECT numero FROM concursos")}


def datas_vizinhas(conn: sqlite3.Connection, numero: int) -> tuple[date | None, date | None]:
    """Data do concurso gravado imediatamente antes e depois de `numero`."""
    ant = conn.execute(
        "SELECT data_sorteio FROM concursos WHERE numero < ? ORDER BY numero DESC LIMIT 1",
        (numero,)).fetchone()
    pos = conn.execute(
        "SELECT data_sorteio FROM concursos WHERE numero > ? ORDER BY numero ASC LIMIT 1",
        (numero,)).fetchone()
    conv = lambda r: date.fromisoformat(r[0]) if r else None
    return conv(ant), conv(pos)


def gravar_concurso(conn: sqlite3.Connection, c: Concurso, arquivo_raw: str, sha256: str) -> None:
    """Grava (ou substitui) um concurso inteiro numa única transação."""
    posicao_sorteio = (
        {d: i for i, d in enumerate(c.dezenas_sorteio, 1)} if c.dezenas_sorteio else {}
    )
    agora = _agora()
    with conn:
        conn.execute("DELETE FROM dezenas WHERE concurso = ?", (c.numero,))
        conn.execute("DELETE FROM rateio WHERE concurso = ?", (c.numero,))
        conn.execute("DELETE FROM concursos WHERE numero = ?", (c.numero,))
        conn.execute(
            """INSERT INTO concursos (numero, data_sorteio, acumulado, valor_arrecadado,
                   valor_estimado_proximo, local_sorteio, municipio_uf,
                   arquivo_raw, json_sha256, coletado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (c.numero, c.data.isoformat(),
             None if c.acumulado is None else int(c.acumulado),
             c.valor_arrecadado, c.valor_estimado_proximo,
             c.local_sorteio, c.municipio_uf, arquivo_raw, sha256, agora))
        conn.executemany(
            "INSERT INTO dezenas (concurso, dezena, posicao_crescente, posicao_sorteio) "
            "VALUES (?, ?, ?, ?)",
            [(c.numero, d, i, posicao_sorteio.get(d))
             for i, d in enumerate(c.dezenas_crescente, 1)])
        conn.executemany(
            "INSERT INTO rateio (concurso, faixa, descricao, ganhadores, valor_premio) "
            "VALUES (?, ?, ?, ?, ?)",
            [(c.numero, f.faixa, f.descricao, f.ganhadores, f.valor_premio) for f in c.rateio])
        conn.execute(
            """INSERT INTO coleta_log (concurso, status, tentativas, ultimo_erro, avisos, atualizado_em)
               VALUES (?, 'ok', 1, NULL, ?, ?)
               ON CONFLICT(concurso) DO UPDATE SET
                   status = 'ok', tentativas = tentativas + 1, ultimo_erro = NULL,
                   avisos = excluded.avisos, atualizado_em = excluded.atualizado_em""",
            (c.numero, "; ".join(c.avisos) or None, agora))


def registrar_erro(conn: sqlite3.Connection, numero: int, erro: str) -> None:
    with conn:
        conn.execute(
            """INSERT INTO coleta_log (concurso, status, tentativas, ultimo_erro, atualizado_em)
               VALUES (?, 'erro', 1, ?, ?)
               ON CONFLICT(concurso) DO UPDATE SET
                   status = 'erro', tentativas = tentativas + 1,
                   ultimo_erro = excluded.ultimo_erro, atualizado_em = excluded.atualizado_em""",
            (numero, erro, _agora()))


def dezenas_gravadas(conn: sqlite3.Connection, numero: int) -> tuple[list[int], list[int | None]]:
    """(dezenas em ordem crescente, dezenas em ordem de sorteio ou [] se não houver)."""
    linhas = conn.execute(
        "SELECT dezena, posicao_crescente, posicao_sorteio FROM dezenas WHERE concurso = ?",
        (numero,)).fetchall()
    crescente = [d for d, _, _ in sorted(linhas, key=lambda r: r[1])]
    com_ordem = [r for r in linhas if r[2] is not None]
    sorteio = [d for d, _, _ in sorted(com_ordem, key=lambda r: r[2])]
    return crescente, sorteio
