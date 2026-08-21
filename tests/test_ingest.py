from __future__ import annotations

import hashlib

import duckdb

from chess_formula.config import load_config
from chess_formula.ingest import game_split, ingest_pgn, position_hash

MINI_PGN = """[Event "Test"]
[Site "Local"]
[Date "2026.08.20"]
[Round "1"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3 1-0
"""


def test_position_hash_ignores_fullmove_but_not_halfmove() -> None:
    base = "8/8/8/8/8/8/4K3/7k w - - 0 1"
    different_move_number = "8/8/8/8/8/8/4K3/7k w - - 0 99"
    different_halfmove = "8/8/8/8/8/8/4K3/7k w - - 1 1"
    assert position_hash(base) == position_hash(different_move_number)
    assert position_hash(base) != position_hash(different_halfmove)


def test_game_split_is_deterministic_and_grouped() -> None:
    ratios = {"train": 0.6, "validation": 0.2, "test": 0.2}
    assert game_split("same-game", 7, ratios) == game_split("same-game", 7, ratios)
    observed = {
        game_split(hashlib.sha256(str(i).encode()).hexdigest(), 7, ratios) for i in range(100)
    }
    assert observed == {"train", "validation", "test"}


def test_pgn_parsing_position_extraction_and_idempotence(tmp_path) -> None:
    pgn = tmp_path / "tiny.pgn"
    pgn.write_text(MINI_PGN, encoding="utf-8")
    database = tmp_path / "test.duckdb"
    config = load_config()
    config["sampling"] = {"every_n_plies": 2, "min_ply": 2, "max_positions_per_game": 10}

    first = ingest_pgn(pgn, database, config)
    second = ingest_pgn(pgn, database, config)

    assert first["games"] == 1
    assert first["new_games"] == 1
    assert first["extracted_positions"] > 0
    assert first["parse_errors"] == 0
    assert second["new_games"] == 0
    connection = duckdb.connect(str(database), read_only=True)
    assert connection.execute("SELECT count(*) FROM games").fetchone()[0] == 1
    assert (
        connection.execute("SELECT count(*) FROM position_occurrences").fetchone()[0]
        == first["extracted_positions"]
    )
    fen, played_move = connection.execute(
        "SELECT p.fen, o.played_move FROM positions p "
        "JOIN position_occurrences o USING(position_hash) LIMIT 1"
    ).fetchone()
    assert len(fen.split()) == 6
    assert len(played_move) in (4, 5)
