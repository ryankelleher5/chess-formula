from __future__ import annotations

import io
import sys

import chess
import chess.engine
import pytest

from chess_formula.frozen_policy import LOCKED_3_COEFFICIENTS, LOCKED_3_INTERCEPT
from chess_formula.uci import UciPolicyEngine, parse_position, run_uci_loop


def test_frozen_coefficients_match_accepted_may_formula() -> None:
    assert LOCKED_3_INTERCEPT == pytest.approx(6.709046125656144)
    assert LOCKED_3_COEFFICIENTS == pytest.approx(
        [75.69811222753397, 13.073404650644708, 70.02438376205043]
    )


def test_position_parser_handles_startpos_fen_and_moves() -> None:
    start = parse_position("position startpos moves e2e4 e7e5")
    expected = chess.Board()
    expected.push_uci("e2e4")
    expected.push_uci("e7e5")
    assert start.fen() == expected.fen()

    fen = "7k/8/8/8/8/8/5Q2/6K1 w - - 0 1"
    assert parse_position(f"position fen {fen}").fen() == fen


def test_position_parser_rejects_illegal_history() -> None:
    with pytest.raises(ValueError, match="Illegal"):
        parse_position("position startpos moves e2e5")


def test_uci_loop_handshake_and_legal_move() -> None:
    output = io.StringIO()
    run_uci_loop(
        UciPolicyEngine(),
        ["uci\n", "isready\n", "position startpos\n", "go nodes 1\n", "quit\n"],
        output,
    )
    lines = output.getvalue().splitlines()
    assert "uciok" in lines
    assert "readyok" in lines
    bestmove = next(line.split()[1] for line in lines if line.startswith("bestmove "))
    assert chess.Move.from_uci(bestmove) in chess.Board().legal_moves


def test_python_chess_can_drive_real_uci_subprocess() -> None:
    engine = chess.engine.SimpleEngine.popen_uci(
        [sys.executable, "-m", "chess_formula.uci", "--policy", "searched-3"],
        timeout=5,
    )
    try:
        board = chess.Board()
        result = engine.play(board, chess.engine.Limit(nodes=1))
        assert result.move in board.legal_moves
    finally:
        engine.quit()
