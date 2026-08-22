from __future__ import annotations

import chess

from chess_formula.loss_audit import (
    classify_refutation,
    extract_candidate_loss_positions,
    move_kind,
    select_first_error,
)


def test_extracts_only_candidate_turns_from_target_losses() -> None:
    game = {
        "opponent": "stockfish-100n",
        "candidate_score": 0.0,
        "candidate_color": "white",
        "opening_id": "test",
        "moves_uci": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6"],
    }
    settings = {"opponent": "stockfish-100n", "opening_plies": 2}
    rows = extract_candidate_loss_positions([game], settings)
    assert [row["played_move"] for row in rows] == ["g1f3", "f1b5"]
    assert all(row["candidate_color"] == "white" for row in rows)


def test_move_kind_distinguishes_quiet_check_and_pawn_capture() -> None:
    board = chess.Board()
    assert move_kind(board, chess.Move.from_uci("g1f3")) == "quiet"
    board = chess.Board("7k/8/8/8/8/8/5Q2/6K1 w - - 0 1")
    assert move_kind(board, chess.Move.from_uci("f2f8")) == "check"
    board = chess.Board("7k/8/8/8/3p4/4P3/8/6K1 w - - 0 1")
    assert move_kind(board, chess.Move.from_uci("e3d4")) == "pawn-capture"


def test_refutation_classifies_quiet_reply_outside_forcing_vocabulary() -> None:
    board = chess.Board()
    result = classify_refutation(board, ["e2e4", "e7e5", "g1f3"])
    assert result["reply_class"] == "excluded-quiet-reply"
    assert result["reply_visible"] is False


def test_first_error_prefers_persistent_major_swing() -> None:
    rows = [
        {
            "ply": 10,
            "regret_cp": 180.0,
            "post_move_candidate_cp": -100.0,
            "pre_move_candidate_cp": 0.0,
        },
        {
            "ply": 12,
            "regret_cp": 200.0,
            "post_move_candidate_cp": -350.0,
            "pre_move_candidate_cp": -50.0,
        },
        {
            "ply": 14,
            "regret_cp": 20.0,
            "post_move_candidate_cp": -400.0,
            "pre_move_candidate_cp": -375.0,
        },
    ]
    selected = select_first_error(
        rows, major_regret_cp=150.0, persistent_disadvantage_cp=300.0
    )
    assert selected["ply"] == 12
    assert selected["selection_reason"] == "first-persistent-major-error"
