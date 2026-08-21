from __future__ import annotations

import chess

from chess_formula.temporal_allocation import (
    derive_temporal_selectors,
    measure_temporal_allocation,
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


def _config() -> dict:
    return {
        "temporal_allocation_adjudication": {
            "frozen_temporal_union": {"threshold_cp": 25},
            "oracle": {"score_clip_cp": 2000},
            "advancement_gate": {
                "minimum_decision_preservation_25cp": 1.0,
                "maximum_pruning_loss_cp": 25,
                "maximum_omissions_over_100cp": 0,
                "maximum_omissions_over_300cp": 0,
                "maximum_micro_retained_fraction": {
                    "root": 0.75,
                    "parent": 0.75,
                },
                "maximum_mean_context_retained_fraction": {
                    "root": 0.75,
                    "parent": 0.75,
                },
            },
        }
    }


def test_temporal_union_recovers_early_promising_branch() -> None:
    tiers = {
        "per-move-10000": _tier(
            "per-move-10000", {"e2e4": 100, "d2d4": 60, "g1f3": 0}
        ),
        "per-move-40000": _tier(
            "per-move-40000", {"e2e4": 70, "d2d4": 110, "g1f3": 0}
        ),
        "per-move-160000": _tier(
            "per-move-160000", {"e2e4": 70, "d2d4": 120, "g1f3": 0}
        ),
    }
    selectors = derive_temporal_selectors(
        tiers,
        checkpoint_nodes=[10000, 40000, 160000],
        threshold_cp=25,
        score_clip_cp=2000,
    )
    assert selectors["late_union"]["parent:one"] == {"d2d4"}
    assert selectors["temporal_union"]["parent:one"] == {"e2e4", "d2d4"}


def test_decision_sufficiency_not_complete_set_recall_controls_gate() -> None:
    audit = _tier(
        "per-move-2560000",
        {"e2e4": 100, "d2d4": 100, "g1f3": 0, "b1c3": -100},
    )
    selected = {"root:one": {"e2e4"}, "parent:one": {"e2e4"}}
    selectors = {name: selected for name in (
        "10k",
        "40k",
        "160k",
        "late_union",
        "temporal_union",
    )}
    result = measure_temporal_allocation(selectors, audit, _config())
    assert result["selectors"]["temporal_union"]["parent"][
        "within25_micro_recall"
    ] == 0.5
    assert result["decision"]["passed"] is True
    assert result["decision"]["compact_selector_discovery_licensed"] is True


def test_late_emerging_loss_fails_decision_sufficiency_gate() -> None:
    audit = _tier(
        "per-move-2560000",
        {"e2e4": 100, "d2d4": 70, "g1f3": 0, "b1c3": -100},
    )
    selected = {"root:one": {"d2d4"}, "parent:one": {"d2d4"}}
    selectors = {name: selected for name in (
        "10k",
        "40k",
        "160k",
        "late_union",
        "temporal_union",
    )}
    result = measure_temporal_allocation(selectors, audit, _config())
    assert result["decision"]["passed"] is False
    assert "parent:maximum_pruning_loss_cp" in result["decision"]["failures"]
    assert "parent:decision_preservation_25cp" in result["decision"]["failures"]
