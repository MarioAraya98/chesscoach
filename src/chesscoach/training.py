"""Logica del entrenador de blunder-check: seleccion de posiciones y veredictos."""

from __future__ import annotations

import io
from dataclasses import dataclass

import chess
import chess.pgn
import pandas as pd

TRAINABLE = ("blunder", "mistake")


@dataclass(frozen=True)
class Verdict:
    status: str  # "acierto" | "repetido" | "impreciso"
    icon: str
    message: str


def trainable_positions(issues: pd.DataFrame) -> pd.DataFrame:
    """Posiciones utiles para entrenar: errores graves con alternativa conocida.

    Sin `best_san` no hay con que comparar, asi que esas se descartan.
    """
    if issues.empty:
        return pd.DataFrame()
    usable = issues[
        issues["severity"].isin(TRAINABLE)
        & issues["fen_before"].notna()
        & issues["best_san"].astype(str).str.len().gt(0)
    ]
    return usable.sort_values("cp_loss", ascending=False).reset_index(drop=True)


def last_opponent_move(pgn: str, fen_before: str) -> str | None:
    """SAN de la jugada del rival que llevo a `fen_before`."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return None
    board = game.board()
    previous: str | None = None
    for move in game.mainline_moves():
        if board.fen() == fen_before:
            return previous
        previous = board.san(move)
        board.push(move)
    return None


def legal_sans(fen: str) -> list[str]:
    board = chess.Board(fen)
    return sorted(board.san(move) for move in board.legal_moves)


def judge(played: str, blunder: str, best: str) -> Verdict:
    if played == best:
        return Verdict("acierto", "✅", f"Correcto: **{best}** era la mejor.")
    if played == blunder:
        return Verdict(
            "repetido",
            "❌",
            f"Repetiste el error: **{blunder}**. La jugada era **{best}**.",
        )
    return Verdict(
        "impreciso",
        "🟡",
        f"Evitaste el error (jugaste **{played}**), pero la mejor era **{best}**.",
    )
