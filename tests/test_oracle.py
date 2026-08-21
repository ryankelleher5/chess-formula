from __future__ import annotations

import os

import chess
import chess.engine
import pytest

from chess_formula.config import load_config
from chess_formula.ingest import ingest_pgn
from chess_formula.oracle import label_positions, normalize_score


def test_stockfish_score_normalization_is_white_relative() -> None:
    white_pov = chess.engine.PovScore(chess.engine.Cp(125), chess.WHITE)
    assert normalize_score(white_pov) == (125, None)
    black_pov = chess.engine.PovScore(chess.engine.Cp(125), chess.BLACK)
    assert normalize_score(black_pov) == (-125, None)
    white_mates = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)
    cp, mate = normalize_score(white_mates, mate_score_cp=100000)
    assert cp > 0
    assert mate == 3


@pytest.mark.skipif(not os.environ.get("STOCKFISH_EXECUTABLE"), reason="Stockfish not configured")
def test_stockfish_integration_is_cached(tmp_path) -> None:
    pgn = tmp_path / "game.pgn"
    pgn.write_text('[Result "*"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *\n', encoding="utf-8")
    database = tmp_path / "test.duckdb"
    config = load_config()
    config["sampling"] = {"every_n_plies": 2, "min_ply": 2, "max_positions_per_game": 2}
    config["labeling"].update({"limit_type": "depth", "limit_value": 4, "multipv": 1})
    ingest_pgn(pgn, database, config)
    first = label_positions(os.environ["STOCKFISH_EXECUTABLE"], database, config)
    second = label_positions(os.environ["STOCKFISH_EXECUTABLE"], database, config)
    assert first["new_labels"] == 2
    assert second["new_labels"] == 0
