from __future__ import annotations

from chess_formula.budget_curve import (
    extract_budget_curve_positions,
    select_budget_candidate,
)


def test_extracts_seeded_candidate_turns_per_completed_game() -> None:
    games = [
        {
            "opponent": "baseline",
            "opening_id": "test",
            "candidate_color": "white",
            "moves_uci": [
                "e2e4",
                "e7e5",
                "g1f3",
                "b8c6",
                "f1b5",
                "a7a6",
                "b5a4",
                "g8f6",
                "e1g1",
                "f8e7",
                "f1e1",
                "b7b5",
                "a4b3",
                "d7d6",
            ],
        }
    ]
    settings = {
        "expected_games": 1,
        "positions_per_game": 3,
        "minimum_unique_positions": 3,
    }
    rows = extract_budget_curve_positions(games, settings, seed=7)
    assert len(rows) == 3
    assert all(row["candidate_color"] == "white" for row in rows)
    assert all(row["pair_key"] == "baseline:test" for row in rows)


def test_budget_selection_chooses_cheapest_eligible_policy() -> None:
    models = {
        "low": {
            "metrics": {"mean_regret_cp": 150.0},
            "complexity": {"mean_total_states": 100.0},
        },
        "cheap": {
            "metrics": {"mean_regret_cp": 105.0},
            "complexity": {"mean_total_states": 700.0},
        },
        "anchor": {
            "metrics": {"mean_regret_cp": 100.0},
            "complexity": {"mean_total_states": 1100.0},
        },
        "high": {
            "metrics": {"mean_regret_cp": 90.0},
            "complexity": {"mean_total_states": 3000.0},
        },
    }
    deltas = {
        "low": {"mean": 50.0, "p97_5": 60.0},
        "cheap": {"mean": 5.0, "p97_5": 12.0},
        "high": {"mean": -10.0, "p97_5": -2.0},
    }

    def match(score: float, lower: float) -> dict:
        return {
            "score_rate": score,
            "score_rate_bootstrap": {"p2_5": lower},
            "candidate_illegal_moves": 0,
            "candidate_timeouts": 0,
            "candidate_engine_errors": 0,
            "opponent_forfeits": 0,
        }

    settings = {
        "anchor": "anchor",
        "low_budget_reference": "low",
        "decision": {
            "minimum_regret_gain_retention": 0.8,
            "maximum_mean_regret_increase_cp": 10,
            "maximum_bootstrap_upper_regret_increase_cp": 15,
            "minimum_head_to_head_score": 0.475,
            "minimum_head_to_head_lower_bound": 0.4,
            "maximum_advancing_candidates": 1,
        },
    }
    result = select_budget_candidate(
        models,
        deltas,
        {
            "low": match(0.3, 0.2),
            "cheap": match(0.5, 0.425),
            "high": match(0.55, 0.45),
        },
        settings,
    )
    assert result["selected_policy"] == "cheap"
    assert result["eligible_cheaper_policies"] == ["cheap"]
