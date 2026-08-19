"""Almacenamiento SQLite de partidas y su analisis."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .config import DB_PATH, ensure_data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    url           TEXT,
    played_at     TEXT NOT NULL,
    color         TEXT NOT NULL,
    opponent      TEXT,
    my_rating     INTEGER,
    opp_rating    INTEGER,
    result        TEXT NOT NULL,
    eco           TEXT,
    opening       TEXT,
    time_class    TEXT,
    time_control  TEXT,
    pgn           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis (
    game_id        TEXT PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
    analyzed_at    TEXT NOT NULL,
    engine         TEXT,
    inaccuracies   INTEGER NOT NULL DEFAULT 0,
    mistakes       INTEGER NOT NULL DEFAULT 0,
    blunders       INTEGER NOT NULL DEFAULT 0,
    my_moves       INTEGER NOT NULL DEFAULT 0,
    avg_seconds    REAL,
    time_left_s    REAL,
    reached_winning INTEGER NOT NULL DEFAULT 0,
    converted      INTEGER,
    rep_exit_ply   INTEGER,
    rep_chapter    TEXT,
    rep_expected   TEXT,
    rep_played     TEXT,
    details        TEXT NOT NULL DEFAULT '{}'
);
"""


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    ensure_data_dir()
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_game(conn: sqlite3.Connection, game: dict[str, Any]) -> bool:
    """Inserta la partida. Devuelve True si era nueva."""
    cur = conn.execute("SELECT 1 FROM games WHERE id = ?", (game["id"],))
    if cur.fetchone():
        return False
    cols = ", ".join(game)
    marks = ", ".join("?" for _ in game)
    conn.execute(f"INSERT INTO games ({cols}) VALUES ({marks})", tuple(game.values()))
    return True


def save_analysis(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    row = dict(row)
    row["details"] = json.dumps(row.get("details", {}), ensure_ascii=False)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT OR REPLACE INTO analysis ({cols}) VALUES ({marks})", tuple(row.values())
    )


def unanalyzed_games(
    conn: sqlite3.Connection, time_classes: tuple[str, ...]
) -> list[sqlite3.Row]:
    """Partidas pendientes, las mas recientes primero."""
    marks = ", ".join("?" for _ in time_classes)
    return conn.execute(
        "SELECT g.* FROM games g LEFT JOIN analysis a ON a.game_id = g.id"
        f" WHERE a.game_id IS NULL AND g.time_class IN ({marks})"
        " ORDER BY g.played_at DESC",
        time_classes,
    ).fetchall()


def joined_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT g.*, a.inaccuracies, a.mistakes, a.blunders, a.my_moves,"
        " a.avg_seconds, a.time_left_s, a.reached_winning, a.converted,"
        " a.rep_exit_ply, a.rep_chapter, a.rep_expected, a.rep_played, a.details"
        " FROM games g LEFT JOIN analysis a ON a.game_id = g.id"
        " ORDER BY g.played_at"
    ).fetchall()


def counts(conn: sqlite3.Connection) -> tuple[int, int]:
    games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    done = conn.execute("SELECT COUNT(*) FROM analysis").fetchone()[0]
    return games, done


def analyzed_games(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT g.* FROM games g JOIN analysis a ON a.game_id = g.id"
    ).fetchall()


def update_repertoire(conn: sqlite3.Connection, game_id: str, dev: Any | None) -> None:
    """Reescribe solo las columnas de repertorio: no requiere volver a correr el motor."""
    hit = dev if dev is not None and dev.by_me else None
    conn.execute(
        "UPDATE analysis SET rep_exit_ply = ?, rep_chapter = ?, rep_expected = ?,"
        " rep_played = ? WHERE game_id = ?",
        (
            hit.ply if hit else None,
            hit.chapter if hit else None,
            hit.expected if hit else None,
            hit.played if hit else None,
            game_id,
        ),
    )
