"""Analiza partidas con Stockfish y extrae las metricas del plan de entrenamiento."""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn

from .config import Analysis
from .repertoire import find_deviation

_CLOCK_RE = re.compile(r"\[%clk\s+(\d+):(\d+):(\d+(?:\.\d+)?)\]")
_EVAL_RE = re.compile(r"\[%eval\s+(#?-?\d+(?:\.\d+)?)\]")
MATE_CP = 10_000


def win_percent(cp: int) -> float:
    """Centipeones -> probabilidad de victoria 0-100 (curva logistica de Lichess)."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * max(-1000, min(1000, cp)))) - 1)


@dataclass
class MoveIssue:
    """Una jugada de Mario que empeoro la posicion."""

    ply: int
    move_number: int
    san: str
    best_san: str
    severity: str
    cp_loss: int
    wp_loss: float
    fen_before: str
    seconds: float | None
    trapped_piece: bool = False


@dataclass
class GameReport:
    game_id: str
    issues: list[MoveIssue] = field(default_factory=list)
    my_moves: int = 0
    avg_seconds: float | None = None
    time_left_s: float | None = None
    reached_winning: bool = False
    converted: bool | None = None
    deviation: Any = None

    def count(self, severity: str) -> int:
        return sum(1 for issue in self.issues if issue.severity == severity)


def _clock_seconds(comment: str) -> float | None:
    match = _CLOCK_RE.search(comment or "")
    if not match:
        return None
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def _pgn_eval_cp(comment: str) -> int | None:
    """Lee la anotacion [%eval] de Lichess. Siempre desde la vista de las blancas."""
    match = _EVAL_RE.search(comment or "")
    if not match:
        return None
    token = match.group(1)
    if token.startswith("#"):
        mate_in = int(token[1:])
        return MATE_CP if mate_in > 0 else -MATE_CP
    return int(round(float(token) * 100))


def _score_cp(info: dict, color: chess.Color) -> int:
    score = info["score"].pov(color)
    mate = score.mate()
    if mate is not None:
        return MATE_CP if mate > 0 else -MATE_CP
    return score.score() or 0


def _increment_seconds(time_control: str | None) -> float:
    match = re.match(r"^(\d+)\+(\d+)$", time_control or "")
    return float(match.group(2)) if match else 0.0


def _is_trapped_piece_blunder(board_before: chess.Board, move: chess.Move) -> bool:
    """Heuristica: la pieza movida queda atacada y sin casillas seguras de retirada."""
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type in (chess.PAWN, chess.KING):
        return False

    board = board_before.copy()
    board.push(move)
    if not board.is_attacked_by(not piece.color, move.to_square):
        return False

    # Simula la respuesta del rival para evaluar las salidas reales de la pieza.
    board.push(chess.Move.null())
    escapes = 0
    for escape in board.legal_moves:
        if escape.from_square != move.to_square:
            continue
        after = board.copy()
        after.push(escape)
        if not after.is_attacked_by(not piece.color, escape.to_square):
            escapes += 1
    return escapes == 0


def deviation_for(row: dict[str, Any], rep_depth: int) -> Any:
    """Desviacion de repertorio de una partida. No necesita motor."""
    game = chess.pgn.read_game(io.StringIO(row["pgn"]))
    if game is None:
        return None
    my_color = chess.WHITE if row["color"] == "white" else chess.BLACK
    return find_deviation(game, my_color, rep_depth)


def analyze_game(
    row: dict[str, Any],
    engine: chess.engine.SimpleEngine | None,
    settings: Analysis,
    rep_depth: int,
) -> GameReport:
    game = chess.pgn.read_game(io.StringIO(row["pgn"]))
    if game is None:
        return GameReport(game_id=row["id"])

    my_color = chess.WHITE if row["color"] == "white" else chess.BLACK
    report = GameReport(game_id=row["id"])
    report.deviation = find_deviation(game, my_color, rep_depth)

    limit = chess.engine.Limit(
        depth=settings.engine_depth, time=settings.engine_movetime_ms / 1000
    )
    increment = _increment_seconds(row.get("time_control"))

    board = game.board()
    node = game
    prev_clock: float | None = None
    last_clock: float | None = None
    move_times: list[float] = []
    prev_eval: int | None = None

    while node.variations:
        node = node.variations[0]
        move = node.move
        my_turn = board.turn == my_color
        comment = node.comment or ""

        # --- reloj ---
        clock = _clock_seconds(comment)
        if my_turn and clock is not None:
            if prev_clock is not None:
                spent = prev_clock + increment - clock
                if 0 <= spent < 600:
                    move_times.append(spent)
            prev_clock = clock
            last_clock = clock

        # --- evaluacion ---
        eval_before = prev_eval
        eval_after: int | None = None
        if engine is not None:
            if eval_before is None:
                eval_before = _score_cp(engine.analyse(board, limit), my_color)
            after_board = board.copy()
            after_board.push(move)
            eval_after = (
                -MATE_CP
                if after_board.is_checkmate() and after_board.turn == my_color
                else _score_cp(engine.analyse(after_board, limit), my_color)
            )
        else:
            pgn_eval = _pgn_eval_cp(comment)
            if pgn_eval is not None:
                eval_after = pgn_eval if my_color == chess.WHITE else -pgn_eval

        if my_turn and eval_before is not None and eval_after is not None:
            report.my_moves += 1
            if eval_before >= settings.winning_cp:
                report.reached_winning = True
            cp_loss = eval_before - eval_after
            wp_loss = win_percent(eval_before) - win_percent(eval_after)
            severity = None
            if wp_loss >= settings.blunder_wp:
                severity = "blunder"
            elif wp_loss >= settings.mistake_wp:
                severity = "mistake"
            elif wp_loss >= settings.inaccuracy_wp:
                severity = "inaccuracy"
            if severity:
                best_san = ""
                if engine is not None:
                    best = engine.play(board, limit).move
                    if best is not None:
                        best_san = board.san(best)
                report.issues.append(
                    MoveIssue(
                        ply=board.ply(),
                        move_number=board.fullmove_number,
                        san=board.san(move),
                        best_san=best_san,
                        severity=severity,
                        cp_loss=min(cp_loss, MATE_CP),
                        wp_loss=round(wp_loss, 1),
                        fen_before=board.fen(),
                        seconds=move_times[-1] if move_times else None,
                        trapped_piece=_is_trapped_piece_blunder(board, move),
                    )
                )
        elif my_turn:
            report.my_moves += 1

        prev_eval = eval_after
        board.push(move)

    if move_times:
        report.avg_seconds = sum(move_times) / len(move_times)
    report.time_left_s = last_clock
    if report.reached_winning:
        report.converted = row["result"] == "win"
    return report


def report_to_row(report: GameReport) -> dict[str, Any]:
    dev = report.deviation
    return {
        "game_id": report.game_id,
        "analyzed_at": datetime.now(UTC).isoformat(),
        "engine": "stockfish",
        "inaccuracies": report.count("inaccuracy"),
        "mistakes": report.count("mistake"),
        "blunders": report.count("blunder"),
        "my_moves": report.my_moves,
        "avg_seconds": report.avg_seconds,
        "time_left_s": report.time_left_s,
        "reached_winning": int(report.reached_winning),
        "converted": None if report.converted is None else int(report.converted),
        "rep_exit_ply": dev.ply if dev and dev.by_me else None,
        "rep_chapter": dev.chapter if dev and dev.by_me else None,
        "rep_expected": dev.expected if dev and dev.by_me else None,
        "rep_played": dev.played if dev and dev.by_me else None,
        "details": {
            "issues": [
                {
                    "move_number": i.move_number,
                    "san": i.san,
                    "best_san": i.best_san,
                    "severity": i.severity,
                    "cp_loss": i.cp_loss,
                    "wp_loss": i.wp_loss,
                    "fen_before": i.fen_before,
                    "seconds": i.seconds,
                    "trapped_piece": i.trapped_piece,
                }
                for i in report.issues
            ]
        },
    }


def open_engine(path: Path) -> chess.engine.SimpleEngine:
    engine = chess.engine.SimpleEngine.popen_uci(str(path))
    engine.configure({"Threads": 2, "Hash": 256})
    return engine
