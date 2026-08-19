"""Carga de configuracion y rutas del proyecto."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config.yaml"
REPERTOIRE_PATH = ROOT / "repertoire.pgn"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "games.db"
PUZZLES_PATH = DATA_DIR / "mis-blunders.pgn"


@dataclass(frozen=True)
class Analysis:
    inaccuracy_wp: int
    mistake_wp: int
    blunder_wp: int
    winning_cp: int
    engine_depth: int
    engine_movetime_ms: int
    repertoire_depth: int
    rushed_seconds: int


@dataclass(frozen=True)
class Config:
    lichess_user: str
    chesscom_user: str
    time_classes: tuple[str, ...]
    targets: dict[str, float]
    analysis: Analysis


@lru_cache(maxsize=1)
def load_config(path: Path | None = None) -> Config:
    raw = yaml.safe_load((path or CONFIG_PATH).read_text(encoding="utf-8"))
    accounts = raw["accounts"]
    return Config(
        lichess_user=accounts["lichess"],
        chesscom_user=accounts["chesscom"],
        time_classes=tuple(raw["time_classes"]),
        targets=raw["targets"],
        analysis=Analysis(**raw["analysis"]),
    )


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
