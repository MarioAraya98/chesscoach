"""Piezas de interfaz compartidas por las paginas, pensadas para el telefono.

El diseno sigue la idea de Lichess: el tablero manda y los controles son una
barra delgada que no le roba espacio.
"""

from __future__ import annotations

import re

import chess
import chess.svg
import streamlit as st

# Solo la etiqueta <svg> de apertura: si se tocan todos los elementos se borran
# tambien los width/height de los <rect> y el tablero se queda sin casillas.
_SVG_ABRE = re.compile(r"<svg\b[^>]*>")
_DIMENSION = re.compile(r'\s(?:width|height)="[^"]*"')

COMPACTO = """
<style>
  .block-container {padding-top: 3.2rem; padding-bottom: 1rem; max-width: 46rem;}
  div[data-testid="stVerticalBlock"] {gap: .4rem;}

  /* Streamlit apila las columnas en pantallas angostas: en el telefono eso
     convertiria la barra de 4 flechas en 4 filas. Se fuerza una sola fila. */
  div[data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    gap: .25rem !important;
  }
  div[data-testid="stHorizontalBlock"] > div,
  div[data-testid="stColumn"] {
    min-width: 0 !important;
    flex: 1 1 0% !important;
    width: auto !important;
  }

  /* Controles delgados, al estilo de la barra de Lichess */
  div[data-testid="stButton"] button {
    padding: .15rem .2rem; min-height: 2rem; line-height: 1.1; width: 100%;
  }
  div[data-testid="stButton"] button p {font-size: .85rem; margin: 0;}
  h1 {font-size: 1.4rem; margin-bottom: .1rem; padding-top: 0;}
  div[data-testid="stAlert"] {padding: .55rem .7rem;}
  div[data-testid="stAlert"] p {font-size: .9rem; margin: 0;}
  div[data-testid="stExpander"] summary p {font-size: .85rem;}

  /* En el telefono cada pixel de ancho cuenta para el tablero */
  @media (max-width: 640px) {
    .block-container {padding-left: .5rem; padding-right: .5rem; padding-top: 2.8rem;}
    div[data-testid="stButton"] button p {font-size: .8rem;}
  }
</style>
"""


def compactar() -> None:
    """Reduce margenes y alturas para que entre mas contenido en una pantalla."""
    st.markdown(COMPACTO, unsafe_allow_html=True)


def _escalable(svg: str) -> str:
    """Deja que el SVG llene su contenedor."""

    def arreglar(etiqueta: re.Match[str]) -> str:
        limpia = _DIMENSION.sub("", etiqueta.group(0))
        return limpia[:-1] + ' style="width:100%;height:100%;display:block">'

    return _SVG_ABRE.sub(arreglar, svg, count=1)


def tablero(
    board: chess.Board,
    orientacion: chess.Color,
    *,
    resaltar=(),
    flechas=(),
    maximo: int = 420,
) -> None:
    """Dibuja el tablero ocupando casi todo el ancho, como en el movil de Lichess."""
    svg = chess.svg.board(
        board,
        orientation=orientacion,
        coordinates=True,
        squares=chess.SquareSet(resaltar) if resaltar else None,
        arrows=flechas,
    )
    # El contenedor lleva aspect-ratio para que su altura se sepa antes de medir
    # el SVG; sin eso Streamlit fija un alto menor y recorta la ultima fila.
    st.markdown(
        "<div style='display:flex;justify-content:center;margin-bottom:.4rem'>"
        f"<div style='width:min(94vw,{maximo}px);aspect-ratio:1/1'>{_escalable(svg)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
