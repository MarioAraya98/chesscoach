"""Visor de estudios: recorrer partidas anotadas jugada por jugada."""

from __future__ import annotations

import chess
import chess.svg
import streamlit as st

from chesscoach import studies

st.set_page_config(page_title="Estudios — ChessCoach", page_icon="📖", layout="centered")

st.title("📖 Estudios")

libros = studies.load_studies()
if not libros:
    st.warning(
        "No hay estudios todavía. Poné archivos `.pgn` anotados en la carpeta `studies/`.\n\n"
        "Podés exportar cualquier Lichess Study como PGN y dejarlo ahí."
    )
    st.stop()

libro = st.selectbox("Libro", list(libros))
capitulos = libros[libro]
titulos = [capitulo.title for capitulo in capitulos]
titulo = st.selectbox("Capítulo", titulos)
capitulo = capitulos[titulos.index(titulo)]

# Cambiar de capitulo reinicia la navegacion.
estado = st.session_state
if estado.get("capitulo_actual") != (libro, titulo):
    estado.capitulo_actual = (libro, titulo)
    estado.paso = 0

total = len(capitulo.steps) - 1
estado.paso = min(estado.paso, total)
paso = capitulo.steps[estado.paso]

tablero = chess.Board(paso.fen)
ultima = chess.Move.from_uci(paso.uci) if paso.uci else None
svg = chess.svg.board(tablero, lastmove=ultima, size=380, coordinates=True)
st.markdown(f'<div style="display:flex;justify-content:center">{svg}</div>', unsafe_allow_html=True)

# --- navegacion ---
botones = st.columns(4)
if botones[0].button("⏮ Inicio", width="stretch"):
    estado.paso = 0
    st.rerun()
if botones[1].button("◀ Atrás", width="stretch"):
    estado.paso = max(0, estado.paso - 1)
    st.rerun()
if botones[2].button("Siguiente ▶", type="primary", width="stretch"):
    estado.paso = min(total, estado.paso + 1)
    st.rerun()
if botones[3].button("Final ⏭", width="stretch"):
    estado.paso = total
    st.rerun()

st.caption(f"Jugada {estado.paso} de {total}")

if paso.san:
    st.markdown(f"### {paso.label} {paso.san}")
if paso.comment:
    st.info(paso.comment)
elif paso.san:
    st.caption("Sin comentario en esta jugada.")

with st.expander("Ver todas las jugadas"):
    linea = " ".join(
        f"**{s.label}** {s.san}" if index == estado.paso else f"{s.label} {s.san}"
        for index, s in enumerate(capitulo.steps)
        if s.san
    )
    st.markdown(linea)
