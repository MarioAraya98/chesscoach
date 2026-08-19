"""Lectura de estudios: partidas anotadas navegables jugada por jugada."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chess
import chess.pgn

from .config import STUDIES_DIR


@dataclass(frozen=True)
class Step:
    """Una posicion del estudio, con la jugada que llevo a ella y su comentario."""

    label: str  # "12..." o "inicio"
    san: str
    fen: str
    comment: str
    uci: str | None  # para resaltar la ultima jugada en el tablero


@dataclass(frozen=True)
class Chapter:
    title: str
    intro: str
    steps: tuple[Step, ...]


def _title(game: chess.pgn.Game) -> str:
    event = game.headers.get("Event", "").strip()
    if event and event not in {"?", "-"}:
        return event
    white = game.headers.get("White", "?")
    black = game.headers.get("Black", "?")
    return f"{white} vs {black}"


def _read_chapters(path: Path) -> list[Chapter]:
    chapters: list[Chapter] = []
    with path.open(encoding="utf-8") as handle:
        while (game := chess.pgn.read_game(handle)) is not None:
            board = game.board()
            steps = [
                Step(label="inicio", san="", fen=board.fen(), comment=game.comment, uci=None)
            ]
            for node in game.mainline():
                move = node.move
                number = board.fullmove_number
                label = f"{number}." if board.turn == chess.WHITE else f"{number}..."
                san = board.san(move)
                board.push(move)
                steps.append(
                    Step(
                        label=label,
                        san=san,
                        fen=board.fen(),
                        comment=node.comment.strip(),
                        uci=move.uci(),
                    )
                )
            chapters.append(
                Chapter(
                    title=_title(game),
                    intro=game.headers.get("Annotator", ""),
                    steps=tuple(steps),
                )
            )
    return chapters


@lru_cache(maxsize=1)
def load_studies() -> dict[str, tuple[Chapter, ...]]:
    """Todos los estudios de `studies/`, agrupados por archivo."""
    if not STUDIES_DIR.exists():
        return {}
    found: dict[str, tuple[Chapter, ...]] = {}
    for path in sorted(STUDIES_DIR.glob("*.pgn")):
        chapters = _read_chapters(path)
        if chapters:
            found[path.stem.replace("_", " ")] = tuple(chapters)
    return found
