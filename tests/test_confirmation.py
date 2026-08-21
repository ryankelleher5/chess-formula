from __future__ import annotations

import numpy as np

from chess_formula.confirmation import grouped_bootstrap_indexes


def test_grouped_bootstrap_is_deterministic_and_keeps_games_whole() -> None:
    game_ids = np.asarray(["a", "a", "b", "b", "b", "c"])
    first = grouped_bootstrap_indexes(game_ids, repeats=5, seed=8)
    second = grouped_bootstrap_indexes(game_ids, repeats=5, seed=8)
    assert all(np.array_equal(left, right) for left, right in zip(first, second, strict=True))
    for sample in first:
        counts = {game: int(np.sum(game_ids[sample] == game)) for game in set(game_ids)}
        assert counts["a"] % 2 == 0
        assert counts["b"] % 3 == 0
        assert counts["c"] >= 0


def test_grouped_bootstrap_rejects_position_level_sample() -> None:
    try:
        grouped_bootstrap_indexes(["only-game", "only-game"], repeats=5, seed=1)
    except ValueError as exc:
        assert "two games" in str(exc)
    else:
        raise AssertionError("Expected grouped bootstrap to require multiple games")
