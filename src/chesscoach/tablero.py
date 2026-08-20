"""Componente propio de tablero: permite tocar o arrastrar la pieza en el telefono.

Streamlit no trae un tablero interactivo y los paquetes de terceros disponibles
no sirven (esperan una imagen rasterizada). Este componente dibuja el SVG que ya
genera python-chess y le superpone una rejilla de 8x8 que captura los gestos,
devolviendo a Python la casilla de origen y la de destino.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chess
import chess.svg
import streamlit.components.v1 as components

_RUTA = Path(__file__).resolve().parent / "componentes" / "tablero"
_componente = components.declare_component("tablero_chesscoach", path=str(_RUTA))


def tablero_tactil(
    board: chess.Board,
    orientacion: chess.Color,
    *,
    seleccion: int | None = None,
    destinos: tuple[int, ...] = (),
    maximo: int = 400,
    key: str | None = None,
) -> dict[str, Any] | None:
    """Dibuja el tablero interactivo y devuelve el ultimo gesto.

    El resultado es `{"desde": "e2", "hasta": "e4", "n": 3}`. Cuando `desde` y
    `hasta` coinciden fue un toque simple (elegir pieza); si difieren, el usuario
    arrastro o toco el destino. El contador `n` permite ignorar gestos repetidos.
    """
    # Sin coordenadas el tablero llena el SVG y la rejilla calza casilla a casilla.
    svg = chess.svg.board(
        board,
        orientation=orientacion,
        size=maximo,
        coordinates=False,
        squares=chess.SquareSet(destinos) if destinos else None,
    )
    return _componente(
        svg=svg,
        orientacion="white" if orientacion == chess.WHITE else "black",
        seleccion=chess.square_name(seleccion) if seleccion is not None else None,
        destinos=[chess.square_name(c) for c in destinos],
        maximo=maximo,
        key=key,
        default=None,
    )
