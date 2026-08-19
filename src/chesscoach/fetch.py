"""Descarga de partidas desde las APIs publicas de Lichess y chess.com."""

from __future__ import annotations

import io
import re
from datetime import UTC, datetime
from typing import Any

import chess.pgn
import httpx

USER_AGENT = "ChessCoach/0.1 (panel de progreso personal)"
TIMEOUT = httpx.Timeout(60.0)

_LICHESS_SPEED_TO_CLASS = {
    "ultraBullet": "bullet",
    "bullet": "bullet",
    "blitz": "blitz",
    "rapid": "rapid",
    "classical": "classical",
    "correspondence": "daily",
}


def _headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT}


def _parse_pgn(text: str) -> chess.pgn.Game | None:
    return chess.pgn.read_game(io.StringIO(text))


def _speed_from_time_control(tc: str) -> str:
    """Clasifica un control de tiempo estilo '600+5' como Lichess."""
    match = re.match(r"^(\d+)(?:\+(\d+))?$", tc or "")
    if not match:
        return "unknown"
    base, inc = int(match.group(1)), int(match.group(2) or 0)
    total = base + 40 * inc
    if total < 179:
        return "bullet"
    if total < 479:
        return "blitz"
    if total < 1499:
        return "rapid"
    return "classical"


def _game_row(
    *,
    game_id: str,
    source: str,
    url: str,
    played_at: datetime,
    headers: dict[str, str],
    username: str,
    time_class: str,
    pgn: str,
) -> dict[str, Any] | None:
    white = (headers.get("White") or "").lower()
    black = (headers.get("Black") or "").lower()
    user = username.lower()
    if user == white:
        color, opponent = "white", headers.get("Black")
        my_elo, opp_elo = headers.get("WhiteElo"), headers.get("BlackElo")
    elif user == black:
        color, opponent = "black", headers.get("White")
        my_elo, opp_elo = headers.get("BlackElo"), headers.get("WhiteElo")
    else:
        return None

    raw_result = headers.get("Result", "*")
    if raw_result == "1/2-1/2":
        result = "draw"
    elif raw_result == "*":
        result = "unknown"
    else:
        won = (raw_result == "1-0") == (color == "white")
        result = "win" if won else "loss"

    def to_int(value: str | None) -> int | None:
        try:
            return int(value) if value else None
        except ValueError:
            return None

    return {
        "id": game_id,
        "source": source,
        "url": url,
        "played_at": played_at.isoformat(),
        "color": color,
        "opponent": opponent,
        "my_rating": to_int(my_elo),
        "opp_rating": to_int(opp_elo),
        "result": result,
        "eco": headers.get("ECO"),
        "opening": headers.get("Opening") or headers.get("ECOUrl", "").rsplit("/", 1)[-1],
        "time_class": time_class,
        "time_control": headers.get("TimeControl"),
        "pgn": pgn,
    }


def fetch_lichess(username: str, max_games: int = 200) -> list[dict[str, Any]]:
    """Descarga las ultimas partidas de Lichess en formato NDJSON con PGN."""
    url = f"https://lichess.org/api/games/user/{username}"
    params = {
        "max": max_games,
        "pgnInJson": "true",
        "clocks": "true",
        "opening": "true",
        "sort": "dateDesc",
    }
    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        resp = client.get(
            url, params=params, headers={**_headers(), "Accept": "application/x-ndjson"}
        )
        resp.raise_for_status()
        for line in resp.text.splitlines():
            if not line.strip():
                continue
            import json

            payload = json.loads(line)
            pgn = payload.get("pgn")
            if not pgn:
                continue
            game = _parse_pgn(pgn)
            if game is None:
                continue
            played_at = datetime.fromtimestamp(payload["createdAt"] / 1000, tz=UTC)
            row = _game_row(
                game_id=f"lichess:{payload['id']}",
                source="lichess",
                url=f"https://lichess.org/{payload['id']}",
                played_at=played_at,
                headers=dict(game.headers),
                username=username,
                time_class=_LICHESS_SPEED_TO_CLASS.get(payload.get("speed", ""), "unknown"),
                pgn=pgn,
            )
            if row:
                rows.append(row)
    return rows


def fetch_chesscom(username: str, months: int = 6) -> list[dict[str, Any]]:
    """Descarga los archivos mensuales publicos de chess.com."""
    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        index = client.get(
            f"https://api.chess.com/pub/player/{username.lower()}/games/archives",
            headers=_headers(),
        )
        index.raise_for_status()
        for archive_url in index.json().get("archives", [])[-months:]:
            resp = client.get(archive_url, headers=_headers())
            resp.raise_for_status()
            for payload in resp.json().get("games", []):
                pgn = payload.get("pgn")
                if not pgn:
                    continue
                game = _parse_pgn(pgn)
                if game is None:
                    continue
                game_id = payload["url"].rstrip("/").rsplit("/", 1)[-1]
                played_at = datetime.fromtimestamp(payload["end_time"], tz=UTC)
                tc = payload.get("time_control", "")
                row = _game_row(
                    game_id=f"chesscom:{game_id}",
                    source="chesscom",
                    url=payload["url"],
                    played_at=played_at,
                    headers=dict(game.headers),
                    username=username,
                    time_class=payload.get("time_class") or _speed_from_time_control(tc),
                    pgn=pgn,
                )
                if row:
                    rows.append(row)
    return rows
