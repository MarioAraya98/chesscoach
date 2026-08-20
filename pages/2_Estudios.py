"""Visor de estudios optimizado para el telefono: tablero y comentario a la vez."""

from __future__ import annotations

import sys
from pathlib import Path

# En la nube el paquete no se instala: hay que exponer src/ antes de importarlo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import chess  # noqa: E402
import chess.svg  # noqa: E402
import streamlit as st  # noqa: E402

from chesscoach import studies, ui  # noqa: E402

st.set_page_config(page_title="Estudios — ChessCoach", page_icon="📖", layout="centered")
ui.compactar()

libros = studies.load_studies()
if not libros:
    st.warning(
        "No hay estudios todavía.\n\n"
        "Importá uno público de Lichess:\n"
        "```\npython -m chesscoach.cli study https://lichess.org/study/XXXXXXXX\n```"
    )
    st.stop()

estado = st.session_state
libro = estado.get("libro") or next(iter(libros))
capitulos = libros.get(libro, next(iter(libros.values())))
titulos = [c.title for c in capitulos]
titulo = estado.get("titulo") if estado.get("titulo") in titulos else titulos[0]
capitulo = capitulos[titulos.index(titulo)]

# El selector va plegado: en el telefono cada linea cuenta.
with st.expander(f"📖 {titulo}", expanded=False):
    nuevo_libro = st.selectbox("Libro", list(libros), index=list(libros).index(libro))
    nuevos = libros[nuevo_libro]
    nuevos_titulos = [c.title for c in nuevos]
    indice = nuevos_titulos.index(titulo) if titulo in nuevos_titulos else 0
    nuevo_titulo = st.selectbox("Capítulo", nuevos_titulos, index=indice)
    if (nuevo_libro, nuevo_titulo) != (libro, titulo):
        estado.libro, estado.titulo = nuevo_libro, nuevo_titulo
        estado.paso = 0
        st.rerun()

if estado.get("capitulo_actual") != (libro, titulo):
    estado.capitulo_actual = (libro, titulo)
    estado.paso = 0

total = len(capitulo.steps) - 1
estado.paso = min(estado.get("paso", 0), total)
paso = capitulo.steps[estado.paso]

flecha = ()
if paso.uci:
    movimiento = chess.Move.from_uci(paso.uci)
    flecha = [chess.svg.Arrow(movimiento.from_square, movimiento.to_square, color="#15781B")]

ui.tablero(chess.Board(paso.fen), chess.WHITE, flechas=flecha, maximo=300)

# --- navegacion compacta, en una sola fila ---
botones = st.columns([1, 1, 1, 1])
if botones[0].button("⏮", width="stretch"):
    estado.paso = 0
    st.rerun()
if botones[1].button("◀", width="stretch"):
    estado.paso = max(0, estado.paso - 1)
    st.rerun()
if botones[2].button("▶", type="primary", width="stretch"):
    estado.paso = min(total, estado.paso + 1)
    st.rerun()
if botones[3].button("⏭", width="stretch"):
    estado.paso = total
    st.rerun()

encabezado = f"{paso.label} {paso.san}" if paso.san else "Introducción"
st.markdown(
    f"<div style='display:flex;justify-content:space-between;font-size:.9rem;"
    f"opacity:.75;margin:.1rem 0'><b>{encabezado}</b>"
    f"<span>{estado.paso}/{total}</span></div>",
    unsafe_allow_html=True,
)

if paso.coach:
    st.info(paso.coach)
elif not paso.author:
    st.caption("Sin comentario en esta jugada.")

if paso.author:
    with st.expander(f"📗 {capitulo.author_label}", expanded=not paso.coach):
        st.success(paso.author)

with st.expander("Todas las jugadas"):
    st.markdown(
        " ".join(
            f"**{s.label} {s.san}**" if i == estado.paso else f"{s.label} {s.san}"
            for i, s in enumerate(capitulo.steps)
            if s.san
        )
    )
