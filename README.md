# Chess Formula

Chess Formula is a research laboratory for one deliberately provocative question:

> How much of strong or optimal chess behavior can be described by a surprisingly small mathematical or algorithmic object?

Chess has an enormous state space and game tree. That establishes combinatorial scale; it does **not** by itself establish that strong decision-making has equally high description complexity. Physics often predicts large systems through compressed laws rather than atom-by-atom simulation. This project tests—rather than assumes—that chess might admit useful compression of the same broad kind.

The first milestone is intentionally modest and fully runnable:

```text
small PGN → sampled positions → Stockfish labels → 16 readable features
          → ridge-linear evaluator → game-held-out benchmark → report
```

The linear evaluator is emitted as an explicit equation. Every experiment records its configuration, seed, engine identity and limits, environment, runtime, metrics, plots, and Git revision where available.

## What this project is not

The project is not currently trying to solve chess, train AlphaZero, beat unrestricted Stockfish, ingest every public game, or brute-force the game tree. Predicting a Stockfish evaluation is not the same as predicting its move, and neither alone establishes objective playing strength. A compact predictive model is interesting evidence, not a mathematical law or proof.

## Quick start

Requirements are Python 3.11+ and a local Stockfish executable.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

chess-formula run-baseline \
  --pgn data/samples/example.pgn \
  --stockfish /path/to/stockfish
```

The equivalent staged workflow is:

```bash
chess-formula ingest data/samples/example.pgn
chess-formula label --stockfish /path/to/stockfish
chess-formula train baseline-linear
chess-formula benchmark baseline-linear
```

Generated data lives in `data/processed/`; generated models in `models/`; and experiment artifacts in `results/YYYY-MM-DD_baseline_linear_NNN/`. These are intentionally ignored by Git.

## The first formula

The baseline uses 16 White-relative measurements: material, mobility, center control, development, space, king safety, passed/isolated/doubled/connected pawns, bishop pair, rooks on open files, piece activity, threat pressure, tempo, and game phase. Ridge regression fits coefficients to clipped Stockfish centipawn labels. The exact learned equation is saved in `formula.txt` and the report.

All evaluation values obey one invariant:

> **Positive evaluation means advantage for White.**

Mate scores are converted to finite centipawn values for storage. Training and baseline metrics clip extreme labels to the configured range (±2000 cp by default), while raw engine values are retained in DuckDB.

## Scientific controls

- A SHA-256-derived seed-stable split assigns whole games to train, validation, or test.
- A deduplicated position is assigned to exactly one split, preventing repeated openings from crossing split boundaries.
- The fixed benchmark is versioned at `benchmarks/baseline-v1.json`.
- Stockfish labels are keyed by exact engine identity and analysis configuration, cached, and resumable.
- The DuckDB schema separates games, unique positions, occurrences, oracle analysis, experiments, and benchmark results.
- PGN ingestion is idempotent and supports plain, gzip, bzip2, and optional zstd streams.
- Important logic lives in the package, not notebooks.

See [docs/evaluation-convention.md](docs/evaluation-convention.md) and [docs/data-model.md](docs/data-model.md) for details.

## What success could look like

Scientifically interesting outcomes include a tiny evaluator with unexpected playing strength, low-dimensional latent structure, symbolic formulas that generalize, a favorable strength-per-compute frontier, compact invariants across position families, or strong evidence that chess judgment does **not** compress well. Negative results matter because the central object is a measured complexity-versus-strength curve—not a predetermined conclusion.

## Repository map

```text
configs/       versioned experiment defaults
data/          raw, processed, and tiny sample inputs
benchmarks/    frozen benchmark definitions
src/           ingestion, oracle, features, models, benchmark, CLI
tests/         deterministic unit and integration tests
results/       ignored generated experiment records
models/        ignored fitted model artifacts
docs/          conventions and architecture notes
```

The long-term sequence and decision gates are in [ROADMAP.md](ROADMAP.md). Chronological evidence belongs in [RESEARCH.md](RESEARCH.md); entries are appended rather than rewritten.

## License

Source code is released under the MIT License. The included miniature PGN is synthetic/local sample data supplied solely to exercise the pipeline.

