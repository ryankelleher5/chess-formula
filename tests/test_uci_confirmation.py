from __future__ import annotations

import json

import pytest

from chess_formula.uci_confirmation import (
    confirmation_decision,
    validate_confirmation_openings,
)


def test_confirmation_openings_are_legal_unique_and_untouched() -> None:
    openings, audit = validate_confirmation_openings(
        "configs/forcing-3-confirmation-openings.json",
        "configs/uci-pilot-openings.json",
        expected_openings=20,
        expected_plies=8,
    )
    assert len(openings) == 20
    assert audit["unique_final_rule_states"] == 20
    assert audit["pilot_final_state_overlaps"] == 0
    assert audit["pilot_move_sequence_overlaps"] == 0


def test_confirmation_openings_reject_prior_suite(tmp_path) -> None:
    prior = json.loads(open("configs/uci-pilot-openings.json").read())
    path = tmp_path / "overlap.json"
    path.write_text(json.dumps(prior), encoding="utf-8")
    with pytest.raises(ValueError, match="overlaps"):
        validate_confirmation_openings(
            path,
            "configs/uci-pilot-openings.json",
            expected_openings=20,
            expected_plies=8,
        )


def test_confirmation_decision_requires_protocol_and_strength_gates() -> None:
    clean = {
        "candidate_illegal_moves": 0,
        "candidate_timeouts": 0,
        "candidate_engine_errors": 0,
        "opponent_forfeits": 0,
        "score_rate_bootstrap": {"p2_5": 0.525},
    }
    settings = {"primary_opponent": "baseline", "candidate": "forcing-3"}
    passed = confirmation_decision({"baseline": clean}, settings)
    assert passed["forcing_3_confirms"] is True

    failed = confirmation_decision(
        {"baseline": {**clean, "score_rate_bootstrap": {"p2_5": 0.5}}},
        settings,
    )
    assert failed["forcing_3_confirms"] is False
    assert failed["accepted_policy_after_confirmation"] == "searched-3"
