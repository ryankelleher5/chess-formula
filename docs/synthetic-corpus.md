# Synthetic stability corpus

The coefficient-stability experiment needs dozens of legally independent games without committing a generated dataset or introducing uncertain third-party licensing. `chess-formula generate-corpus` therefore creates the input locally and deterministically.

For each game, `guided-stockfish-v1` chooses the first six plies from legal moves using a seeded distribution that favors center occupation, minor-piece development, castling, and captures while penalizing early queen movement. Stockfish 18 then plays both sides at 100 nodes/move, one thread, and 16 MB hash until a terminal result or 72 plies. The PGN records generator version, seed, engine, and node budget in its headers.

The frozen `coefficient-stability-v1` configuration generates 36 games, samples every third ply after ply four, and caps each game at 20 positions. The odd cadence deliberately alternates side to move. The accepted corpus produced 691 unique positions: 347 White-to-move and 344 Black-to-move.

## What this corpus can test

- deterministic end-to-end reproducibility;
- game-grouped coefficient and metric stability;
- whether additional formula terms improve the complexity frontier inside this domain;
- unusual but legal positions outside a single human opening repertoire.

## What it cannot establish

The games are neither representative human chess nor strong self-play. The opening policy and 100-node continuation define a narrow artificial distribution, and depth-8 labels are only a shallow oracle. Results must transfer to an independent human-game or exact domain before being interpreted as general chess structure. The generated PGN, derived DuckDB database, and experiment artifacts are ignored by Git.
