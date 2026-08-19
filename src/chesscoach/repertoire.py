"""Detecta en que jugada Mario se sale de su repertorio preparado."""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chess
import chess.pgn

from .config import REPERTOIRE_PATH

GENERIC_CHAPTER = "Repertorio (varias lineas)"


@dataclass(frozen=True)
class Deviation:
    """Punto donde la partida abandona el repertorio."""

    ply: int
    chapter: str
    expected: str
    played: str
    by_me: bool

    @property
    def move_number(self) -> int:
        return self.ply // 2 + 1


@dataclass(frozen=True)
class Line:
    """Una linea preparada: el capitulo, el color que juega Mario y sus jugadas."""

    chapter: str
    color: chess.Color
    moves: tuple[str, ...]


@lru_cache(maxsize=1)
def load_lines(path: Path | None = None) -> tuple[Line, ...]:
    source = path or REPERTOIRE_PATH
    if not source.exists():
        return ()

    lines: list[Line] = []
    stream = io.StringIO(source.read_text(encoding="utf-8"))
    while (game := chess.pgn.read_game(stream)) is not None:
        board = game.board()
        sans: list[str] = []
        for move in game.mainline_moves():
            sans.append(board.san(move))
            board.push(move)
        if not sans:
            continue
        # El header White/Black marca de que lado juega Mario en ese capitulo.
        color = chess.WHITE if game.headers.get("White", "").lower() == "mario" else chess.BLACK
        lines.append(
            Line(chapter=game.headers.get("Event", "sin nombre"), color=color, moves=tuple(sans))
        )
    return tuple(lines)


def find_deviation(
    game: chess.pgn.Game, my_color: chess.Color, max_ply: int
) -> Deviation | None:
    """Primera jugada de Mario dentro de `max_ply` que se aparta del repertorio.

    Solo se consideran los capitulos preparados para su color. Si el rival sale
    primero del libro, la linea deja de estar preparada y no se reporta nada.
    """
    alive = [line for line in load_lines() if line.color == my_color]
    if not alive:
        return None

    board = game.board()
    for ply, move in enumerate(game.mainline_moves()):
        if ply >= max_ply:
            return None
        alive = [line for line in alive if len(line.moves) > ply]
        if not alive:
            return None

        san = board.san(move)
        matching = [line for line in alive if line.moves[ply] == san]
        if matching:
            alive = matching
            board.push(move)
            continue

        if board.turn != my_color:
            return None  # el rival salio del libro: la preparacion ya no aplica

        expected = sorted({line.moves[ply] for line in alive})
        chapters = {line.chapter for line in alive}
        return Deviation(
            ply=ply,
            chapter=alive[0].chapter if len(chapters) == 1 else GENERIC_CHAPTER,
            expected=" / ".join(expected),
            played=san,
            by_me=True,
        )
    return None
