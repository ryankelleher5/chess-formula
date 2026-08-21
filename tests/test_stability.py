from __future__ import annotations

import numpy as np

from chess_formula.model import fit_ridge
from chess_formula.stability import grouped_resamples, summarize_coefficients


def test_grouped_resamples_are_deterministic_and_disjoint() -> None:
    game_ids = [f"game-{index // 3}" for index in range(30)]
    first = grouped_resamples(game_ids, repeats=5, test_fraction=0.2, seed=7)
    second = grouped_resamples(game_ids, repeats=5, test_fraction=0.2, seed=7)
    assert first == second
    for train, test in first:
        assert train.isdisjoint(test)
        assert train | test == set(game_ids)
        assert len(test) == 2


def test_coefficient_summary_reports_sign_stability() -> None:
    runs = [np.array([1.0, -2.0]), np.array([2.0, -1.0]), np.array([-0.5, -3.0])]
    summary = summarize_coefficients(runs, ["unstable", "stable"])
    assert summary["unstable"]["dominant_sign_fraction"] == 2 / 3
    assert summary["stable"]["dominant_sign_fraction"] == 1.0


def test_fit_ridge_recovers_simple_raw_unit_relation() -> None:
    matrix = np.arange(20, dtype=float).reshape(-1, 1)
    target = 3.0 * matrix[:, 0] + 7.0
    coefficients, intercept = fit_ridge(matrix, target, alpha=0.0)
    np.testing.assert_allclose(coefficients, [3.0], atol=1e-10)
    assert abs(intercept - 7.0) < 1e-10
