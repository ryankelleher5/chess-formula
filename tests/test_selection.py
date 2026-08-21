from __future__ import annotations

import numpy as np

from chess_formula.selection import forward_select_features, lock_consensus_subset


def test_forward_selection_finds_small_predictive_subset() -> None:
    rng = np.random.default_rng(4)
    game_ids = np.repeat([f"game-{index}" for index in range(12)], 8)
    material = rng.normal(size=len(game_ids))
    signal = rng.normal(size=len(game_ids))
    noise = rng.normal(size=len(game_ids))
    matrix = np.column_stack([material, noise, signal])
    target = 5.0 * material + 3.0 * signal
    result = forward_select_features(
        matrix,
        target,
        game_ids,
        ["material", "noise", "signal"],
        alpha=0.1,
        repeats=4,
        validation_fraction=0.25,
        retention_fraction=0.9,
        seed=9,
    )
    assert result["selected_features"] == ["material", "signal"]
    assert result["selected_size"] == 2


def test_consensus_lock_uses_upper_median_size_and_frequency() -> None:
    result = lock_consensus_subset(
        [
            ["material", "mobility"],
            ["material", "king_safety", "mobility"],
            ["material", "king_safety", "tempo"],
            ["material", "king_safety"],
        ],
        ["material", "mobility", "king_safety", "tempo"],
    )
    assert result["locked_size"] == 3
    assert result["locked_features"] == ["material", "king_safety", "mobility"]
    assert result["selection_frequency"]["king_safety"] == 0.75
