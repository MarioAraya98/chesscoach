"""Visor de estudios: partidas anotadas con dos columnas de comentario."""

from __future__ import annotations

import chess
import chess.svg
import streamlit as st

from chesscoach import studies

st.set_page_config(page_title="Estudios — ChessCoach", page_icon="📖", layout="wide")

st.title("📖 Estudios")

libros = studies.load_studies()
if not libros:
    st.warning(
        "No hay estudios todavía.\n\n"
        "Importá uno público de Lichess:\n"
        "```\npython -m chesscoach.cli study https://lichess.org/study/XXXXXXXX\n```\n"
        "o dejá cualquier `.pgn` anotado en la carpeta `studies/`."
    )
    st.stop()

seleccion = st.columns(2)
libro = seleccion[0].selectbox("Libro", list(libros))
capitulos = libros[libro]
titulos = [capitulo.title for capitulo in capitulos]
titulo = seleccion[1].selectbox("Capítulo", titulos)
capitulo = capitulos[titulos.index(titulo)]

# Botones y deslizador comparten la clave `paso`: si cada uno llevara su propio
# estado, el deslizador pisaria el valor de los botones en cada rerun.
estado = st.session_state
if estado.get("capitulo_actual") != (libro, titulo):
    estado.capitulo_actual = (libro, titulo)
    estado.paso = 0

total = len(capitulo.steps) - 1
estado.paso = min(estado.get("paso", 0), total)
paso = capitulo.steps[estado.paso]

tablero, comentarios = st.columns([1, 1], gap="large")

with tablero:
    board = chess.Board(paso.fen)
    ultima = chess.Move.from_uci(paso.uci) if paso.uci else None
    svg = chess.svg.board(board, lastmove=ultima, size=390, coordinates=True)
    st.markdown(f'<div style="display:flex;justify-content:center">{svg}</div>',
                unsafe_allow_html=True)

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
    if total:
        st.slider("Ir a la jugada", 0, total, key="paso")

with comentarios:
    if paso.san:
        st.markdown(f"## {paso.label} {paso.san}")
    else:
        st.markdown("## Introducción")

    st.markdown("#### 🎓 Entrenador")
    if paso.coach:
        st.info(paso.coach)
    else:
        st.caption("Sin comentario del entrenador en esta jugada.")

    st.markdown(f"#### 📗 {capitulo.author_label}")
    if paso.author:
        st.success(paso.author)
    else:
        st.caption(
            "Vacío. Acá van las notas del autor del estudio, o las tuyas: agregá "
            "`[[NOTAS]] tu texto` en el comentario del PGN."
        )

with st.expander("Ver todas las jugadas"):
    linea = " ".join(
        f"**{s.label} {s.san}**" if index == estado.paso else f"{s.label} {s.san}"
        for index, s in enumerate(capitulo.steps)
        if s.san
    )
    st.markdown(linea)
