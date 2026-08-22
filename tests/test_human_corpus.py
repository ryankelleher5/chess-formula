from __future__ import annotations

import hashlib

import zstandard

from chess_formula.human_corpus import download_verified, select_human_sample


def _pgn_games(count: int) -> str:
    games = []
    for index in range(count):
        rating = 1700 if index == 0 else 1900 + index
        games.append(
            f'''[Event "Human sample {index}"]
[Site "https://lichess.org/test{index}"]
[Date "2013.01.01"]
[Round "-"]
[White "White{index}"]
[Black "Black{index}"]
[Result "1-0"]
[WhiteElo "{rating}"]
[BlackElo "{rating}"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 1-0'''
        )
    return "\n\n".join(games) + "\n"


def test_verified_download_reuses_matching_file_url(tmp_path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"verified corpus")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    destination = tmp_path / "download.bin"
    first = download_verified(
        source.as_uri(), destination, digest, expected_bytes=source.stat().st_size
    )
    second = download_verified(
        source.as_uri(), destination, digest, expected_bytes=source.stat().st_size
    )
    assert first["cached"] is False
    assert second["cached"] is True
    assert destination.read_bytes() == b"verified corpus"


def test_human_sample_selection_is_deterministic_and_filtered(tmp_path) -> None:
    archive = tmp_path / "games.pgn.zst"
    archive.write_bytes(zstandard.ZstdCompressor().compress(_pgn_games(10).encode()))
    first = tmp_path / "first.pgn"
    second = tmp_path / "second.pgn"
    settings = {
        "games": 4,
        "seed": 11,
        "minimum_rating": 1800,
        "minimum_plies": 4,
        "maximum_plies": 20,
    }
    first_stats = select_human_sample(archive, first, **settings)
    second_stats = select_human_sample(archive, second, **settings)
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert first_stats["games"] == 4
    assert first_stats["eligible_games"] == 9
    assert first_stats["minimum_selected_rating"] >= 1800
    assert first_stats["selected_source_indexes"] == second_stats["selected_source_indexes"]
