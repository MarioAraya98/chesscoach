"""Localizacion y descarga automatica del motor Stockfish."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import httpx

from .config import DATA_DIR, ensure_data_dir

ENGINE_DIR = DATA_DIR / "engine"
RELEASES_API = "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"
# Se prefiere la primera variante compatible con CPUs modernas; sse41-popcnt es el mas portable.
ASSET_PREFERENCE = ("windows-x86-64-avx2", "windows-x86-64-sse41-popcnt", "windows-x86-64")


def find_engine() -> Path | None:
    """Busca Stockfish en PATH y luego en la carpeta local del proyecto."""
    on_path = shutil.which("stockfish")
    if on_path:
        return Path(on_path)
    if ENGINE_DIR.is_dir():
        for candidate in sorted(ENGINE_DIR.rglob("stockfish*.exe")):
            return candidate
        for candidate in sorted(ENGINE_DIR.rglob("stockfish")):
            if candidate.is_file():
                return candidate
    return None


def _pick_asset(assets: list[dict]) -> dict | None:
    for token in ASSET_PREFERENCE:
        for asset in assets:
            name = asset.get("name", "")
            if token in name and name.endswith(".zip"):
                return asset
    return None


def download_engine(progress=print) -> Path:
    """Descarga la ultima release de Stockfish para Windows y la descomprime."""
    ensure_data_dir()
    ENGINE_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=httpx.Timeout(120.0), follow_redirects=True) as client:
        release = client.get(RELEASES_API, headers={"User-Agent": "ChessCoach"})
        release.raise_for_status()
        asset = _pick_asset(release.json().get("assets", []))
        if asset is None:
            raise RuntimeError("No se encontro un binario de Stockfish para Windows.")

        progress(f"Descargando {asset['name']} ...")
        archive = ENGINE_DIR / asset["name"]
        with client.stream("GET", asset["browser_download_url"]) as stream:
            stream.raise_for_status()
            with archive.open("wb") as handle:
                for chunk in stream.iter_bytes(chunk_size=1 << 16):
                    handle.write(chunk)

    progress("Descomprimiendo ...")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(ENGINE_DIR)
    archive.unlink(missing_ok=True)

    engine = find_engine()
    if engine is None:
        raise RuntimeError("Descarga completa pero no se encontro el ejecutable.")
    progress(f"Motor listo: {engine}")
    return engine


def ensure_engine(progress=print) -> Path:
    return find_engine() or download_engine(progress)
