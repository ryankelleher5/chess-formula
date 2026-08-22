from __future__ import annotations

import chess

from chess_formula.uncertainty_adjudication import (
    derive_frozen_selectors,
    evaluate_selector,
    measure_adjudication,
)


def _context(tier: str, kind: str, scores: dict[str, int]) -> dict:
    return {
        "tier_id": tier,
        "context_key": f"{kind}:one",
        "context_kind": kind,
        "fen": chess.STARTING_FEN,
        "side_to_move": "white",
        "legal_moves": len(scores),
        "moves": [
            {"move_uci": move, "eval_cp": score, "mate": None}
            for move, score in scores.items()
        ],
    }


def _tier(tier: str, scores: dict[str, int]) -> dict[str, dict]:
    return {
        f"{kind}:one": _context(tier, kind, scores)
        for kind in ("root", "parent")
    }


def test_conservative_union_is_frozen_from_both_prior_tiers() -> None:
    tiers = {
        "per-move-40000": _tier(
            "per-move-40000", {"e2e4": 100, "d2d4": 80, "g1f3": 0}
        ),
        "per-move-160000": _tier(
            "per-move-160000", {"e2e4": 70, "d2d4": 110, "g1f3": 0}
        ),
    }
    selectors = derive_frozen_selectors(tiers, threshold_cp=25, score_clip_cp=2000)
    assert selectors["40k"]["parent:one"] == {"e2e4", "d2d4"}
    assert selectors["160k"]["parent:one"] == {"d2d4"}
    assert selectors["intersection"]["parent:one"] == {"d2d4"}
    assert selectors["union"]["parent:one"] == {"e2e4", "d2d4"}


def test_evaluation_reports_deep_false_negative_consequence() -> None:
    audit = _tier("per-move-640000", {"e2e4": 50, "d2d4": 40, "g1f3": 400})
    selector = {"root:one": {"e2e4"}, "parent:one": {"e2e4"}}
    result = evaluate_selector(selector, audit, threshold_cp=25, score_clip_cp=2000)
    assert result["parent"]["top_reply_recall"] == 0
    assert result["parent"]["maximum_pruning_loss_cp"] == 350
    assert result["parent"]["omissions_over_100cp"] == 1
    assert result["parent"]["omissions_over_300cp"] == 1


def test_empty_control_is_a_capped_zero_branch_failure() -> None:
    audit = _tier("per-move-640000", {"e2e4": 50, "d2d4": 40, "g1f3": 400})
    selector = {"root:one": set(), "parent:one": set()}
    result = evaluate_selector(selector, audit, threshold_cp=25, score_clip_cp=2000)
    assert result["parent"]["zero_retained_contexts"] == 1
    assert result["parent"]["maximum_pruning_loss_cp"] == 4000


def test_advancement_requires_literal_complete_recall() -> None:
    audit = _tier("per-move-640000", {"e2e4": 100, "d2d4": 90, "g1f3": 0})
    selectors = {
        name: {"root:one": {"e2e4"}, "parent:one": {"e2e4"}}
        for name in ("40k", "160k", "intersection", "union")
    }
    config = {
        "uncertainty_adjudication": {
            "frozen_union": {"threshold_cp": 25},
            "oracle": {"score_clip_cp": 2000},
            "advancement_gate": {
                "minimum_top_reply_recall": 1.0,
                "minimum_within25_micro_recall": 1.0,
                "minimum_decision_preservation_25cp": 1.0,
                "maximum_omissions_over_100cp": 0,
                "maximum_omissions_over_300cp": 0,
                "maximum_mean_retained_fraction": {"root": 0.35, "parent": 0.35},
            },
        }
    }
    result = measure_adjudication(selectors, audit, config)
    assert result["decision"]["passed"] is False
    assert "parent:within25_micro_recall" in result["decision"]["failures"]
