from __future__ import annotations

import argparse
import shlex
import sys
import time
from collections.abc import Iterable
from typing import TextIO

import chess

from .frozen_policy import (
    MAXIMUM_EXPANDED_CHILDREN_PER_ROOT,
    SEARCH_DEPTH_PLIES,
    TERMINAL_CP,
    frozen_formula,
)
from .move_policy import PolicyChoice, choose_legal_move

ENGINE_NAME = "Chess Formula Searched Locked-3"
ENGINE_AUTHOR = "Chess Formula contributors"


def parse_position(command: str) -> chess.Board:
    tokens = shlex.split(command)
    if not tokens or tokens[0] != "position":
        raise ValueError("Expected a UCI position command")
    if len(tokens) >= 2 and tokens[1] == "startpos":
        board = chess.Board()
        index = 2
    elif len(tokens) >= 8 and tokens[1] == "fen":
        board = chess.Board(" ".join(tokens[2:8]))
        index = 8
    else:
        raise ValueError("Position must use startpos or a six-field FEN")
    if index < len(tokens):
        if tokens[index] != "moves":
            raise ValueError("Unexpected text after UCI position")
        for move_uci in tokens[index + 1 :]:
            move = chess.Move.from_uci(move_uci)
            if move not in board.legal_moves:
                raise ValueError(f"Illegal position move: {move_uci}")
            board.push(move)
    return board


class UciPolicyEngine:
    def __init__(self, policy: str = "searched-3") -> None:
        self.policy = policy
        self.formula = frozen_formula(policy)
        self.board = chess.Board()

    def choose(self) -> PolicyChoice:
        searched = self.policy == "searched-3"
        return choose_legal_move(
            self.board,
            self.formula.evaluate,
            terminal_cp=TERMINAL_CP,
            search_depth_plies=SEARCH_DEPTH_PLIES if searched else None,
            maximum_expanded_children=(
                MAXIMUM_EXPANDED_CHILDREN_PER_ROOT if searched else None
            ),
        )

    def handle(self, command: str) -> list[str]:
        stripped = command.strip()
        if not stripped:
            return []
        name = stripped.split(maxsplit=1)[0]
        if name == "uci":
            return [
                f"id name {ENGINE_NAME} [{self.policy}]",
                f"id author {ENGINE_AUTHOR}",
                "uciok",
            ]
        if name == "isready":
            return ["readyok"]
        if name == "ucinewgame":
            self.board = chess.Board()
            return []
        if name == "position":
            self.board = parse_position(stripped)
            return []
        if name == "go":
            if self.board.is_game_over(claim_draw=False):
                return ["bestmove 0000"]
            started = time.perf_counter()
            choice = self.choose()
            elapsed_ms = max(1, round((time.perf_counter() - started) * 1000))
            nodes = choice.legal_moves_evaluated + choice.forcing_children_expanded
            score = choice.predicted_cp if self.board.turn is chess.WHITE else -choice.predicted_cp
            nps = round(nodes * 1000 / elapsed_ms)
            return [
                f"info depth 3 score cp {round(score)} nodes {nodes} "
                f"nps {nps} time {elapsed_ms}",
                f"bestmove {choice.move}",
            ]
        if name in {"setoption", "stop", "ponderhit", "debug", "register"}:
            return []
        if name == "quit":
            return []
        return [f"info string unsupported command: {name}"]


def run_uci_loop(
    engine: UciPolicyEngine,
    commands: Iterable[str] = sys.stdin,
    output: TextIO = sys.stdout,
) -> int:
    for command in commands:
        try:
            responses = engine.handle(command)
        except (ValueError, chess.InvalidMoveError) as exc:
            responses = [f"info string error: {exc}"]
        for response in responses:
            print(response, file=output, flush=True)
        if command.strip() == "quit":
            break
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Frozen Chess Formula UCI engine")
    parser.add_argument(
        "--policy",
        choices=["searched-3", "locked-3", "full-16"],
        default="searched-3",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_uci_loop(UciPolicyEngine(args.policy))


if __name__ == "__main__":
    raise SystemExit(main())
