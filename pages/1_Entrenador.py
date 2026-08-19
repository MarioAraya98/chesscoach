"""Entrenador de blunder-check: revivir tus propias posiciones antes del error."""

from __future__ import annotations

import random
import time

import chess
import chess.svg
import streamlit as st

from chesscoach import metrics, store, training
from chesscoach.config import load_config

st.set_page_config(page_title="Entrenador — ChessCoach", page_icon="🎯", layout="centered")

PREGUNTAS = (
    "¿Qué jaques tiene el rival?",
    "¿Qué capturas tiene el rival?",
    "¿Qué amenaza su última jugada?",
)


@st.cache_data(ttl=300)
def cargar_posiciones():
    config = load_config()
    with store.connect() as conn:
        frame = metrics.load_frame(conn, config)
    return training.trainable_positions(metrics.issues_frame(frame))


@st.cache_data(ttl=300)
def jugada_del_rival(game_id: str, fen: str) -> str | None:
    with store.connect() as conn:
        pgn = store.game_pgn(conn, game_id)
    return training.last_opponent_move(pgn, fen) if pgn else None


config = load_config()
espera = config.analysis.rushed_seconds
posiciones = cargar_posiciones()

st.title("🎯 Entrenador de blunder-check")

if posiciones.empty:
    st.warning("Todavía no hay posiciones. Corré `chesscoach analyze` primero.")
    st.stop()

st.caption(
    f"{len(posiciones)} posiciones de tus propias partidas, justo antes de tu error. "
    f"No sabés si hay peligro — como en una partida real."
)

# --- estado de la sesion ---
estado = st.session_state
if "orden" not in estado:
    estado.orden = random.sample(range(len(posiciones)), len(posiciones))
    estado.pos = 0
    estado.fase = "pensando"
    estado.inicio = time.time()
    estado.stats = {"acierto": 0, "repetido": 0, "impreciso": 0}


def siguiente() -> None:
    estado.pos = (estado.pos + 1) % len(estado.orden)
    estado.fase = "pensando"
    estado.inicio = time.time()


fila = posiciones.iloc[estado.orden[estado.pos]]
tablero = chess.Board(fila.fen_before)

# --- marcador ---
total = sum(estado.stats.values())
marcador = st.columns(4)
marcador[0].metric("Resueltas", total)
marcador[1].metric("✅ Mejor jugada", estado.stats["acierto"])
marcador[2].metric("🟡 Evitó el error", estado.stats["impreciso"])
marcador[3].metric("❌ Repitió", estado.stats["repetido"])

st.divider()

# --- tablero ---
svg = chess.svg.board(tablero, orientation=tablero.turn, size=380, coordinates=True)
st.markdown(f'<div style="display:flex;justify-content:center">{svg}</div>', unsafe_allow_html=True)

color = "blancas" if tablero.turn == chess.WHITE else "negras"
rival = jugada_del_rival(fila.game_id, fila.fen_before)
# Va dentro de HTML para centrarlo, asi que el enfasis no puede ser markdown.
pie = f"Jugás con <b>{color}</b> · jugada {int(fila.move_number)}"
if rival:
    pie += f" · el rival acaba de jugar <b>{rival}</b>"
st.markdown(f"<p style='text-align:center'>{pie}</p>", unsafe_allow_html=True)

st.divider()

# --- fase 1: pensar ---
if estado.fase == "pensando":
    transcurrido = time.time() - estado.inicio
    restante = max(0, espera - transcurrido)

    st.subheader("Antes de mover, respondé:")
    for indice, pregunta in enumerate(PREGUNTAS):
        st.text_input(pregunta, key=f"q{estado.pos}_{indice}", placeholder="escribí lo que ves...")

    if restante > 0:
        st.progress(transcurrido / espera, text=f"Pensá {restante:.0f}s más")
        if st.button("Ya lo pensé", width="stretch"):
            st.rerun()  # recalcula el tiempo transcurrido
    else:
        st.success(f"Listo, pasaron {espera}s. Ahora elegí tu jugada.")
        if st.button("Elegir jugada", type="primary", width="stretch"):
            estado.fase = "moviendo"
            st.rerun()

# --- fase 2: mover ---
elif estado.fase == "moviendo":
    jugada = st.selectbox("Tu jugada", training.legal_sans(fila.fen_before), key=f"m{estado.pos}")
    if st.button("Confirmar", type="primary", width="stretch"):
        estado.veredicto = training.judge(jugada, fila.san, fila.best_san)
        estado.stats[estado.veredicto.status] += 1
        estado.fase = "resultado"
        st.rerun()

# --- fase 3: resultado ---
else:
    veredicto = estado.veredicto
    mostrar = {"acierto": st.success, "impreciso": st.warning, "repetido": st.error}
    mostrar[veredicto.status](f"{veredicto.icon} {veredicto.message}")

    detalle = f"Perdiste {int(fila.cp_loss)} centipeones."
    if fila.seconds is not None and not (fila.seconds != fila.seconds):
        detalle += f" Ese día jugaste esta posición en **{fila.seconds:.0f}s**."
    if fila.trapped_piece:
        detalle += " 🐴 La pieza quedó atrapada."
    st.info(detalle)

    st.markdown(f"[Ver la partida completa]({fila.url})")
    if st.button("Siguiente posición", type="primary", width="stretch"):
        siguiente()
        st.rerun()
