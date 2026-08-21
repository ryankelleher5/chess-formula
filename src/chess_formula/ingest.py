from __future__ import annotations

import bz2
import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import TextIO

import chess
import chess.pgn

from .database import connect_database


def position_hash(fen: str) -> str:
    """Hash rule-relevant FEN state; omit only the bookkeeping fullmove number."""
    fields = fen.split()
    if len(fields) != 6:
        raise ValueError(f"Invalid FEN with {len(fields)} fields: {fen}")
    canonical = " ".join(fields[:5])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def game_split(game_id: str, seed: int, ratios: dict[str, float]) -> str:
    total = sum(ratios[name] for name in ("train", "validation", "test"))
    if abs(total - 1.0) > 1e-9:
        raise ValueError("Split ratios must sum to 1.0")
    digest = hashlib.sha256(f"{seed}:{game_id}".encode()).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64
    if value < ratios["train"]:
        return "train"
    if value < ratios["train"] + ratios["validation"]:
        return "validation"
    return "test"


def _open_pgn(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    if path.suffix == ".bz2":
        return bz2.open(path, "rt", encoding="utf-8", errors="replace")
    if path.suffix == ".zst":
        try:
            import zstandard  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Install the optional 'zstandard' package for .zst PGNs") from exc
        binary = path.open("rb")
        reader = zstandard.ZstdDecompressor().stream_reader(binary)
        return io.TextIOWrapper(reader, encoding="utf-8", errors="replace")
    return path.open(encoding="utf-8", errors="replace")


def _stable_game_id(source: Path, index: int, game: chess.pgn.Game) -> str:
    moves = " ".join(move.uci() for move in game.mainline_moves())
    identity = {
        "source": source.name,
        "index": index,
        "event": game.headers.get("Event", ""),
        "date": game.headers.get("Date", ""),
        "round": game.headers.get("Round", ""),
        "white": game.headers.get("White", ""),
        "black": game.headers.get("Black", ""),
        "moves": moves,
    }
    encoded = json.dumps(identity, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ingest_pgn(pgn_path: str | Path, database: str | Path, config: dict) -> dict[str, int]:
    path = Path(pgn_path)
    if not path.exists():
        raise FileNotFoundError(path)
    connection = connect_database(database)
    sample = config["sampling"]
    ratios = config["split"]
    stats = {"games": 0, "new_games": 0, "extracted_positions": 0, "parse_errors": 0}

    with _open_pgn(path) as handle:
        index = 0
        while game := chess.pgn.read_game(handle):
            index += 1
            stats["games"] += 1
            if game.errors:
                stats["parse_errors"] += len(game.errors)
            game_id = _stable_game_id(path, index, game)
            split = game_split(game_id, int(config["seed"]), ratios)
            exists = connection.execute(
                "SELECT 1 FROM games WHERE game_id = ?", [game_id]
            ).fetchone()
            if exists:
                continue

            moves = list(game.mainline_moves())
            connection.execute(
                "INSERT INTO games (game_id, source, headers_json, result, ply_count, split) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    game_id,
                    str(path),
                    json.dumps(dict(game.headers), sort_keys=True),
                    game.headers.get("Result", "*"),
                    len(moves),
                    split,
                ],
            )
            stats["new_games"] += 1
            board = game.board()
            sampled = 0
            for ply, move in enumerate(moves):
                eligible = (
                    ply >= int(sample["min_ply"])
                    and (ply - int(sample["min_ply"])) % int(sample["every_n_plies"]) == 0
                    and sampled < int(sample["max_positions_per_game"])
                )
                if eligible:
                    fen = board.fen()
                    digest = position_hash(fen)
                    fields = fen.split()
                    connection.execute(
                        "INSERT OR IGNORE INTO positions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            digest,
                            fen,
                            board.board_fen(),
                            "white" if board.turn == chess.WHITE else "black",
                            board.legal_moves.count(),
                            fields[2],
                            None if fields[3] == "-" else fields[3],
                            board.halfmove_clock,
                            board.fullmove_number,
                            split,
                        ],
                    )
                    connection.execute(
                        "INSERT INTO position_occurrences VALUES (?, ?, ?, ?, ?)",
                        [game_id, ply, digest, move.uci(), game.headers.get("Result", "*")],
                    )
                    sampled += 1
                    stats["extracted_positions"] += 1
                board.push(move)

    stats["unique_positions"] = connection.execute("SELECT count(*) FROM positions").fetchone()[0]
    connection.close()
    return stats
