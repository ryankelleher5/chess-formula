from __future__ import annotations

import hashlib
import io
import random
import shutil
import urllib.request
from pathlib import Path

import chess.pgn
import zstandard

from .config import write_json


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified(
    url: str,
    destination: str | Path,
    expected_sha256: str,
    *,
    expected_bytes: int | None = None,
) -> dict:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        actual = sha256_file(path)
        if actual == expected_sha256:
            return {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": actual,
                "cached": True,
            }
        raise RuntimeError(
            f"Existing archive checksum mismatch at {path}; remove it explicitly before retrying"
        )
    partial = path.with_suffix(path.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        actual = sha256_file(partial)
        if actual != expected_sha256:
            raise RuntimeError(
                f"Downloaded archive checksum mismatch: expected {expected_sha256}, got {actual}"
            )
        if expected_bytes is not None and partial.stat().st_size != expected_bytes:
            actual_bytes = partial.stat().st_size
            raise RuntimeError(
                f"Downloaded archive size mismatch: expected {expected_bytes}, got {actual_bytes}"
            )
        partial.replace(path)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": expected_sha256,
        "cached": False,
    }


def _eligible(
    game: chess.pgn.Game, minimum_rating: int, minimum_plies: int, maximum_plies: int
) -> bool:
    headers = game.headers
    if game.errors or headers.get("Result") not in {"1-0", "0-1", "1/2-1/2"}:
        return False
    if headers.get("Variant", "Standard") not in {"Standard", "From Position"}:
        return False
    if headers.get("WhiteTitle") == "BOT" or headers.get("BlackTitle") == "BOT":
        return False
    try:
        white_rating = int(headers["WhiteElo"])
        black_rating = int(headers["BlackElo"])
    except (KeyError, ValueError):
        return False
    plies = game.end().ply()
    return (
        white_rating >= minimum_rating
        and black_rating >= minimum_rating
        and minimum_plies <= plies <= maximum_plies
    )


def select_human_sample(
    archive: str | Path,
    output: str | Path,
    *,
    games: int,
    seed: int,
    minimum_rating: int,
    minimum_plies: int,
    maximum_plies: int,
) -> dict:
    if games < 1:
        raise ValueError("games must be positive")
    rng = random.Random(seed)
    reservoir: list[tuple[int, chess.pgn.Game]] = []
    scanned = 0
    eligible = 0
    with Path(archive).open("rb") as compressed:
        reader = zstandard.ZstdDecompressor().stream_reader(compressed)
        with io.TextIOWrapper(reader, encoding="utf-8", errors="replace") as text:
            while game := chess.pgn.read_game(text):
                scanned += 1
                if not _eligible(game, minimum_rating, minimum_plies, maximum_plies):
                    continue
                eligible += 1
                item = (scanned, game)
                if len(reservoir) < games:
                    reservoir.append(item)
                else:
                    index = rng.randrange(eligible)
                    if index < games:
                        reservoir[index] = item
    if len(reservoir) < games:
        raise RuntimeError(f"Only {len(reservoir)} eligible games found; requested {games}")
    reservoir.sort(key=lambda item: item[0])
    exporter_options = {"headers": True, "variations": False, "comments": False}
    selected_text = (
        "\n\n".join(
            game.accept(chess.pgn.StringExporter(**exporter_options)) for _, game in reservoir
        )
        + "\n"
    )
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(selected_text, encoding="utf-8")
    ratings = [
        int(game.headers[color]) for _, game in reservoir for color in ("WhiteElo", "BlackElo")
    ]
    plies = [game.end().ply() for _, game in reservoir]
    return {
        "games": len(reservoir),
        "games_scanned": scanned,
        "eligible_games": eligible,
        "selected_source_indexes": [index for index, _ in reservoir],
        "minimum_selected_rating": min(ratings),
        "maximum_selected_rating": max(ratings),
        "mean_selected_rating": sum(ratings) / len(ratings),
        "minimum_selected_plies": min(plies),
        "maximum_selected_plies": max(plies),
        "output": str(destination),
        "output_sha256": sha256_file(destination),
    }


def prepare_human_corpus(config: dict) -> dict:
    corpus = config["human_corpus"]
    download = download_verified(
        corpus["source_url"],
        corpus["archive"],
        corpus["source_sha256"],
        expected_bytes=int(corpus["source_bytes"]),
    )
    selection = select_human_sample(
        corpus["archive"],
        corpus["sample"],
        games=int(corpus["games"]),
        seed=int(config["seed"]),
        minimum_rating=int(corpus["minimum_rating"]),
        minimum_plies=int(corpus["minimum_plies"]),
        maximum_plies=int(corpus["maximum_plies"]),
    )
    provenance = {
        "source": {
            "url": corpus["source_url"],
            "sha256": corpus["source_sha256"],
            "bytes": corpus["source_bytes"],
            "reported_games": corpus["source_games"],
            "license": corpus["license"],
            "license_url": corpus["license_url"],
        },
        "download": download,
        "selection": selection,
        "seed": config["seed"],
    }
    write_json(corpus["provenance"], provenance)
    return provenance
