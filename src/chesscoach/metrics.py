"""Calculo de las metricas del plan de entrenamiento."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .config import Config

COLUMNS = [
    "id", "source", "url", "played_at", "color", "opponent", "my_rating",
    "opp_rating", "result", "eco", "opening", "time_class", "blunders",
    "mistakes", "inaccuracies", "my_moves", "avg_seconds", "time_left_s",
    "reached_winning", "converted", "rep_exit_ply", "rep_chapter",
    "rep_expected", "rep_played", "details",
]


@dataclass(frozen=True)
class Metric:
    """Una metrica con su meta y direccion de mejora."""

    key: str
    label: str
    value: float | None
    target: float
    lower_is_better: bool
    unit: str = ""

    @property
    def on_target(self) -> bool:
        if self.value is None:
            return False
        return self.value <= self.target if self.lower_is_better else self.value >= self.target

    @property
    def status(self) -> str:
        if self.value is None:
            return "sin datos"
        if self.on_target:
            return "ok"
        margin = 0.3 * self.target if self.target else 0.3
        distance = (
            self.value - self.target if self.lower_is_better else self.target - self.value
        )
        return "cerca" if distance <= margin else "lejos"


def load_frame(conn: sqlite3.Connection, config: Config) -> pd.DataFrame:
    from .store import joined_rows

    rows = [dict(r) for r in joined_rows(conn)]
    frame = pd.DataFrame(rows, columns=COLUMNS if rows else COLUMNS)
    if frame.empty:
        return frame
    frame["played_at"] = pd.to_datetime(frame["played_at"], format="mixed", utc=True)
    frame = frame[frame["time_class"].isin(config.time_classes)]
    return frame.sort_values("played_at").reset_index(drop=True)


def issues_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Aplana todas las jugadas problematicas en una tabla."""
    records: list[dict[str, Any]] = []
    for row in frame.itertuples():
        if not isinstance(row.details, str):
            continue
        for issue in json.loads(row.details).get("issues", []):
            records.append({**issue, "game_id": row.id, "url": row.url,
                            "played_at": row.played_at, "opening": row.opening})
    return pd.DataFrame(records)


def rushed_error_rate(frame: pd.DataFrame, rushed_seconds: int) -> float | None:
    """Proporcion de errores graves cometidos en jugadas apuradas.

    Es la metrica que conecta la causa (jugar rapido) con el efecto (colgar piezas).
    """
    issues = issues_frame(frame)
    if issues.empty or "seconds" not in issues:
        return None
    serious = issues[issues["severity"].isin(["blunder", "mistake"])].dropna(subset=["seconds"])
    if serious.empty:
        return None
    return float((serious["seconds"] < rushed_seconds).mean())


def compute(frame: pd.DataFrame, config: Config) -> list[Metric]:
    t = config.targets
    if frame.empty:
        empty = [None] * 6
        blunders, time_left, spm, disasters, conversion, rushed = empty
    else:
        analyzed = frame.dropna(subset=["my_moves"])
        blunders = (
            (analyzed["blunders"] + analyzed["mistakes"]).mean()
            if not analyzed.empty
            else None
        )
        time_left = frame["time_left_s"].mean()
        spm = frame["avg_seconds"].mean()
        disasters = frame["rep_exit_ply"].notna().sum() / len(frame)
        winning = frame[frame["reached_winning"] == 1]
        conversion = winning["converted"].mean() if not winning.empty else None
        rushed = rushed_error_rate(frame, config.analysis.rushed_seconds)

    def clean(value: Any) -> float | None:
        return None if value is None or pd.isna(value) else float(value)

    return [
        Metric("blunders", "Errores graves por partida", clean(blunders),
               t["blunders_per_game"], True),
        Metric("time_left", "Tiempo sobrante al terminar", clean(time_left),
               t["time_left_seconds"], True, "s"),
        Metric("spm", "Segundos por jugada", clean(spm),
               t["seconds_per_move"], False, "s"),
        Metric("rushed", "Errores por jugar apurado", clean(rushed),
               t["rushed_error_rate"], True, "%"),
        Metric("disasters", "Partidas fuera del repertorio", clean(disasters),
               t["opening_disasters"], True, "%"),
        Metric("conversion", "Ventajas ganadoras convertidas", clean(conversion),
               t["conversion_rate"], False, "%"),
    ]


def rolling_trend(frame: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """Media movil de las metricas clave para graficar la tendencia."""
    if frame.empty:
        return pd.DataFrame()
    trend = frame[["played_at", "my_rating", "source"]].copy()
    trend["errores"] = (frame["blunders"] + frame["mistakes"]).rolling(window, min_periods=3).mean()
    trend["seg_por_jugada"] = frame["avg_seconds"].rolling(window, min_periods=3).mean()
    trend["tiempo_sobrante"] = frame["time_left_s"].rolling(window, min_periods=3).mean()
    return trend


def repertoire_leaks(frame: pd.DataFrame) -> pd.DataFrame:
    """Agrupa las salidas del repertorio por linea, para saber que estudiar."""
    if frame.empty or frame["rep_exit_ply"].isna().all():
        return pd.DataFrame()
    leaks = frame.dropna(subset=["rep_exit_ply"])
    grouped = (
        leaks.groupby(["rep_chapter", "rep_expected", "rep_played"])
        .agg(veces=("id", "count"),
             jugada=("rep_exit_ply", lambda s: int(s.iloc[0]) // 2 + 1),
             derrotas=("result", lambda s: (s == "loss").sum()))
        .reset_index()
        .sort_values(["veces", "derrotas"], ascending=False)
    )
    return grouped


def today_plan(frame: pd.DataFrame, config: Config) -> list[str]:
    """Traduce las metricas fuera de meta en tareas concretas, la peor primero."""
    if frame.empty:
        return ["Sin datos: corre `chesscoach all` despues de jugar."]

    by_key = {m.key: m for m in compute(frame, config)}
    tasks: list[tuple[int, str]] = []

    rushed = by_key["rushed"]
    if rushed.value is not None and not rushed.on_target:
        tasks.append((
            0,
            f"{rushed.value * 100:.0f}% de tus errores graves salieron en menos de "
            f"{config.analysis.rushed_seconds}s. Antes de mover, cuenta hasta 15 y "
            f"revisa jaques y capturas del rival.",
        ))

    spm = by_key["spm"]
    if spm.value is not None and not spm.on_target:
        tasks.append((
            1,
            f"Promedias {spm.value:.0f}s por jugada (meta {spm.target:.0f}s). "
            f"Juega hoy en 15+10 y termina con menos de 3:00 en el reloj.",
        ))

    leaks = repertoire_leaks(frame)
    if not leaks.empty:
        worst = leaks.iloc[0]
        tasks.append((
            2,
            f"Repasa {worst.rep_chapter}: en la jugada {worst.jugada} juegas "
            f"{worst.rep_played} y deberia ser {worst.rep_expected} "
            f"({worst.veces} veces, {worst.derrotas} derrotas).",
        ))

    conversion = by_key["conversion"]
    if conversion.value is not None and not conversion.on_target:
        tasks.append((
            3,
            f"Convertiste {conversion.value * 100:.0f}% de las posiciones ganadas. "
            f"Con ventaja material: cambia piezas, no peones del enroque.",
        ))

    if not tasks:
        return ["Todas las metricas en meta. Sube el control de tiempo o el nivel de rival."]
    return [text for _, text in sorted(tasks)]
