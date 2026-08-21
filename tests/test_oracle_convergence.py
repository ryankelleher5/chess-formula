from __future__ import annotations

import chess

from chess_formula.oracle_convergence import compare_oracle_tiers, measure_convergence


def _entry(tier: str, kind: str, scores: dict[str, int]) -> dict:
    return {
        "tier_id": tier,
        "family": "total",
        "cost_rule": "fixed-total-nodes",
        "tier_value": 100,
        "context_key": f"{kind}:one",
        "context_kind": kind,
        "fen": chess.STARTING_FEN,
        "requested_nodes": 100,
        "moves": [
            {"move_uci": move, "eval_cp": score, "mate": None}
            for move, score in scores.items()
        ],
    }


def test_tier_comparison_detects_rank_and_threshold_changes() -> None:
    left = {
        "root:one": _entry("low", "root", {"e2e4": 100, "d2d4": 80, "g1f3": 0}),
        "parent:one": _entry(
            "low", "parent", {"e2e4": 100, "d2d4": 80, "g1f3": 0}
        ),
    }
    right = {
        "root:one": _entry("high", "root", {"e2e4": 70, "d2d4": 110, "g1f3": 0}),
        "parent:one": _entry(
            "high", "parent", {"e2e4": 70, "d2d4": 110, "g1f3": 0}
        ),
    }
    result = compare_oracle_tiers(left, right, thresholds=[25, 50], score_clip_cp=2000)
    assert result["root"]["top_move_agreement"] == 0
    assert result["parent"]["mean_near_set_jaccard"]["25"] == 0.5
    assert result["root"]["threshold_label_agreement"]["25"] < 1


def test_convergence_gate_selects_cheapest_stable_tier() -> None:
    entries = {}
    for family, tier, nodes in (
        ("total", "total-low", 100),
        ("total", "total-high", 400),
        ("per-reply", "reply-low", 120),
        ("per-reply", "reply-high", 480),
    ):
        for kind in ("root", "parent"):
            row = _entry(tier, kind, {"e2e4": 100, "d2d4": 60, "g1f3": 0})
            row.update(family=family, requested_nodes=nodes)
            entries[f"{tier}:{kind}"] = row
    config = {
        "oracle_convergence": {
            "oracle": {"score_clip_cp": 2000},
            "regret_thresholds_cp": [10, 25, 50, 100],
            "budget_families": [
                {
                    "id": "total",
                    "cost_rule": "fixed-total-nodes",
                    "levels": [
                        {"id": "total-low", "value": 100},
                        {"id": "total-high", "value": 400},
                    ],
                },
                {
                    "id": "per-reply",
                    "cost_rule": "nodes-per-legal-reply",
                    "levels": [
                        {"id": "reply-low", "value": 10},
                        {"id": "reply-high", "value": 40},
                    ],
                },
            ],
            "stability_gate": {
                "minimum_top_move_agreement": 0.85,
                "minimum_top3_set_jaccard": 0.80,
                "minimum_near25_set_jaccard": 0.75,
                "minimum_threshold_label_agreement": 0.90,
                "required_label_thresholds_cp": [25, 50, 100],
                "maximum_median_regret_difference_cp": 25,
            },
            "cross_cost_rule_comparison": {
                "left_tier": "total-high",
                "right_tier": "reply-high",
            },
        }
    }
    result = measure_convergence(entries, config)
    assert result["decision"]["stability_gate_passed"] is True
    assert result["decision"]["selected_training_reference"] == "total-low"
