"""Lectura de estudios: partidas anotadas navegables jugada por jugada.

Cada jugada admite DOS comentarios en el mismo PGN, separados por etiquetas:

    { [[COACH]] mi analisis [[NOTAS]] lo que anotes vos leyendo }

Sin etiquetas, todo el comentario se toma como del autor del estudio. Asi los
estudios importados de Lichess conservan su texto en la columna del autor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chess
import chess.pgn
import httpx

from .config import STUDIES_DIR

_SPLIT = re.compile(r"\[\[(COACH|NOTAS)\]\]")
_STUDY_ID = re.compile(r"(?:lichess\.org/study/)?([A-Za-z0-9]{8})")


@dataclass(frozen=True)
class Step:
    """Una posicion del estudio, con la jugada que llevo a ella."""

    label: str
    san: str
    fen: str
    coach: str
    author: str
    uci: str | None


@dataclass(frozen=True)
class Chapter:
    title: str
    author_label: str
    steps: tuple[Step, ...]


def split_comment(comment: str) -> tuple[str, str]:
    """Separa un comentario en (entrenador, autor)."""
    texto = " ".join((comment or "").split())
    if not texto:
        return "", ""
    partes = _SPLIT.split(texto)
    if len(partes) == 1:
        return "", texto  # sin etiquetas: es del autor del estudio
    coach: list[str] = []
    autor: list[str] = []
    if partes[0].strip():
        autor.append(partes[0].strip())
    for etiqueta, cuerpo in zip(partes[1::2], partes[2::2], strict=True):
        destino = coach if etiqueta == "COACH" else autor
        if cuerpo.strip():
            destino.append(cuerpo.strip())
    return " ".join(coach), " ".join(autor)


def _title(game: chess.pgn.Game) -> str:
    event = game.headers.get("Event", "").strip()
    if event and event not in {"?", "-"}:
        return event
    return f"{game.headers.get('White', '?')} vs {game.headers.get('Black', '?')}"


def _read_chapters(path: Path) -> list[Chapter]:
    chapters: list[Chapter] = []
    with path.open(encoding="utf-8") as handle:
        while (game := chess.pgn.read_game(handle)) is not None:
            board = game.board()
            coach, autor = split_comment(game.comment)
            steps = [Step("inicio", "", board.fen(), coach, autor, None)]
            for node in game.mainline():
                move = node.move
                numero = board.fullmove_number
                label = f"{numero}." if board.turn == chess.WHITE else f"{numero}..."
                san = board.san(move)
                board.push(move)
                coach, autor = split_comment(node.comment)
                steps.append(Step(label, san, board.fen(), coach, autor, move.uci()))
            annotator = game.headers.get("Annotator", "").strip()
            chapters.append(
                Chapter(
                    title=_title(game),
                    author_label=annotator or "Autor del estudio",
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
        if chapters := _read_chapters(path):
            found[path.stem.replace("_", " ")] = tuple(chapters)
    return found


def import_lichess_study(url_or_id: str, name: str | None = None) -> Path:
    """Descarga un estudio PUBLICO de Lichess a `studies/`.

    Acepta la URL completa o el id de 8 caracteres.
    """
    match = _STUDY_ID.search(url_or_id.strip())
    if not match:
        raise ValueError(f"No se reconoce un id de estudio en: {url_or_id}")
    study_id = match.group(1)

    response = httpx.get(
        f"https://lichess.org/api/study/{study_id}.pgn",
        params={"comments": "true", "variations": "false"},
        headers={"User-Agent": "chesscoach"},
        follow_redirects=True,
        timeout=60,
    )
    if response.status_code == 404:
        raise ValueError(f"El estudio {study_id} no existe o no es publico.")
    response.raise_for_status()
    if not response.text.strip():
        raise ValueError(f"El estudio {study_id} vino vacio.")

    STUDIES_DIR.mkdir(parents=True, exist_ok=True)
    destino = STUDIES_DIR / f"{(name or study_id).replace(' ', '_')}.pgn"
    destino.write_text(response.text, encoding="utf-8")
    load_studies.cache_clear()
    return destino
