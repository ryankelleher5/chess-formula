# Human transfer corpus

`human-transfer-v1` tests whether conclusions drawn from deterministic synthetic self-play transfer to an independent human-game domain.

## Source and license

The source is the official Lichess standard-rated January 2013 archive:

- URL: `https://database.lichess.org/standard/lichess_db_standard_rated_2013-01.pgn.zst`
- advertised size: 17,761,302 bytes
- official SHA-256: `aa40b3671fa3cf1072eb182892cd90b0e1e003a4a5943492f64b77e7f3fd1635`
- advertised games: 121,332
- license: Creative Commons CC0, as stated by the [Lichess open database](https://database.lichess.org/)

The archive index and official checksum list are at `https://database.lichess.org/standard/` and `https://database.lichess.org/standard/sha256sums.txt`.

## Deterministic selection

The preparation command verifies the complete archive before decompressing it as a stream. It scans all 121,332 games and uses a seed-20260822 reservoir sample, preventing chronological “first N” bias. Eligible games must:

- be completed standard games;
- have both ratings present and at least 1800;
- contain 40–160 plies;
- not carry a `BOT` player title.

There were 8,458 eligible games. The frozen selection contains 60 games, ratings 1800–2189 (mean 1938.34), and 41–156 plies. Its uncompressed PGN SHA-256 is `d9797fd5d6867268c8304b6adb954e6058738cac133940e254a8a13c342e305d`. The exact source indexes are retained in the generated provenance JSON.

The archive, selected PGN, provenance JSON, DuckDB database, labels, and reports are deliberately ignored by Git. The versioned configuration and benchmark definition are sufficient to regenerate them.

## Reproduction

```bash
chess-formula --config configs/human-transfer.json prepare-human-corpus
chess-formula --config configs/human-transfer.json \
  ingest data/raw/lichess_human_transfer_60.pgn
chess-formula --config configs/human-transfer.json \
  label --stockfish "$(command -v stockfish)"
chess-formula --config configs/human-transfer.json stability baseline-linear
```

## Limitations

This is an independent domain, not a universal population. It represents rating-filtered Lichess games from one early month, with only 60 selected games and few endgame positions. Human moves select the positions, but Stockfish depth-8 still supplies the evaluation target. User identities and played moves are present in the untracked source PGN and are not copied into reports.
