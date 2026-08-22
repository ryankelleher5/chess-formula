from __future__ import annotations

import chess.pgn

from chess_formula.corpus import generate_corpus


def _read_games(path):
    games = []
    with path.open(encoding="utf-8") as handle:
        while game := chess.pgn.read_game(handle):
            games.append(game)
    return games


def test_generated_corpus_is_deterministic_and_legal(tmp_path) -> None:
    first = tmp_path / "first.pgn"
    second = tmp_path / "second.pgn"
    settings = {
        "games": 3,
        "max_plies": 12,
        "seed": 42,
        "opening_random_plies": 6,
        "engine_nodes_per_move": 10,
    }
    first_stats = generate_corpus(first, **settings)
    generate_corpus(second, **settings)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    games = _read_games(first)
    assert len(games) == 3
    assert first_stats["games"] == 3
    assert all(not game.errors for game in games)
    assert all(len(list(game.mainline_moves())) == 12 for game in games)
