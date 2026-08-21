from __future__ import annotations

import chess

from chess_formula.march import selective_minimax
from chess_formula.search_frontier import (
    choose_frontier_move,
    frontier_moves,
    scheduled_minimax,
    select_frontier_candidate,
)


def test_forcing_schedule_reproduces_accepted_minimax() -> None:
    board = chess.Board("7k/8/8/8/8/8/5Q2/6K1 w - - 0 1")

    def evaluator(position: chess.Board) -> float:
        return float(len(position.move_stack))

    accepted, accepted_expanded = selective_minimax(
        board,
        evaluator,
        depth_plies=2,
        maximum_expanded_children=128,
        terminal_cp=2000,
    )
    frontier, frontier_expanded, exhausted = scheduled_minimax(
        board,
        evaluator,
        selector_schedule=["forcing", "forcing"],
        maximum_expanded_children=128,
        terminal_cp=2000,
    )
    assert frontier == accepted
    assert frontier_expanded == accepted_expanded
    assert exhausted is False


def test_all_captures_adds_pawn_capture_but_not_quiet_move() -> None:
    board = chess.Board("7k/8/8/8/3p4/4P3/8/6K1 w - - 0 1")
    pawn_capture = chess.Move.from_uci("e3d4")
    quiet = chess.Move.from_uci("g1f2")
    assert pawn_capture not in frontier_moves(board, "forcing")
    assert pawn_capture in frontier_moves(board, "all-captures")
    assert quiet not in frontier_moves(board, "all-captures")
    assert quiet in frontier_moves(board, "all")


def test_frontier_choice_is_legal_and_reports_budget_exhaustion() -> None:
    board = chess.Board()
    choice = choose_frontier_move(
        board,
        lambda _: 0.0,
        selector_schedule=["all", "forcing"],
        maximum_expanded_children_per_root=1,
        terminal_cp=2000,
    )
    assert chess.Move.from_uci(choice.move) in board.legal_moves
    assert choice.legal_moves_evaluated == 20
    assert choice.internal_children_expanded == 20
    assert choice.budget_exhausted_roots == 20


def test_selection_uses_eligibility_then_lowest_state_count() -> None:
    models = {
        "baseline": {
            "metrics": {"mean_regret_cp": 100.0},
            "complexity": {"mean_total_states": 100.0},
        },
        "cheap": {
            "metrics": {"mean_regret_cp": 85.0},
            "complexity": {"mean_total_states": 150.0},
        },
        "strong": {
            "metrics": {"mean_regret_cp": 70.0},
            "complexity": {"mean_total_states": 300.0},
        },
        "uncertain": {
            "metrics": {"mean_regret_cp": 80.0},
            "complexity": {"mean_total_states": 120.0},
        },
    }
    deltas = {
        "cheap": {"mean": -15.0, "p2_5": -20.0, "p97_5": -5.0},
        "strong": {"mean": -30.0, "p2_5": -40.0, "p97_5": -20.0},
        "uncertain": {"mean": -20.0, "p2_5": -40.0, "p97_5": 2.0},
    }
    decision = select_frontier_candidate(
        models,
        deltas,
        {
            "baseline": "baseline",
            "minimum_relative_mean_regret_improvement": 0.10,
            "require_group_bootstrap_interval_below_zero": True,
            "maximum_advancing_candidates": 1,
        },
    )
    assert decision["selected_policy"] == "cheap"
    assert decision["eligible_extensions"] == ["cheap", "strong"]


def test_selection_retains_baseline_when_threshold_fails() -> None:
    models = {
        "baseline": {
            "metrics": {"mean_regret_cp": 100.0},
            "complexity": {"mean_total_states": 100.0},
        },
        "candidate": {
            "metrics": {"mean_regret_cp": 95.0},
            "complexity": {"mean_total_states": 90.0},
        },
    }
    result = select_frontier_candidate(
        models,
        {"candidate": {"mean": -5.0, "p2_5": -10.0, "p97_5": -1.0}},
        {
            "baseline": "baseline",
            "minimum_relative_mean_regret_improvement": 0.10,
            "require_group_bootstrap_interval_below_zero": True,
            "maximum_advancing_candidates": 1,
        },
    )
    assert result["baseline_retained"] is True
