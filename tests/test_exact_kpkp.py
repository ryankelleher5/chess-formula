from __future__ import annotations

import chess
import numpy as np

from chess_formula.config import load_config
from chess_formula.exact_kpkp import (
    audit_kpkp_tablebase_manifest,
    canonical_state_key,
    connected_fold_assignments,
    enforce_kpkp_probe_partition,
    has_reachable_ep_state,
    matches_domain,
    nested_fold_assignments,
    partition_for_key,
    primitive_geometry_strata,
    probe_kpkp_development_labels,
    random_move_ordering,
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


def test_behaviorally_irrelevant_ep_marker_collapses_before_partitioning() -> None:
    with_marker = chess.Board("7k/8/7p/8/P7/8/8/K7 b - a3 0 1")
    without_marker = chess.Board("7k/8/7p/8/P7/8/8/K7 b - - 0 1")
    assert has_reachable_ep_state(with_marker)
    assert not with_marker.has_legal_en_passant()
    assert set(with_marker.legal_moves) == set(without_marker.legal_moves)
    assert canonical_state_key(with_marker) == canonical_state_key(without_marker)
    assert partition_for_key(canonical_state_key(with_marker), 20260908) == partition_for_key(
        canonical_state_key(without_marker), 20260908
    )
    for move in with_marker.legal_moves:
        np.testing.assert_array_equal(
            transition_features(with_marker, move),
            transition_features(without_marker, move),
        )


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


def test_transition_symmetry_covers_ep_promotion_capture_black_and_kppvk() -> None:
    cases = (
        ("8/7k/8/3pP3/8/8/K7/8 w - d6 0 1", "e5d6"),
        ("7k/P7/8/8/8/8/7p/K7 w - - 0 1", "a7a8q"),
        ("7k/8/3p4/4P3/8/8/8/K7 w - - 0 1", "e5d6"),
        ("8/7k/3p4/8/4P3/8/K7/8 b - - 0 1", "d6d5"),
        ("8/7k/8/8/3PP3/8/K7/8 w - - 0 1", "d4d5"),
    )
    for fen, move_uci in cases:
        board = chess.Board(fen)
        move = chess.Move.from_uci(move_uci)
        assert move in board.legal_moves
        expected = transition_features(board, move)
        for transform in range(4):
            transformed_board = transform_board(board, transform)
            transformed_move = transform_move(move, transform)
            assert transformed_move in transformed_board.legal_moves
            np.testing.assert_array_equal(
                transition_features(transformed_board, transformed_move), expected
            )


def test_random_order_and_primitive_strata_are_frozen_and_symmetry_equivariant() -> None:
    board = chess.Board("8/7k/8/3pP3/8/8/K7/8 w - d6 0 1")
    ordered = random_move_ordering(board, seed=20260908, repeat=3)
    assert ordered == random_move_ordering(board, seed=20260908, repeat=3)
    transformed = transform_board(board, 1)
    transformed_order = random_move_ordering(transformed, seed=20260908, repeat=3)
    assert [transform_move(move, 1) for move in ordered] == transformed_order
    ep_move = chess.Move.from_uci("e5d6")
    strata = primitive_geometry_strata(board, ep_move)
    assert strata["legal_en_passant"] == "true"
    assert "legal-en-passant" in strata["move_kind"]


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


def test_nested_folds_exclude_outer_validation_and_group_transitions() -> None:
    first = _kpkp_board()
    second = first.copy(stack=False)
    second.push(chess.Move.from_uci("e4e5"))
    outer, inner = nested_fold_assignments([first, second], seed=7, outer_folds=5, inner_folds=4)
    assert len(set(outer.values())) == 1
    held_out = next(iter(outer.values()))
    assert not inner[held_out]


def test_weighted_estimands_keep_pooled_and_context_means_distinct() -> None:
    rows = [
        {"stratum": "white:noep", "retained": 1, "legal": 2},
        {"stratum": "black:ep", "retained": 1, "legal": 10},
    ]
    result = weighted_estimands(rows, {"white:noep": 90, "black:ep": 10})
    assert result["population_pooled_retained_fraction"] == 100 / 280
    assert result["population_mean_context_retained_fraction"] == 0.46
    assert result["stratum_balanced_mean_context_retained_fraction"] == 0.3


def test_review_manifest_is_metadata_only_and_probe_guard_fails_closed() -> None:
    config = load_config("configs/experiment-021-kpkp-review.json")
    audit = audit_kpkp_tablebase_manifest(config)
    assert audit["files"] == 20
    assert audit["tablebase_files_opened"] == 0
    assert audit["outcomes_probed"] == 0
    with np.testing.assert_raises(PermissionError):
        enforce_kpkp_probe_partition(config, "development")
    with np.testing.assert_raises(PermissionError):
        probe_kpkp_development_labels(
            config,
            directory="/definitely/not/a/tablebase/directory",
            partition="development",
        )
    authorized = {**config, "experiment_021_kpkp_review": {**config["experiment_021_kpkp_review"]}}
    authorized["experiment_021_kpkp_review"]["development_outcomes_authorized"] = True
    authorized["experiment_021_kpkp_review"]["tablebase_probes_authorized"] = True
    with np.testing.assert_raises(PermissionError):
        enforce_kpkp_probe_partition(authorized, "selection")
    with np.testing.assert_raises(PermissionError):
        enforce_kpkp_probe_partition(authorized, "confirmation")
    enforce_kpkp_probe_partition(authorized, "development")
