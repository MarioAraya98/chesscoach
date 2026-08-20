"""Panel de progreso de ajedrez. Ejecutar con: uv run streamlit run app.py"""

from __future__ import annotations

import sys
from pathlib import Path

# En la nube el paquete no se instala: hay que exponer src/ antes de importarlo.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from chesscoach import metrics, store, ui  # noqa: E402
from chesscoach.config import PUZZLES_PATH, load_config  # noqa: E402

st.set_page_config(page_title="ChessCoach — Panel de Mario", page_icon="♟️", layout="centered")
ui.compactar()

# Colores legibles en tema claro y oscuro: nada de fondos claros fijos, porque
# en modo oscuro el texto va en blanco y el bloque queda ilegible.
COLOR = {"ok": "#2ea043", "cerca": "#d29922", "lejos": "#f85149", "sin datos": "#8b949e"}
ICONO = {"ok": "✅", "cerca": "🟡", "lejos": "🔴", "sin datos": "⚪"}
FONDO = "rgba(128,128,128,.14)"
BORDE = "rgba(128,128,128,.35)"


@st.cache_data(ttl=60)
def cargar() -> tuple[pd.DataFrame, int, int]:
    config = load_config()
    with store.connect() as conn:
        total, hechas = store.counts(conn)
        frame = metrics.load_frame(conn, config)
    return frame, total, hechas


def valor(metric: metrics.Metric) -> str:
    if metric.value is None:
        return "—"
    if metric.unit == "%":
        return f"{metric.value * 100:.0f}%"
    if metric.unit == "s" and metric.value > 90:
        return f"{int(metric.value) // 60}:{int(metric.value) % 60:02d}"
    return f"{metric.value:.1f}{metric.unit}"


def meta(metric: metrics.Metric) -> str:
    if metric.unit == "%":
        return f"{metric.target * 100:.0f}%"
    if metric.unit == "s" and metric.target > 90:
        return f"{int(metric.target) // 60}:{int(metric.target) % 60:02d}"
    return f"{metric.target:.1f}{metric.unit}"


def avance(metric: metrics.Metric) -> float:
    """Cuanto falta para la meta, de 0 a 1, para dibujar la barrita."""
    if metric.value is None or not metric.target:
        return 0.0
    if metric.lower_is_better:
        return max(0.0, min(1.0, metric.target / metric.value)) if metric.value else 1.0
    return max(0.0, min(1.0, metric.value / metric.target))


def sin_zona(data: pd.DataFrame) -> pd.DataFrame:
    """Fechas sin zona horaria para que Vega no las desplace a la hora local."""
    salida = data.copy()
    salida["played_at"] = salida["played_at"].dt.tz_localize(None)
    return salida


config = load_config()
frame, descargadas, analizadas = cargar()

if frame.empty:
    st.title("♟️ ChessCoach")
    st.warning("Todavía no hay partidas analizadas. Corré `chesscoach all` en la terminal.")
    st.stop()

# --- filtros discretos, plegados ---
with st.sidebar:
    st.header("Filtros")
    fuentes = st.multiselect(
        "Plataforma", sorted(frame["source"].unique()), default=sorted(frame["source"].unique())
    )
    dias = st.slider("Últimos N días", 7, 365, 60, step=7)
    st.caption(f"{descargadas} descargadas · {analizadas} analizadas")

corte = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=dias)
vista = frame[frame["source"].isin(fuentes) & (frame["played_at"] >= corte)]
if vista.empty:
    st.info("No hay partidas en ese rango. Ampliá el filtro en el menú lateral.")
    st.stop()

calculadas = metrics.compute(vista, config)
en_meta = sum(m.on_target for m in calculadas)
ganadas = int((vista["result"] == "win").sum())
perdidas = int((vista["result"] == "loss").sum())
tablas = int((vista["result"] == "draw").sum())

# --- cabecera: lo esencial de un vistazo ---
ratings = vista.dropna(subset=["my_rating"])
insignias = []
for fuente, grupo in ratings.groupby("source"):
    ultimo = int(grupo["my_rating"].iloc[-1])
    delta = ultimo - int(grupo["my_rating"].iloc[0])
    signo = "#2ea043" if delta >= 0 else "#f85149"
    insignias.append(
        f"<span style='background:{FONDO};border-radius:8px;padding:.25rem .5rem;"
        f"margin-right:.4rem;white-space:nowrap'>{fuente} <b>{ultimo}</b> "
        f"<span style='color:{signo}'>{delta:+d}</span></span>"
    )

st.markdown(
    f"<div style='display:flex;justify-content:space-between;align-items:center;"
    f"flex-wrap:wrap;gap:.4rem'>"
    f"<h1 style='margin:0'>♟️ Panel de Mario</h1>"
    f"<div style='font-size:.95rem'>{''.join(insignias)}</div></div>"
    f"<div style='opacity:.75;font-size:.9rem;margin:.3rem 0 .6rem'>"
    f"{len(vista)} partidas · {ganadas}G {perdidas}P {tablas}T · "
    f"<b>{en_meta} de {len(calculadas)}</b> metas cumplidas</div>",
    unsafe_allow_html=True,
)

# --- lo primero que se ve: que hacer hoy ---
st.markdown("#### 🎯 Qué entrenar hoy")
for indice, tarea in enumerate(metrics.today_plan(vista, config), start=1):
    st.markdown(
        f"<div style='background:{FONDO};border-left:4px solid #4c8eda;border-radius:6px;"
        f"padding:.5rem .7rem;margin-bottom:.35rem;font-size:.92rem'>"
        f"<b>{indice}.</b> {tarea}</div>",
        unsafe_allow_html=True,
    )

st.markdown("")
accesos = st.columns(2)
accesos[0].link_button("🎯 Ir al Entrenador", "Entrenador", width="stretch")
accesos[1].link_button("📖 Ir a Estudios", "Estudios", width="stretch")

# --- metricas como tarjetas con barra de avance ---
st.markdown("#### Tarjeta de progreso")
filas = [calculadas[i:i + 2] for i in range(0, len(calculadas), 2)]
for fila in filas:
    columnas = st.columns(2)
    for columna, metrica in zip(columnas, fila, strict=False):
        pct = avance(metrica) * 100
        columna.markdown(
            f"<div style='border:1px solid {BORDE};border-radius:10px;padding:.5rem .7rem'>"
            f"<div style='font-size:.82rem;opacity:.8'>{ICONO[metrica.status]} {metrica.label}</div>"
            f"<div style='display:flex;align-items:baseline;gap:.4rem'>"
            f"<span style='font-size:1.5rem;font-weight:700;color:{COLOR[metrica.status]}'>"
            f"{valor(metrica)}</span>"
            f"<span style='font-size:.78rem;opacity:.6'>meta {meta(metrica)}</span></div>"
            f"<div style='background:{FONDO};border-radius:99px;height:5px;margin-top:.3rem'>"
            f"<div style='width:{pct:.0f}%;background:{COLOR[metrica.status]};"
            f"height:5px;border-radius:99px'></div></div></div>",
            unsafe_allow_html=True,
        )

# --- el resto, plegado: solo se abre si interesa ---
fugas = metrics.repertoire_leaks(vista)
if not fugas.empty:
    with st.expander(f"🔴 Fugas de repertorio ({len(fugas)})"):
        for fuga in fugas.head(6).itertuples():
            st.markdown(
                f"**{fuga.rep_chapter}** — jugada {fuga.jugada}: jugaste `{fuga.rep_played}`, "
                f"debe ser `{fuga.rep_expected}` · {fuga.veces}× ({fuga.derrotas} derrotas)"
            )

errores = metrics.issues_frame(vista)

with st.expander("📉 Tendencia"):
    tendencia = metrics.rolling_trend(vista)
    graficos = {
        "Errores graves": ("errores", config.targets["blunders_per_game"]),
        "Segundos por jugada": ("seg_por_jugada", config.targets["seconds_per_move"]),
        "Tiempo sobrante (s)": ("tiempo_sobrante", config.targets["time_left_seconds"]),
    }
    for titulo, (campo, objetivo) in graficos.items():
        datos = sin_zona(tendencia.dropna(subset=[campo]))
        if datos.empty:
            continue
        linea = (
            alt.Chart(datos).mark_line(point=True)
            .encode(x=alt.X("played_at:T", title=""), y=alt.Y(f"{campo}:Q", title=""))
        )
        guia = (
            alt.Chart(pd.DataFrame({"y": [objetivo]}))
            .mark_rule(strokeDash=[6, 4], color="green").encode(y="y:Q")
        )
        st.altair_chart((linea + guia).properties(title=titulo, height=180), width="stretch")

    if not ratings.empty:
        st.altair_chart(
            alt.Chart(sin_zona(ratings)).mark_line(point=True).encode(
                x=alt.X("played_at:T", title=""),
                y=alt.Y("my_rating:Q", title="Rating", scale=alt.Scale(zero=False)),
                color="source:N",
            ).properties(title="Evolución del rating", height=200),
            width="stretch",
        )

if not errores.empty:
    with st.expander("💸 Errores más caros"):
        peores = errores.sort_values("cp_loss", ascending=False).head(15)
        st.dataframe(
            peores[["played_at", "move_number", "san", "best_san", "severity",
                    "cp_loss", "seconds", "url"]]
            .rename(columns={
                "played_at": "Fecha", "move_number": "Jugada", "san": "Jugaste",
                "best_san": "Mejor", "severity": "Tipo", "cp_loss": "Pérdida (cp)",
                "seconds": "Seg", "url": "Partida",
            }),
            width="stretch", hide_index=True,
            column_config={"Partida": st.column_config.LinkColumn(display_text="abrir")},
        )
        if PUZZLES_PATH.exists() and PUZZLES_PATH.stat().st_size:
            st.download_button(
                "⬇️ Descargar mis errores como PGN",
                PUZZLES_PATH.read_bytes(),
                file_name="mis-blunders.pgn",
                mime="application/x-chess-pgn",
            )
