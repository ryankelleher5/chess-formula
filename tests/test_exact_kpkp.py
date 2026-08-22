from __future__ import annotations

import chess
import numpy as np

from chess_formula.exact_kpkp import (
    canonical_state_key,
    connected_fold_assignments,
    has_reachable_ep_state,
    matches_domain,
    transform_board,
    transform_move,
    transition_feature_names,
    transition_features,
    transition_isolation_audit,
    weighted_estimands,
)


def _kpkp_board() -> chess.Board:
    return chess.Board("8/7k/3p4/8/4P3/8/K7/8 w - - 0 1")


def test_reachable_en_passant_state_is_preserved_by_symmetry() -> None:
    board = chess.Board("8/7k/8/3pP3/8/8/K7/8 w - d6 0 1")
    assert board.is_valid()
    assert has_reachable_ep_state(board)
    for transform in range(4):
        transformed = transform_board(board, transform)
        assert transformed.is_valid()
        assert has_reachable_ep_state(transformed)
        assert canonical_state_key(transformed) == canonical_state_key(board)


def test_transition_features_and_ordering_are_symmetry_equivariant() -> None:
    board = _kpkp_board()
    move = chess.Move.from_uci("e4e5")
    expected = transition_features(board, move)
    for transform in range(4):
        transformed_board = transform_board(board, transform)
        transformed_move = transform_move(move, transform)
        assert transformed_move in transformed_board.legal_moves
        np.testing.assert_array_equal(
            transition_features(transformed_board, transformed_move), expected
        )


def test_representation_supports_variable_same_color_pawns() -> None:
    board = chess.Board("8/7k/8/8/3PP3/8/K7/8 w - - 0 1")
    assert board.is_valid()
    assert matches_domain(board, "KPPvK")
    move = chess.Move.from_uci("d4d5")
    features = transition_features(board, move)
    assert len(features) == len(transition_feature_names())
    assert np.isfinite(features).all()


def test_transition_isolation_detects_successor_leakage() -> None:
    development = _kpkp_board()
    successor = development.copy(stack=False)
    successor.push(chess.Move.from_uci("e4e5"))
    audit = transition_isolation_audit(
        {"development": [development], "selection": [successor], "confirmation": []}
    )
    assert audit["exact_root_overlap"] == 0
    assert audit["symmetry_class_root_overlap"] == 0
    assert audit["directed_predecessor_successor_overlap"] == 1
    assert audit["passed"] is False


def test_connected_roots_are_assigned_to_same_fold() -> None:
    first = _kpkp_board()
    second = first.copy(stack=False)
    second.push(chess.Move.from_uci("e4e5"))
    assignments = connected_fold_assignments([first, second], seed=7, folds=5)
    assert len(set(assignments.values())) == 1


def test_weighted_estimands_keep_pooled_and_context_means_distinct() -> None:
    rows = [
        {"stratum": "white:noep", "retained": 1, "legal": 2},
        {"stratum": "black:ep", "retained": 1, "legal": 10},
    ]
    result = weighted_estimands(
        rows, {"white:noep": 90, "black:ep": 10}
    )
    assert result["population_pooled_retained_fraction"] == 100 / 280
    assert result["population_mean_context_retained_fraction"] == 0.46
    assert result["stratum_balanced_mean_context_retained_fraction"] == 0.3
