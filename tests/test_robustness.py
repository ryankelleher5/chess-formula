from __future__ import annotations

from chess_formula.database import connect_database
from chess_formula.robustness import interval_excludes_zero_below, prior_position_hashes


def test_advance_decision_requires_negative_upper_interval() -> None:
    assert interval_excludes_zero_below({"mean": -4.0, "p97_5": -0.1}) is True
    assert interval_excludes_zero_below({"mean": -4.0, "p97_5": 0.1}) is False
    assert interval_excludes_zero_below({"mean": 1.0, "p97_5": -0.1}) is False


def test_prior_position_hashes_reads_all_databases(tmp_path) -> None:
    paths = [tmp_path / "first.duckdb", tmp_path / "second.duckdb"]
    for index, path in enumerate(paths):
        connection = connect_database(path)
        connection.execute(
            "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                f"hash-{index}",
                "8/8/8/8/8/8/8/K6k w - - 0 1",
                "8/8/8/8/8/8/8/K6k",
                "white",
                3,
                "-",
                None,
                0,
                1,
                "train",
            ],
        )
        connection.close()
    assert prior_position_hashes(paths) == {"hash-0", "hash-1"}
