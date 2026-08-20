"""Interfaz de linea de comandos: sync, analyze, report, puzzles."""

from __future__ import annotations

import argparse
import json
import sys

from . import analyze as analysis_mod
from . import engine as engine_mod
from . import fetch, metrics, puzzles, store
from .config import PUZZLES_PATH, load_config


def cmd_sync(args: argparse.Namespace) -> int:
    config = load_config()
    added = 0
    with store.connect() as conn:
        for label, loader in (
            ("Lichess", lambda: fetch.fetch_lichess(config.lichess_user, args.max)),
            ("chess.com", lambda: fetch.fetch_chesscom(config.chesscom_user, args.months)),
        ):
            try:
                rows = loader()
            except Exception as exc:  # la API puede fallar o la cuenta no existir
                print(f"  {label}: error -> {exc}")
                continue
            new = sum(store.upsert_game(conn, row) for row in rows)
            added += new
            print(f"  {label}: {len(rows)} partidas vistas, {new} nuevas")
    print(f"Total nuevas: {added}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    config = load_config()
    engine_path = engine_mod.find_engine()
    if engine_path is None:
        if args.no_download:
            print("Sin motor. Se usaran las evaluaciones incluidas en el PGN de Lichess.")
        else:
            engine_path = engine_mod.ensure_engine()

    engine = analysis_mod.open_engine(engine_path) if engine_path else None
    try:
        with store.connect() as conn:
            pending = store.unanalyzed_games(conn, config.time_classes)
            if args.limit:
                pending = pending[: args.limit]
            print(f"Partidas por analizar: {len(pending)}")
            for index, row in enumerate(pending, start=1):
                data = dict(row)
                report = analysis_mod.analyze_game(
                    data, engine, config.analysis, config.analysis.repertoire_depth
                )
                store.save_analysis(conn, analysis_mod.report_to_row(report))
                conn.commit()  # commit por partida: una corrida larga se puede interrumpir
                print(
                    f"  [{index}/{len(pending)}] {data['id']}"
                    f" errores={report.count('blunder')}+{report.count('mistake')}",
                    flush=True,
                )
    finally:
        if engine is not None:
            engine.quit()
    return 0


def cmd_repertoire(_: argparse.Namespace) -> int:
    """Recalcula las fugas de repertorio tras editar repertoire.pgn, sin usar el motor."""
    config = load_config()
    with store.connect() as conn:
        rows = store.analyzed_games(conn)
        leaks = 0
        for row in rows:
            dev = analysis_mod.deviation_for(dict(row), config.analysis.repertoire_depth)
            store.update_repertoire(conn, row["id"], dev)
            leaks += bool(dev and dev.by_me)
    print(f"{len(rows)} partidas revisadas, {leaks} fuera del repertorio")
    return 0


def cmd_study(args: argparse.Namespace) -> int:
    """Descarga un estudio publico de Lichess a la carpeta studies/."""
    from . import studies

    try:
        destino = studies.import_lichess_study(args.url, args.name)
    except Exception as exc:
        print(f"No se pudo importar: {exc}")
        return 1
    chapters = studies.load_studies()
    total = sum(len(c) for c in chapters.values())
    print(f"Guardado en {destino}")
    print(f"Estudios disponibles: {len(chapters)} archivos, {total} capitulos")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    """Calcula con el motor las lineas que justifican cada jugada.

    Se guardan en la base porque la nube no tiene Stockfish: el entrenador solo
    lee lo que esta PC dejo calculado.
    """
    import chess

    config = load_config()
    engine_path = engine_mod.find_engine() or engine_mod.ensure_engine()
    engine = analysis_mod.open_engine(engine_path)
    hechas = 0
    try:
        with store.connect() as conn:
            filas = conn.execute(
                "SELECT game_id, details FROM analysis"
            ).fetchall()
            for indice, fila in enumerate(filas, start=1):
                datos = json.loads(fila["details"])
                issues = datos.get("issues", [])
                cambiado = False
                for issue in issues:
                    if issue.get("pv_mejor") is not None and not args.force:
                        continue
                    board = chess.Board(issue["fen_before"])
                    issue["pv_mejor"] = analysis_mod.variante(board, engine, config.analysis)
                    tras = board.copy()
                    try:
                        tras.push_san(issue["san"])
                        issue["pv_refuta"] = analysis_mod.variante(
                            tras, engine, config.analysis
                        )
                    except ValueError:
                        issue["pv_refuta"] = []
                    cambiado = True
                    hechas += 1
                if cambiado:
                    conn.execute(
                        "UPDATE analysis SET details = ? WHERE game_id = ?",
                        (json.dumps(datos, ensure_ascii=False), fila["game_id"]),
                    )
                    conn.commit()
                if indice % 10 == 0:
                    print(f"  {indice}/{len(filas)} partidas · {hechas} explicaciones",
                          flush=True)
    finally:
        engine.quit()
    print(f"Listo: {hechas} posiciones con linea calculada")
    return 0


def cmd_report(_: argparse.Namespace) -> int:
    config = load_config()
    with store.connect() as conn:
        total, done = store.counts(conn)
        frame = metrics.load_frame(conn, config)

    print(f"\nPartidas: {total} descargadas, {done} analizadas\n")
    print(f"{'METRICA':<34}{'ACTUAL':>10}{'META':>10}   ESTADO")
    print("-" * 70)
    for metric in metrics.compute(frame, config):
        value = "-" if metric.value is None else (
            f"{metric.value * 100:.0f}%" if metric.unit == "%" else f"{metric.value:.1f}{metric.unit}"
        )
        target = (
            f"{metric.target * 100:.0f}%" if metric.unit == "%"
            else f"{metric.target:.1f}{metric.unit}"
        )
        mark = {"ok": "OK", "cerca": "CERCA", "lejos": "LEJOS"}.get(metric.status, "?")
        print(f"{metric.label:<34}{value:>10}{target:>10}   {mark}")

    leaks = metrics.repertoire_leaks(frame)
    if not leaks.empty:
        print("\nFUGAS DE REPERTORIO (las 5 peores)")
        print("-" * 70)
        for leak in leaks.head(5).itertuples():
            print(
                f"  {leak.rep_chapter}: en la jugada {leak.jugada} jugaste"
                f" {leak.rep_played}, deberia ser {leak.rep_expected}"
                f"  ({leak.veces}x, {leak.derrotas} derrotas)"
            )

    print("\nQUE ENTRENAR HOY")
    print("-" * 70)
    for index, task in enumerate(metrics.today_plan(frame, config), start=1):
        print(f"  {index}. {task}")
    return 0


def cmd_puzzles(_: argparse.Namespace) -> int:
    config = load_config()
    with store.connect() as conn:
        frame = metrics.load_frame(conn, config)
        issues = metrics.issues_frame(frame)
    count = puzzles.export_puzzles(issues)
    print(f"{count} posiciones escritas en {PUZZLES_PATH}")
    print("Importalas en un Lichess Study para entrenar con tus propios errores.")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    return cmd_sync(args) or cmd_analyze(args) or cmd_report(args) or cmd_puzzles(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chesscoach", description="Panel de progreso de ajedrez")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync", help="descargar partidas nuevas")
    sync.add_argument("--max", type=int, default=200, help="partidas de Lichess a traer")
    sync.add_argument("--months", type=int, default=6, help="meses de chess.com a traer")
    sync.set_defaults(func=cmd_sync)

    analyze = subparsers.add_parser("analyze", help="analizar con Stockfish")
    analyze.add_argument("--limit", type=int, default=15, help="maximo de partidas por corrida")
    analyze.add_argument("--no-download", action="store_true", help="no descargar Stockfish")
    analyze.set_defaults(func=cmd_analyze)

    subparsers.add_parser(
        "repertoire", help="recalcular fugas tras editar repertoire.pgn"
    ).set_defaults(func=cmd_repertoire)

    study = subparsers.add_parser("study", help="importar un estudio publico de Lichess")
    study.add_argument("url", help="URL o id del estudio (ej. lichess.org/study/abcd1234)")
    study.add_argument("--name", help="nombre del archivo en studies/")
    study.set_defaults(func=cmd_study)

    explain = subparsers.add_parser(
        "explain", help="calcular las lineas que explican cada error"
    )
    explain.add_argument("--force", action="store_true", help="recalcular las ya hechas")
    explain.set_defaults(func=cmd_explain)

    subparsers.add_parser("report", help="tarjeta de progreso en consola").set_defaults(
        func=cmd_report
    )
    subparsers.add_parser("puzzles", help="exportar PGN con mis errores").set_defaults(
        func=cmd_puzzles
    )

    run_all = subparsers.add_parser("all", help="sync + analyze + report + puzzles")
    run_all.add_argument("--max", type=int, default=200)
    run_all.add_argument("--months", type=int, default=6)
    run_all.add_argument("--limit", type=int, default=15)
    run_all.add_argument("--no-download", action="store_true")
    run_all.set_defaults(func=cmd_all)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
