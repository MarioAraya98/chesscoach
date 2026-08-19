"""Panel de progreso de ajedrez. Ejecutar con: uv run streamlit run app.py"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from chesscoach import metrics, store
from chesscoach.config import PUZZLES_PATH, load_config

st.set_page_config(page_title="ChessCoach - Panel de Mario", page_icon="♟️", layout="wide")

STATUS_ICON = {"ok": "✅", "cerca": "🟡", "lejos": "🔴", "sin datos": "⚪"}


@st.cache_data(ttl=60)
def load_data() -> tuple[pd.DataFrame, int, int]:
    config = load_config()
    with store.connect() as conn:
        total, done = store.counts(conn)
        frame = metrics.load_frame(conn, config)
    return frame, total, done


def format_value(metric: metrics.Metric) -> str:
    if metric.value is None:
        return "—"
    if metric.unit == "%":
        return f"{metric.value * 100:.0f}%"
    if metric.unit == "s" and metric.value > 90:
        return f"{int(metric.value) // 60}:{int(metric.value) % 60:02d}"
    return f"{metric.value:.1f}{metric.unit}"


def format_target(metric: metrics.Metric) -> str:
    if metric.unit == "%":
        return f"{metric.target * 100:.0f}%"
    if metric.unit == "s" and metric.target > 90:
        return f"{int(metric.target) // 60}:{int(metric.target) % 60:02d}"
    return f"{metric.target:.1f}{metric.unit}"


def chart_ready(data: pd.DataFrame) -> pd.DataFrame:
    """Fechas sin zona horaria para que Vega no las desplace a la hora local."""
    out = data.copy()
    out["played_at"] = out["played_at"].dt.tz_localize(None)
    return out


config = load_config()
frame, total_games, analyzed = load_data()

st.title("♟️ Panel de Progreso — Mario")

if frame.empty:
    st.warning(
        "Todavia no hay partidas analizadas. Corre en la terminal:\n\n"
        "```\nuv run chesscoach all\n```"
    )
    st.stop()

# --- filtros ---
with st.sidebar:
    st.header("Filtros")
    sources = st.multiselect(
        "Plataforma", sorted(frame["source"].unique()), default=sorted(frame["source"].unique())
    )
    days = st.slider("Ultimos N dias", 7, 365, 60, step=7)
    st.divider()
    st.caption(f"{total_games} partidas descargadas · {analyzed} analizadas")

cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
view = frame[frame["source"].isin(sources) & (frame["played_at"] >= cutoff)]
if view.empty:
    st.info("No hay partidas en ese rango. Amplia el filtro.")
    st.stop()

# --- cabecera ---
wins = int((view["result"] == "win").sum())
losses = int((view["result"] == "loss").sum())
draws = int((view["result"] == "draw").sum())
ratings = view.dropna(subset=["my_rating"])
computed = metrics.compute(view, config)

head = st.columns(4)
head[0].metric("Partidas", len(view))
head[1].metric("Récord", f"{wins}-{losses}-{draws}")
# Los ratings de Lichess y chess.com no son comparables: nunca se promedian.
head[2].markdown("**Rating**")
for source, group in ratings.groupby("source"):
    latest = int(group["my_rating"].iloc[-1])
    delta = latest - int(group["my_rating"].iloc[0])
    head[2].markdown(f"{source} · **{latest}** `{delta:+d}`")
head[3].metric(
    "Precisión del plan", f"{sum(m.on_target for m in computed)}/{len(computed)}"
)

st.divider()

# --- que entrenar hoy ---
st.subheader("🎯 Qué entrenar hoy")
for index, task in enumerate(metrics.today_plan(view, config), start=1):
    st.info(f"**{index}.** {task}")

st.divider()

# --- tarjeta de metricas ---
st.subheader("Tarjeta de progreso")
cards = st.columns(3)
for position, metric in enumerate(computed):
    cards[position % 3].markdown(
        f"**{STATUS_ICON[metric.status]} {metric.label}**\n\n"
        f"# {format_value(metric)}\n"
        f"meta: {format_target(metric)}"
    )

st.divider()

# --- alertas accionables ---
left, right = st.columns(2)

with left:
    st.subheader("🔴 Fugas de repertorio")
    leaks = metrics.repertoire_leaks(view)
    if leaks.empty:
        st.success("Sin desviaciones. El repertorio se está aplicando.")
    else:
        for leak in leaks.head(5).itertuples():
            st.error(
                f"**{leak.rep_chapter}** — jugada {leak.jugada}: jugaste "
                f"`{leak.rep_played}`, debe ser `{leak.rep_expected}` "
                f"· {leak.veces}× ({leak.derrotas} derrotas)"
            )

with right:
    st.subheader("🐴 Piezas atrapadas")
    issues = metrics.issues_frame(view)
    trapped = issues[issues["trapped_piece"]] if not issues.empty else pd.DataFrame()
    if trapped.empty:
        st.success("Ninguna pieza quedó atrapada. Regla del caballo viajero aplicada.")
    else:
        for row in trapped.head(6).itertuples():
            st.warning(f"Jugada {row.move_number}: `{row.san}` — [ver partida]({row.url})")

st.divider()

# --- tendencias ---
st.subheader("Tendencia (media móvil de 10 partidas)")
trend = metrics.rolling_trend(view)
charts = {
    "Errores graves por partida": ("errores", config.targets["blunders_per_game"]),
    "Segundos por jugada": ("seg_por_jugada", config.targets["seconds_per_move"]),
    "Tiempo sobrante (s)": ("tiempo_sobrante", config.targets["time_left_seconds"]),
}
columns = st.columns(3)
for column, (title, (field, target)) in zip(columns, charts.items(), strict=True):
    data = chart_ready(trend.dropna(subset=[field]))
    if data.empty:
        column.caption(f"{title}: sin datos suficientes")
        continue
    line = (
        alt.Chart(data)
        .mark_line(point=True)
        .encode(x=alt.X("played_at:T", title=""), y=alt.Y(f"{field}:Q", title=""))
    )
    goal = (
        alt.Chart(pd.DataFrame({"y": [target]}))
        .mark_rule(strokeDash=[6, 4], color="green")
        .encode(y="y:Q")
    )
    column.altair_chart((line + goal).properties(title=title, height=240), use_container_width=True)

if not ratings.empty:
    st.altair_chart(
        alt.Chart(chart_ready(ratings))
        .mark_line(point=True)
        .encode(
            x=alt.X("played_at:T", title=""),
            y=alt.Y("my_rating:Q", title="Rating", scale=alt.Scale(zero=False)),
            color="source:N",
        )
        .properties(title="Evolución del rating", height=260),
        use_container_width=True,
    )

st.divider()

# --- errores recientes ---
st.subheader("Errores más caros")
if issues.empty:
    st.info("Sin errores registrados en este rango.")
else:
    top = issues.sort_values("cp_loss", ascending=False).head(15)
    st.dataframe(
        top[["played_at", "move_number", "san", "best_san", "severity", "cp_loss", "seconds", "url"]]
        .rename(columns={
            "played_at": "Fecha", "move_number": "Jugada", "san": "Jugaste",
            "best_san": "Mejor", "severity": "Tipo", "cp_loss": "Pérdida (cp)",
            "seconds": "Segundos", "url": "Partida",
        }),
        use_container_width=True,
        hide_index=True,
        column_config={"Partida": st.column_config.LinkColumn(display_text="abrir")},
    )
    if PUZZLES_PATH.exists() and PUZZLES_PATH.stat().st_size:
        st.download_button(
            "⬇️ Descargar mis errores como PGN (importar en Lichess Study)",
            PUZZLES_PATH.read_bytes(),
            file_name="mis-blunders.pgn",
            mime="application/x-chess-pgn",
        )
