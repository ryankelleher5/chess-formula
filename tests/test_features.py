from __future__ import annotations

import chess

from chess_formula.features import extract_features, feature_matrix


def test_starting_position_features_are_color_symmetric() -> None:
    features = extract_features(chess.Board())
    assert features["material"] == 0
    assert features["center_control"] == 0
    assert features["bishop_pair"] == 0
    assert features["tempo"] == 1


def test_material_uses_white_perspective() -> None:
    board = chess.Board("4k3/8/8/8/8/8/3Q4/4K3 w - - 0 1")
    assert extract_features(board)["material"] == 9.0
    black_queen = chess.Board("4k3/3q4/8/8/8/8/8/4K3 b - - 0 1")
    assert extract_features(black_queen)["material"] == -9.0


def test_feature_matrix_is_stable() -> None:
    matrix, names = feature_matrix([chess.Board().fen(), chess.Board().fen()])
    assert matrix.shape == (2, 16)
    assert names[0] == "material"
    assert names[-1] == "game_phase"
