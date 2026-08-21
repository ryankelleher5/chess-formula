from __future__ import annotations

import chess

from chess_formula.march import forcing_moves, selective_minimax


def test_forcing_moves_excludes_quiet_starting_moves() -> None:
    assert forcing_moves(chess.Board()) == []


def test_forcing_search_finds_white_mate_in_one() -> None:
    board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 w - - 0 1")
    value, expanded = selective_minimax(
        board,
        lambda position: 0.0,
        depth_plies=2,
        maximum_expanded_children=128,
        terminal_cp=2000.0,
    )
    assert value == 2000.0
    assert expanded > 0


def test_forcing_search_returns_static_value_without_candidates() -> None:
    value, expanded = selective_minimax(
        chess.Board(),
        lambda position: 42.0,
        depth_plies=2,
        maximum_expanded_children=128,
        terminal_cp=2000.0,
    )
    assert value == 42.0
    assert expanded == 0


def test_forcing_search_respects_expansion_budget() -> None:
    board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 w - - 0 1")
    _, expanded = selective_minimax(
        board,
        lambda position: 0.0,
        depth_plies=2,
        maximum_expanded_children=1,
        terminal_cp=2000.0,
    )
    assert expanded == 1
