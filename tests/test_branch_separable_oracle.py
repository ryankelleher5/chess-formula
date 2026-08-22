from __future__ import annotations

import chess

from chess_formula.branch_separable_oracle import (
    ambiguity_metrics,
    measure_branch_separable,
)


def _context(tier: str, kind: str, scores: dict[str, int], nodes: int) -> dict:
    return {
        "tier_id": tier,
        "context_key": f"{kind}:one",
        "context_kind": kind,
        "fen": chess.STARTING_FEN,
        "side_to_move": "white",
        "legal_moves": len(scores),
        "nodes_per_move": nodes,
        "requested_nodes": nodes * len(scores),
        "moves": [
            {"move_uci": move, "eval_cp": score, "mate": None}
            for move, score in scores.items()
        ],
    }


def _tier(tier: str, scores: dict[str, int], nodes: int) -> dict[str, dict]:
    return {
        f"{kind}:one": _context(tier, kind, scores, nodes)
        for kind in ("root", "parent")
    }


def test_ambiguity_metrics_keep_disagreement_separate() -> None:
    low = _tier("low", {"e2e4": 100, "d2d4": 80, "g1f3": 0}, 10)
    high = _tier("high", {"e2e4": 70, "d2d4": 110, "g1f3": 0}, 40)
    result = ambiguity_metrics(low, high, thresholds=[25], score_clip_cp=2000)
    assert result["parent"]["thresholds"]["25"]["ambiguous"] == 1
    assert result["parent"]["top_reply_disagreements"] == 1
    assert result["parent"]["maximum_larger_reciprocal_regret_cp"] == 40


def test_audit_maximum_cannot_select_itself() -> None:
    levels = [2500, 10000, 40000, 160000]
    tiers = {
        f"per-move-{nodes}": _tier(
            f"per-move-{nodes}",
            {"e2e4": 100, "d2d4": 60, "g1f3": 0},
            nodes,
        )
        for nodes in levels
    }
    shared = {
        "per-reply-40000": _tier(
            "per-reply-40000", {"e2e4": 100, "d2d4": 60, "g1f3": 0}, 40000
        ),
        "total-1280000": _tier(
            "total-1280000", {"e2e4": 100, "d2d4": 60, "g1f3": 0}, 40000
        ),
    }
    config = {
        "branch_separable_oracle": {
            "nodes_per_move": levels,
            "regret_thresholds_cp": [10, 25, 50, 100],
            "oracle": {"score_clip_cp": 2000},
            "stability_gate": {
                "minimum_top_move_agreement": 0.85,
                "minimum_top3_set_jaccard": 0.80,
                "minimum_near25_set_jaccard": 0.75,
                "minimum_threshold_label_agreement": 0.90,
                "required_label_thresholds_cp": [25, 50, 100],
                "maximum_median_regret_difference_cp": 25,
            },
            "external_comparisons": [
                {
                    "label": "matched",
                    "independent_tier": "per-move-40000",
                    "shared_tier": "per-reply-40000",
                    "matched_nominal_nodes_per_move": True,
                },
                {
                    "label": "deep",
                    "independent_tier": "per-move-160000",
                    "shared_tier": "total-1280000",
                    "matched_nominal_nodes_per_move": False,
                },
            ],
        }
    }
    result = measure_branch_separable(tiers, shared, config)
    assert result["decision"]["selected_training_reference"] == "per-move-2500"
    assert result["decision"]["audit_only_tier"] == "per-move-160000"
    assert "per-move-160000" not in result["decision"]["eligible_tiers"]
