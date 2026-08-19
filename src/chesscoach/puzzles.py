"""Genera un PGN de puzzles a partir de los propios errores de Mario."""

from __future__ import annotations

import chess
import chess.pgn
import pandas as pd

from .config import PUZZLES_PATH, ensure_data_dir

SEVERITY_LABEL = {
    "blunder": "ERROR GRAVE",
    "mistake": "Error",
    "inaccuracy": "Imprecision",
}


def export_puzzles(issues: pd.DataFrame, limit: int = 60) -> int:
    """Escribe las posiciones previas a cada error como capitulos de estudio."""
    ensure_data_dir()
    if issues.empty:
        PUZZLES_PATH.write_text("", encoding="utf-8")
        return 0

    selected = (
        issues[issues["severity"].isin(["blunder", "mistake"])]
        .sort_values(["cp_loss"], ascending=False)
        .head(limit)
    )

    chunks: list[str] = []
    for row in selected.itertuples():
        board = chess.Board(row.fen_before)
        game = chess.pgn.Game()
        game.setup(board)
        label = SEVERITY_LABEL.get(row.severity, row.severity)
        tag = " [PIEZA ATRAPADA]" if getattr(row, "trapped_piece", False) else ""
        game.headers["Event"] = f"{label}{tag} - jugada {row.move_number}"
        game.headers["Site"] = row.url or "?"
        game.headers["White"] = "Juegan" if board.turn == chess.WHITE else "?"
        game.headers["Result"] = "*"
        best = f" La mejor era {row.best_san}." if row.best_san else ""
        game.comment = (
            f"Jugaste {row.san} y perdiste {row.cp_loss / 100:.1f} puntos.{best}"
            " Encuentra la jugada correcta."
        )
        chunks.append(str(game))

    PUZZLES_PATH.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
    return len(chunks)
