from __future__ import annotations

import math
import random
from pathlib import Path

import chess
import chess.engine
import chess.pgn

GENERATOR_VERSION = "guided-stockfish-v1"
PIECE_VALUES = {
    chess.PAWN: 1.0,
    chess.KNIGHT: 3.2,
    chess.BISHOP: 3.3,
    chess.ROOK: 5.0,
    chess.QUEEN: 9.0,
    chess.KING: 0.0,
}
CENTER = {chess.D4, chess.E4, chess.D5, chess.E5}
EXTENDED_CENTER = {
    chess.C3,
    chess.D3,
    chess.E3,
    chess.F3,
    chess.C4,
    chess.F4,
    chess.C5,
    chess.F5,
    chess.C6,
    chess.D6,
    chess.E6,
    chess.F6,
}
MINOR_HOME = {chess.B1, chess.C1, chess.F1, chess.G1, chess.B8, chess.C8, chess.F8, chess.G8}


def _opening_score(board: chess.Board, move: chess.Move) -> float:
    moving_piece = board.piece_at(move.from_square)
    captured_piece = board.piece_at(move.to_square)
    score = 0.0
    if captured_piece:
        score += 2.0 * PIECE_VALUES[captured_piece.piece_type]
    if move.to_square in CENTER:
        score += 2.0
    elif move.to_square in EXTENDED_CENTER:
        score += 0.75
    if (
        move.from_square in MINOR_HOME
        and moving_piece
        and moving_piece.piece_type
        in (
            chess.KNIGHT,
            chess.BISHOP,
        )
    ):
        score += 1.5
    if moving_piece and moving_piece.piece_type == chess.QUEEN:
        score -= 1.5
    if board.is_castling(move):
        score += 3.0
    board.push(move)
    if board.is_check():
        score += 1.0
    board.pop()
    return score


def choose_guided_move(board: chess.Board, rng: random.Random) -> chess.Move:
    moves = list(board.legal_moves)
    if not moves:
        raise ValueError("Cannot select a move in a terminal position")
    scores = [_opening_score(board, move) for move in moves]
    maximum = max(scores)
    weights = [math.exp((score - maximum) / 1.25) for score in scores]
    return rng.choices(moves, weights=weights, k=1)[0]


def generate_corpus(
    output: str | Path,
    *,
    games: int,
    max_plies: int,
    seed: int,
    opening_random_plies: int,
    stockfish_path: str | Path | None = None,
    engine_nodes_per_move: int = 100,
) -> dict:
    if games < 1 or max_plies < 1:
        raise ValueError("games and max_plies must be positive")
    rng = random.Random(seed)
    engine = None
    engine_version = None
    if stockfish_path is not None:
        path = Path(stockfish_path)
        if not path.exists():
            raise FileNotFoundError(path)
        engine = chess.engine.SimpleEngine.popen_uci(str(path))
        engine_version = engine.id.get("name", path.name)
        configurable = {
            name: value
            for name, value in {"Threads": 1, "Hash": 16}.items()
            if name in engine.options
        }
        if configurable:
            engine.configure(configurable)

    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    generated: list[chess.pgn.Game] = []
    terminal_games = 0
    try:
        for game_number in range(1, games + 1):
            board = chess.Board()
            moves: list[chess.Move] = []
            for ply in range(max_plies):
                if board.is_game_over(claim_draw=True):
                    break
                if ply < opening_random_plies or engine is None:
                    move = choose_guided_move(board, rng)
                else:
                    result = engine.play(
                        board,
                        chess.engine.Limit(nodes=engine_nodes_per_move),
                    )
                    if result.move is None:
                        break
                    move = result.move
                moves.append(move)
                board.push(move)
            outcome = board.outcome(claim_draw=True)
            terminal_games += outcome is not None
            game = chess.pgn.Game()
            game.headers.update(
                {
                    "Event": "Chess Formula Synthetic Stability Corpus",
                    "Site": "Local deterministic generator",
                    "Date": "2026.08.20",
                    "Round": str(game_number),
                    "White": f"Synthetic-{game_number:03d}-White",
                    "Black": f"Synthetic-{game_number:03d}-Black",
                    "Result": outcome.result() if outcome else "*",
                    "Generator": GENERATOR_VERSION,
                    "GeneratorSeed": str(seed),
                    "Engine": engine_version or "guided-random-only",
                    "EngineNodes": str(engine_nodes_per_move if engine else 0),
                }
            )
            node = game
            for move in moves:
                node = node.add_variation(move)
            generated.append(game)
        text = (
            "\n\n".join(
                game.accept(
                    chess.pgn.StringExporter(headers=True, variations=False, comments=False)
                )
                for game in generated
            )
            + "\n"
        )
        destination.write_text(text, encoding="utf-8")
    finally:
        if engine is not None:
            engine.quit()
    return {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "games": len(generated),
        "terminal_games": terminal_games,
        "maximum_plies": max_plies,
        "opening_random_plies": opening_random_plies,
        "engine": engine_version,
        "engine_nodes_per_move": engine_nodes_per_move if engine_version else 0,
        "output": str(destination),
    }
