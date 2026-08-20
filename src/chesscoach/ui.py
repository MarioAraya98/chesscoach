"""Piezas de interfaz compartidas por las paginas, pensadas para el telefono."""

from __future__ import annotations

import re

import chess
import chess.svg
import streamlit as st

_DIMENSIONES = re.compile(r'\s(?:width|height)="\d+"')

COMPACTO = """
<style>
  .block-container {padding-top: 2.2rem; padding-bottom: 1rem;}
  div[data-testid="stVerticalBlock"] {gap: .45rem;}
  div[data-testid="stHorizontalBlock"] {gap: .35rem;}
  button[kind] p {font-size: .82rem; margin: 0;}
  h1 {font-size: 1.45rem; margin-bottom: .2rem;}
  div[data-testid="stAlert"] p {font-size: .9rem;}
</style>
"""


def compactar() -> None:
    """Reduce margenes y tamanos para que entre mas contenido en una pantalla."""
    st.markdown(COMPACTO, unsafe_allow_html=True)


def tablero(
    board: chess.Board,
    orientacion: chess.Color,
    *,
    resaltar=(),
    flechas=(),
    maximo: int = 320,
) -> None:
    """Dibuja el tablero escalable al ancho disponible.

    Se le quitan los atributos width/height del SVG para que el viewBox mande y
    la figura se ajuste sola a la pantalla del telefono.
    """
    svg = chess.svg.board(
        board,
        orientation=orientacion,
        coordinates=True,
        squares=chess.SquareSet(resaltar) if resaltar else None,
        arrows=flechas,
    )
    st.markdown(
        "<div style='display:flex;justify-content:center'>"
        f"<div style='width:min(72vw,{maximo}px)'>{_DIMENSIONES.sub('', svg)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
