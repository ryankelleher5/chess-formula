from __future__ import annotations

import os

import chess
import numpy as np
import pytest

from chess_formula.config import load_config
from chess_formula.database import connect_database
from chess_formula.ingest import ingest_pgn
from chess_formula.move_policy import (
    choose_legal_move,
    label_forced_policy_moves,
    move_quality_metrics,
)
from chess_formula.oracle import label_positions


def test_static_policy_returns_legal_white_maximum_with_uci_tie_break() -> None:
    board = chess.Board()

    def evaluator(position: chess.Board) -> float:
        last_move = position.peek().uci()
        return 10.0 if last_move in {"a2a3", "b2b3"} else 0.0

    choice = choose_legal_move(board, evaluator, terminal_cp=2000)
    assert choice.move == "a2a3"
    assert chess.Move.from_uci(choice.move) in board.legal_moves
    assert choice.legal_moves_evaluated == 20
    assert choice.forcing_children_expanded == 0


def test_static_policy_minimizes_for_black() -> None:
    board = chess.Board()
    board.push_uci("e2e4")

    def evaluator(position: chess.Board) -> float:
        return -5.0 if position.peek().uci() == "a7a5" else 5.0

    choice = choose_legal_move(board, evaluator, terminal_cp=2000)
    assert choice.move == "a7a5"
    assert choice.predicted_cp == -5.0


def test_searched_policy_counts_root_and_forcing_work() -> None:
    board = chess.Board("7k/8/8/8/8/8/5Q2/6K1 w - - 0 1")
    choice = choose_legal_move(
        board,
        lambda _: 0.0,
        terminal_cp=2000,
        search_depth_plies=2,
        maximum_expanded_children=128,
    )
    assert chess.Move.from_uci(choice.move) in board.legal_moves
    assert choice.legal_moves_evaluated == board.legal_moves.count()
    assert choice.forcing_children_expanded > 0


def test_terminal_position_cannot_choose_move() -> None:
    board = chess.Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1")
    with pytest.raises(ValueError, match="terminal"):
        choose_legal_move(board, lambda _: 0.0, terminal_cp=2000)


def test_move_quality_uses_side_to_move_and_clamps_oracle_inversions() -> None:
    metrics, regret = move_quality_metrics(
        turns=np.asarray([chess.WHITE, chess.BLACK, chess.WHITE]),
        chosen_moves=["a2a3", "a7a6", "b2b3"],
        chosen_scores=np.asarray([80.0, -30.0, 120.0]),
        best_moves=["a2a3", "b7b6", "c2c3"],
        best_scores=np.asarray([100.0, -50.0, 100.0]),
        top_moves=[["a2a3"], ["b7b6", "a7a6"], ["c2c3", "b2b3"]],
        top_k=2,
    )
    assert regret.tolist() == [20.0, 20.0, 0.0]
    assert metrics["mean_regret_cp"] == pytest.approx(40 / 3)
    assert metrics["top_1_agreement"] == pytest.approx(1 / 3)
    assert metrics["top_2_agreement"] == 1.0
    assert metrics["oracle_noise_inversion_rate"] == pytest.approx(1 / 3)


@pytest.mark.skipif(not os.environ.get("STOCKFISH_EXECUTABLE"), reason="Stockfish not configured")
def test_forced_policy_oracle_is_cached(tmp_path) -> None:
    pgn = tmp_path / "game.pgn"
    pgn.write_text('[Result "*"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *\n', encoding="utf-8")
    database = tmp_path / "test.duckdb"
    config = load_config()
    config["sampling"] = {"every_n_plies": 2, "min_ply": 2, "max_positions_per_game": 1}
    config["labeling"].update({"limit_type": "depth", "limit_value": 4, "multipv": 3})
    ingest_pgn(pgn, database, config)
    root = label_positions(os.environ["STOCKFISH_EXECUTABLE"], database, config)
    connection = connect_database(database)
    digest, fen = connection.execute("SELECT position_hash, fen FROM positions").fetchone()
    best = connection.execute(
        "SELECT best_move FROM engine_analysis WHERE engine_key = ?", [root["engine_key"]]
    ).fetchone()[0]
    connection.close()
    alternative = next(
        move.uci() for move in chess.Board(fen).legal_moves if move.uci() != best
    )
    first = label_forced_policy_moves(
        os.environ["STOCKFISH_EXECUTABLE"],
        database,
        config,
        root["engine_key"],
        {digest: {best, alternative}},
    )
    second = label_forced_policy_moves(
        os.environ["STOCKFISH_EXECUTABLE"],
        database,
        config,
        root["engine_key"],
        {digest: {best, alternative}},
    )
    assert first["new_forced_moves"] == 1
    assert first["root_best_moves_reused"] == 1
    assert second["new_forced_moves"] == 0
    assert second["cached_forced_moves"] == 1
