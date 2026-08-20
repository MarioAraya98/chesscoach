"""Explicaciones de entrenador para cada posicion del entrenador.

Todo lo que se afirma sale de hechos comprobables sobre el tablero (capturas,
jaques, piezas colgadas, ataques dobles) o de la linea principal del motor. No se
inventan valoraciones: si un hecho no se puede verificar, no se menciona.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

NOMBRE = {
    chess.PAWN: "peón",
    chess.KNIGHT: "caballo",
    chess.BISHOP: "alfil",
    chess.ROOK: "torre",
    chess.QUEEN: "dama",
    chess.KING: "rey",
}
VALOR = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
VALIOSAS = (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)


@dataclass(frozen=True)
class Explicacion:
    por_que_mejor: str
    que_paso: str
    linea_mejor: str
    refutacion: str


def _pieza_capturada(board: chess.Board, jugada: chess.Move) -> str | None:
    if board.is_en_passant(jugada):
        return NOMBRE[chess.PAWN]
    objetivo = board.piece_at(jugada.to_square)
    return NOMBRE[objetivo.piece_type] if objetivo else None


def _amenazas_tras(board: chess.Board, jugada: chess.Move) -> list[str]:
    """Piezas rivales valiosas que quedan atacadas por la pieza recien movida."""
    despues = board.copy()
    despues.push(jugada)
    rival = not board.turn
    atacadas = []
    for casilla in despues.attacks(jugada.to_square):
        pieza = despues.piece_at(casilla)
        if pieza and pieza.color == rival and pieza.piece_type in VALIOSAS:
            atacadas.append(NOMBRE[pieza.piece_type])
    return atacadas


def _cuelga(board: chess.Board, jugada: chess.Move) -> str | None:
    """Si tras la jugada la pieza movida queda ganable por el rival.

    python-chess 1.11 no expone evaluacion de intercambios, asi que se compara
    atacantes contra defensores: sin defensa, o con un atacante mas barato que
    la pieza, el rival gana material.
    """
    movida = board.piece_at(jugada.from_square)
    if movida is None or movida.piece_type == chess.KING:
        return None

    despues = board.copy()
    despues.push(jugada)
    casilla = jugada.to_square
    atacantes = despues.attackers(not board.turn, casilla)
    if not atacantes:
        return None

    defensores = despues.attackers(board.turn, casilla)
    if not defensores:
        return NOMBRE[movida.piece_type]

    mas_barato = min(
        VALOR.get(despues.piece_at(c).piece_type, 99) for c in atacantes
    )
    if mas_barato < VALOR.get(movida.piece_type, 0):
        return NOMBRE[movida.piece_type]
    return None


def _estaba_amenazada(board: chess.Board, jugada: chess.Move) -> str | None:
    """Si la pieza movida estaba atacada y con la jugada se pone a salvo."""
    pieza = board.piece_at(jugada.from_square)
    if pieza is None or not board.is_attacked_by(not board.turn, jugada.from_square):
        return None
    if _cuelga(board, jugada):
        return None
    return NOMBRE[pieza.piece_type]


def _motivos(board: chess.Board, jugada: chess.Move) -> list[str]:
    despues = board.copy()
    despues.push(jugada)
    if despues.is_checkmate():
        return ["da mate"]

    motivos = []
    if board.gives_check(jugada):
        motivos.append("da jaque")
    if (comida := _pieza_capturada(board, jugada)):
        motivos.append(f"captura un {comida}")
    if (salvada := _estaba_amenazada(board, jugada)):
        motivos.append(f"pone a salvo tu {salvada}, que estaba atacado")
    atacadas = _amenazas_tras(board, jugada)
    if len(atacadas) >= 2:
        motivos.append(f"ataca a la vez {atacadas[0]} y {atacadas[1]}")
    elif atacadas:
        motivos.append(f"ataca su {atacadas[0]}")
    return motivos


def _linea(board: chess.Board, jugadas: list[str]) -> str:
    """Formatea una lista de SAN como '21...Bd7 22.Nxd7 Qxd7'."""
    if not jugadas:
        return ""
    tablero = board.copy()
    partes = []
    for san in jugadas:
        try:
            jugada = tablero.parse_san(san)
        except ValueError:
            break
        numero = tablero.fullmove_number
        prefijo = f"{numero}." if tablero.turn == chess.WHITE else f"{numero}..."
        partes.append(f"{prefijo}{san}")
        tablero.push(jugada)
    return " ".join(partes)


def explicar(
    fen: str,
    jugada_mejor: str,
    jugada_tuya: str,
    pv_mejor: list[str] | None = None,
    pv_refutacion: list[str] | None = None,
) -> Explicacion:
    """Arma la explicacion de por que una jugada es mejor que la otra."""
    board = chess.Board(fen)
    try:
        mejor = board.parse_san(jugada_mejor)
    except ValueError:
        return Explicacion("", "", "", "")

    motivos = _motivos(board, mejor)
    por_que = (
        f"**{jugada_mejor}** es la mejor porque " + ", y ".join(motivos) + "."
        if motivos
        else f"**{jugada_mejor}** es la mejor: mejora tu posición sin dar contrajuego."
    )

    que_paso = ""
    if jugada_tuya and jugada_tuya != jugada_mejor:
        try:
            tuya = board.parse_san(jugada_tuya)
        except ValueError:
            tuya = None
        if tuya is not None:
            if (colgada := _cuelga(board, tuya)):
                que_paso = f"Con **{jugada_tuya}** tu {colgada} queda capturable."
            elif (perdida := _estaba_amenazada(board, mejor)) and mejor.from_square != tuya.from_square:
                que_paso = (
                    f"**{jugada_tuya}** ignora que tu {perdida} estaba atacado."
                )
            else:
                que_paso = (
                    f"**{jugada_tuya}** deja escapar la ventaja: mirá la diferencia "
                    f"con **{jugada_mejor}** en las líneas de abajo."
                )

    return Explicacion(
        por_que_mejor=por_que,
        que_paso=que_paso,
        linea_mejor=_linea(board, pv_mejor or []),
        refutacion=_linea(board, pv_refutacion or []),
    )
