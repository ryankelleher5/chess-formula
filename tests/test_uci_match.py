from __future__ import annotations

import chess
import pytest

from chess_formula.uci_match import (
    load_opening_suite,
    play_uci_game,
    score_to_elo,
    summarize_match,
)


def test_frozen_opening_suite_is_legal_and_paired() -> None:
    openings = load_opening_suite("configs/uci-pilot-openings.json")
    assert len(openings) == 20
    assert all(len(opening["moves"]) == 8 for opening in openings)


def test_score_to_elo_has_expected_orientation() -> None:
    assert score_to_elo(0.5, 40) == pytest.approx(0.0)
    assert score_to_elo(0.75, 40) > 0
    assert score_to_elo(0.25, 40) < 0


def test_match_summary_resamples_opening_pairs() -> None:
    games = []
    for opening, scores in {"a": [1.0, 0.5], "b": [0.0, 0.5]}.items():
        for score in scores:
            games.append(
                {
                    "opening_id": opening,
                    "candidate_score": score,
                    "termination": "checkmate",
                    "failure_actor": None,
                    "failure_kind": None,
                    "candidate_telemetry": {
                        "moves": 2,
                        "total_time_ms": 20.0,
                        "reported_nodes": 10,
                    },
                    "opponent_telemetry": {
                        "moves": 2,
                        "total_time_ms": 10.0,
                        "reported_nodes": 4,
                    },
                }
            )
    summary = summarize_match(games, repeats=100, seed=7)
    assert summary["wins"] == 1
    assert summary["draws"] == 2
    assert summary["losses"] == 1
    assert summary["score_rate"] == 0.5
    assert summary["candidate_resources"]["mean_time_ms_per_move"] == 10.0


def test_unscored_short_uci_game_has_no_illegal_move() -> None:
    settings = {
        "candidate": "searched-3",
        "engine_timeout_seconds": 5.0,
        "maximum_total_plies": 12,
        "draw_claims": True,
        "policy_go_nodes": 1,
        "stockfish_threads": 1,
        "stockfish_hash_mb": 16,
    }
    opening = {
        "id": "smoke",
        "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6"],
    }
    opponent = {"name": "locked-3", "type": "policy", "policy": "locked-3"}
    record, _ = play_uci_game(
        opening,
        opponent,
        chess.WHITE,
        "/opt/homebrew/bin/stockfish",
        settings,
    )
    assert record["failure_actor"] is None
    assert record["total_plies"] == 12
