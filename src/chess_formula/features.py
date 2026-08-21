from __future__ import annotations

from collections import Counter

import chess
import numpy as np

PIECE_VALUES = {
    chess.PAWN: 1.0,
    chess.KNIGHT: 3.2,
    chess.BISHOP: 3.3,
    chess.ROOK: 5.0,
    chess.QUEEN: 9.0,
    chess.KING: 0.0,
}
CENTER = (chess.D4, chess.E4, chess.D5, chess.E5)


def _difference(board: chess.Board, fn) -> float:
    return float(fn(board, chess.WHITE) - fn(board, chess.BLACK))


def _material(board: chess.Board, color: chess.Color) -> float:
    return sum(len(board.pieces(piece, color)) * value for piece, value in PIECE_VALUES.items())


def _mobility(board: chess.Board, color: chess.Color) -> int:
    copy = board.copy(stack=False)
    copy.turn = color
    return copy.legal_moves.count()


def _center_control(board: chess.Board, color: chess.Color) -> int:
    return sum(len(board.attackers(color, square)) for square in CENTER)


def _development(board: chess.Board, color: chess.Color) -> int:
    homes = (
        (chess.B1, chess.G1, chess.C1, chess.F1)
        if color == chess.WHITE
        else (chess.B8, chess.G8, chess.C8, chess.F8)
    )
    original = (chess.KNIGHT, chess.KNIGHT, chess.BISHOP, chess.BISHOP)
    return sum(
        board.piece_at(square) != chess.Piece(kind, color)
        for square, kind in zip(homes, original, strict=True)
    )


def _space(board: chess.Board, color: chess.Color) -> int:
    ranks = range(4, 8) if color == chess.WHITE else range(0, 4)
    return sum(
        board.is_attacked_by(color, chess.square(file, rank)) for rank in ranks for file in range(8)
    )


def _king_safety(board: chess.Board, color: chess.Color) -> float:
    king = board.king(color)
    if king is None:
        return 0.0
    direction = 1 if color == chess.WHITE else -1
    shield_rank = chess.square_rank(king) + direction
    shield = 0
    if 0 <= shield_rank <= 7:
        for file in range(
            max(0, chess.square_file(king) - 1), min(7, chess.square_file(king) + 1) + 1
        ):
            if board.piece_at(chess.square(file, shield_rank)) == chess.Piece(chess.PAWN, color):
                shield += 1
    castled = 1.0 if chess.square_file(king) in (2, 6) else 0.0
    enemy = not color
    ring_pressure = sum(
        board.is_attacked_by(enemy, square)
        for square in chess.SquareSet(chess.BB_KING_ATTACKS[king] | chess.BB_SQUARES[king])
    )
    return shield + castled - 0.5 * ring_pressure


def _passed_pawns(board: chess.Board, color: chess.Color) -> int:
    enemy_pawns = board.pieces(chess.PAWN, not color)
    count = 0
    for square in board.pieces(chess.PAWN, color):
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        forward = range(rank + 1, 8) if color == chess.WHITE else range(rank - 1, -1, -1)
        blockers = {
            chess.square(adj_file, adj_rank)
            for adj_file in range(max(0, file - 1), min(7, file + 1) + 1)
            for adj_rank in forward
        }
        count += not any(square in enemy_pawns for square in blockers)
    return count


def _isolated_pawns(board: chess.Board, color: chess.Color) -> int:
    files = Counter(chess.square_file(square) for square in board.pieces(chess.PAWN, color))
    return sum(
        amount
        for file, amount in files.items()
        if files.get(file - 1, 0) == 0 and files.get(file + 1, 0) == 0
    )


def _doubled_pawns(board: chess.Board, color: chess.Color) -> int:
    files = Counter(chess.square_file(square) for square in board.pieces(chess.PAWN, color))
    return sum(max(0, amount - 1) for amount in files.values())


def _connected_pawns(board: chess.Board, color: chess.Color) -> int:
    pawns = board.pieces(chess.PAWN, color)
    connected = 0
    for square in pawns:
        file, rank = chess.square_file(square), chess.square_rank(square)
        neighbors = [
            chess.square(other_file, other_rank)
            for other_file in (file - 1, file + 1)
            if 0 <= other_file <= 7
            for other_rank in (rank - 1, rank, rank + 1)
            if 0 <= other_rank <= 7
        ]
        connected += any(neighbor in pawns for neighbor in neighbors)
    return connected


def _bishop_pair(board: chess.Board, color: chess.Color) -> int:
    return int(len(board.pieces(chess.BISHOP, color)) >= 2)


def _rooks_on_open_files(board: chess.Board, color: chess.Color) -> int:
    all_pawns = board.pieces(chess.PAWN, chess.WHITE) | board.pieces(chess.PAWN, chess.BLACK)
    return sum(
        not any(chess.square(file, rank) in all_pawns for rank in range(8))
        for file in (chess.square_file(square) for square in board.pieces(chess.ROOK, color))
    )


def _piece_activity(board: chess.Board, color: chess.Color) -> int:
    return sum(
        len(board.attacks(square))
        for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        for square in board.pieces(piece_type, color)
    )


def _threat_pressure(board: chess.Board, color: chess.Color) -> float:
    pressure = 0.0
    for square, piece in board.piece_map().items():
        if piece.color != color and board.is_attacked_by(color, square):
            pressure += PIECE_VALUES[piece.piece_type]
    return pressure


def extract_features(board: chess.Board) -> dict[str, float]:
    if not board.is_valid():
        raise ValueError(f"Cannot extract features from invalid position: {board.fen()}")
    nonpawn = sum(
        len(board.pieces(piece, color)) * PIECE_VALUES[piece]
        for color in chess.COLORS
        for piece in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
    )
    return {
        "material": _difference(board, _material),
        "mobility": _difference(board, _mobility),
        "center_control": _difference(board, _center_control),
        "development": _difference(board, _development),
        "space": _difference(board, _space),
        "king_safety": _difference(board, _king_safety),
        "passed_pawns": _difference(board, _passed_pawns),
        "isolated_pawns": _difference(board, _isolated_pawns),
        "doubled_pawns": _difference(board, _doubled_pawns),
        "connected_pawns": _difference(board, _connected_pawns),
        "bishop_pair": _difference(board, _bishop_pair),
        "rooks_open_files": _difference(board, _rooks_on_open_files),
        "piece_activity": _difference(board, _piece_activity),
        "threat_pressure": _difference(board, _threat_pressure),
        "tempo": 1.0 if board.turn == chess.WHITE else -1.0,
        "game_phase": float(nonpawn / 62.0),
    }


def feature_matrix(fens: list[str], names: list[str] | None = None) -> tuple[np.ndarray, list[str]]:
    rows = [extract_features(chess.Board(fen)) for fen in fens]
    feature_names = names or list(rows[0])
    return np.asarray(
        [[row[name] for name in feature_names] for row in rows], dtype=float
    ), feature_names
