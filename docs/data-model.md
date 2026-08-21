# Data model and leakage controls

DuckDB contains six logical records:

- `games`: stable source identity, headers, result, ply count, deterministic split;
- `positions`: unique rule-relevant state and its single assigned split;
- `position_occurrences`: the game/ply context and played move;
- `engine_analysis`: immutable cache keyed by position plus engine/configuration fingerprint;
- `experiments`: run configuration, revision, timing, and artifact path;
- `benchmark_results`: metrics keyed by experiment and frozen benchmark version.

The position hash covers the first five FEN fields: placement, side to move, castling, en passant, and halfmove clock. It intentionally omits only the fullmove counter, which does not change legal moves or the 50-move state. When the same position occurs in games assigned to different splits, its first deterministic ingestion assignment remains authoritative, so a unique board cannot leak across train and test.

Raw game files and derived databases are separate and ignored by Git. Ingestion is idempotent by stable game ID. Stockfish analysis is resumable: an existing `(position_hash, engine_key)` row is never recomputed unless `--force` is explicit.

