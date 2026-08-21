from __future__ import annotations

from chess_formula.robustness import interval_excludes_zero_below


def test_advance_decision_requires_negative_upper_interval() -> None:
    assert interval_excludes_zero_below({"mean": -4.0, "p97_5": -0.1}) is True
    assert interval_excludes_zero_below({"mean": -4.0, "p97_5": 0.1}) is False
    assert interval_excludes_zero_below({"mean": 1.0, "p97_5": -0.1}) is False
