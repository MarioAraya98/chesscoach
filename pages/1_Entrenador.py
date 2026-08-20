"""Entrenador de blunder-check: revivir tus propias posiciones antes del error.

Pensado para el telefono: marcador en una linea, una pregunta a la vez y la
jugada se hace tocando la pieza y despues la casilla de destino.
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

# En la nube el paquete no se instala: hay que exponer src/ antes de importarlo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import chess  # noqa: E402
import chess.svg  # noqa: E402
import streamlit as st  # noqa: E402

from chesscoach import metrics, store, training, ui  # noqa: E402
from chesscoach.config import load_config  # noqa: E402
from chesscoach.tablero import tablero_tactil  # noqa: E402

st.set_page_config(page_title="Entrenador — ChessCoach", page_icon="🎯", layout="centered")
ui.compactar()

PREGUNTAS = (
    "¿Qué **jaques** tiene el rival?",
    "¿Qué **capturas** tiene el rival?",
    "¿Qué amenaza su **última jugada**?",
)
LADO = 380


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


def mostrar_tablero(board: chess.Board, orientacion: chess.Color, resaltar=(), flecha=()) -> None:
    ui.tablero(board, orientacion, resaltar=resaltar, flechas=flecha, maximo=LADO)


config = load_config()
espera = config.analysis.rushed_seconds
posiciones = cargar_posiciones()

st.title("🎯 Entrenador")

if posiciones.empty:
    st.warning("Todavía no hay posiciones. Corré `chesscoach analyze` primero.")
    st.stop()

estado = st.session_state
if "orden" not in estado:
    estado.orden = random.sample(range(len(posiciones)), len(posiciones))
    estado.pos = 0
    estado.fase = "pensando"
    estado.pregunta = 0
    estado.inicio = time.time()
    estado.origen = None
    estado.ultimo_gesto = None
    estado.stats = {"acierto": 0, "repetido": 0, "impreciso": 0}


def siguiente() -> None:
    estado.pos = (estado.pos + 1) % len(estado.orden)
    estado.fase = "pensando"
    estado.pregunta = 0
    estado.inicio = time.time()
    estado.origen = None
    estado.ultimo_gesto = None


def resolver(san: str, fila) -> None:
    estado.veredicto = training.judge(san, fila.san, fila.best_san)
    estado.stats[estado.veredicto.status] += 1
    estado.fase = "resultado"


fila = posiciones.iloc[estado.orden[estado.pos]]
tablero = chess.Board(fila.fen_before)
orientacion = tablero.turn

# --- marcador en una sola linea ---
s = estado.stats
hechas = sum(s.values())
st.markdown(
    "<div style='display:flex;gap:16px;flex-wrap:wrap;align-items:center;"
    "font-size:1rem;margin-bottom:.3rem'>"
    f"<span><b>{hechas}</b> resueltas</span>"
    f"<span>✅ <b>{s['acierto']}</b></span>"
    f"<span>🟡 <b>{s['impreciso']}</b></span>"
    f"<span>❌ <b>{s['repetido']}</b></span>"
    f"<span style='opacity:.6'>{len(posiciones)} disponibles</span>"
    "</div>",
    unsafe_allow_html=True,
)

color = "blancas" if orientacion == chess.WHITE else "negras"
rival = jugada_del_rival(fila.game_id, fila.fen_before)
pie = f"Jugás con <b>{color}</b> · jugada {int(fila.move_number)}"
if rival:
    pie += f" · el rival jugó <b>{rival}</b>"
st.markdown(f"<div style='font-size:.9rem;opacity:.85'>{pie}</div>", unsafe_allow_html=True)

# --- fase 1: pensar, una pregunta a la vez ---
if estado.fase == "pensando":
    mostrar_tablero(tablero, orientacion)

    indice = estado.pregunta
    st.markdown(f"**Pregunta {indice + 1} de {len(PREGUNTAS)}** — {PREGUNTAS[indice]}")
    st.text_input("respuesta", key=f"q{estado.pos}_{indice}",
                  placeholder="escribí lo que ves...", label_visibility="collapsed")

    ultima = indice == len(PREGUNTAS) - 1
    if st.button("Ya puedo mover ▶" if ultima else "Siguiente pregunta ▶",
                 type="primary", width="stretch"):
        if not ultima:
            estado.pregunta += 1
            st.rerun()
        restante = espera - (time.time() - estado.inicio)
        if restante > 0:
            st.warning(f"Pensá {restante:.0f}s más. La prisa es tu error #1.")
        else:
            estado.fase = "moviendo"
            st.rerun()

# --- fase 2: tocar la pieza y despues el destino (o arrastrarla) ---
elif estado.fase == "moviendo":
    destinos = tuple(
        m.to_square for m in tablero.legal_moves if m.from_square == estado.origen
    ) if estado.origen is not None else ()

    if estado.origen is None:
        st.caption("Tocá la pieza que querés mover, o arrastrala.")
    else:
        pieza = tablero.piece_at(estado.origen).unicode_symbol()
        st.caption(f"{pieza} en {chess.square_name(estado.origen)} · tocá el destino.")

    gesto = tablero_tactil(
        tablero, orientacion,
        seleccion=estado.origen, destinos=destinos,
        maximo=LADO, key=f"tb{estado.pos}",
    )

    if gesto and gesto.get("n") != estado.get("ultimo_gesto"):
        estado.ultimo_gesto = gesto["n"]
        desde = chess.parse_square(gesto["desde"])
        hasta = chess.parse_square(gesto["hasta"])
        movibles = {m.from_square for m in tablero.legal_moves}

        if desde == hasta:
            estado.origen = desde if desde in movibles else None
            st.rerun()
        else:
            jugada = chess.Move(desde, hasta)
            if jugada not in tablero.legal_moves:  # corona siempre a dama
                jugada = chess.Move(desde, hasta, promotion=chess.QUEEN)
            if jugada in tablero.legal_moves:
                resolver(tablero.san(jugada), fila)
            else:
                estado.origen = desde if desde in movibles else None
            st.rerun()

    with st.expander("Elegir de una lista"):
        elegida = st.selectbox("Tu jugada", training.legal_sans(fila.fen_before),
                               key=f"sel{estado.pos}", label_visibility="collapsed")
        if st.button("Confirmar", type="primary", width="stretch"):
            resolver(elegida, fila)
            st.rerun()

# --- fase 3: resultado ---
else:
    veredicto = estado.veredicto
    mejor = tablero.parse_san(fila.best_san)
    mostrar_tablero(tablero, orientacion,
                    flecha=[chess.svg.Arrow(mejor.from_square, mejor.to_square, color="#15781B")])
    {"acierto": st.success, "impreciso": st.warning, "repetido": st.error}[veredicto.status](
        f"{veredicto.icon} {veredicto.message}"
    )

    detalle = f"Perdiste {int(fila.cp_loss)} centipeones."
    if fila.seconds is not None and fila.seconds == fila.seconds:
        detalle += f" Ese día jugaste esta posición en **{fila.seconds:.0f}s**."
    if fila.trapped_piece:
        detalle += " 🐴 La pieza quedó atrapada."
    st.info(detalle)

    st.markdown(f"[Ver la partida completa]({fila.url})")
    if st.button("Siguiente posición ▶", type="primary", width="stretch"):
        siguiente()
        st.rerun()
