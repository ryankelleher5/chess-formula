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

## First verified experiment

The pipeline-validation run `2026-08-21_baseline_linear_001` used 101 unique positions from six games (55/18/28 train/validation/test) and Stockfish 18 at depth 10, MultiPV 3, one thread, and 16 MB hash. The 17-parameter evaluator achieved 192.08 cp MAE, 0.4271 correlation, 64.29% sign accuracy, and a 7.14% ≥500 cp error rate on 28 held-out positions.

These figures validate the apparatus, not the hypothesis. The dataset is too small, several learned coefficient signs are implausible, and both catastrophic errors come from related forcing positions in one test game. [RESEARCH.md](RESEARCH.md) records the interpretation and next experiment without treating this run as playing-strength evidence.

## Coefficient-stability experiment

The second experiment expands to a reproducibly generated, untracked 36-game legal corpus and performs 30 game-grouped resamples over 691 balanced-side positions. It compares material-only (2 parameters), compact-5 (6), and full-16 (17) formulas:

| Formula | Mean MAE | Mean correlation | Sign accuracy | ≥500 cp errors |
|---|---:|---:|---:|---:|
| Material-only | 183.84 cp | 0.6112 | 74.03% | 2.78% |
| Compact-5 | **179.61 cp** | 0.6482 | 78.12% | 3.33% |
| Full-16 | 182.46 cp | **0.6526** | **78.55%** | 4.00% |

The full model's tiny correlation gain does not compensate for its description cost or worse MAE/catastrophic-error rate. The compact formula is the current Pareto candidate, while material alone remains a strong control.

Run the experiment from scratch:

```bash
chess-formula --config configs/stability.json generate-corpus \
  --output data/raw/stability-synthetic.pgn \
  --stockfish "$(command -v stockfish)"
chess-formula --config configs/stability.json ingest data/raw/stability-synthetic.pgn
chess-formula --config configs/stability.json label --stockfish "$(command -v stockfish)"
chess-formula --config configs/stability.json stability baseline-linear
```

The generated PGN, DuckDB database, and report remain ignored. See [docs/synthetic-corpus.md](docs/synthetic-corpus.md) for the sampling domain and limitations.

## Human-domain transfer

The next frozen benchmark uses a deterministic 60-game reservoir sample from the official CC0 Lichess January 2013 standard-rated archive. It contains 1,091 unique positions, balanced 542/549 by side to move. The synthetic compact-5 conclusion did **not** transfer cleanly:

| Formula | Mean MAE | Mean correlation | Sign accuracy | ≥500 cp errors |
|---|---:|---:|---:|---:|
| Material-only | 154.00 cp | 0.6473 | 72.98% | 3.58% |
| Compact-5 | 150.67 cp | 0.6548 | **73.68%** | 3.58% |
| Full-16 | **141.25 cp** | **0.7050** | 72.72% | **2.47%** |

Full-16 gains most in human middlegames and forcing-proxy positions. A passed-pawn term that was stably negative on synthetic data becomes stably positive on human games, showing why independent-domain validation is required before interpreting coefficients as chess structure. See [docs/human-corpus.md](docs/human-corpus.md) for provenance, licensing, exact checksums, selection rules, and reproduction commands.

## Minimum-subset selection

Nested game-grouped forward selection on the January corpus locked a three-feature
subset—`material`, `space`, and `tempo`—for an untouched February confirmation.
The selection procedure achieved 150.76 cp outer-fold MAE, recovering only 3.23
cp of full-16's 12.75 cp improvement over material. The failure to meet the 90%
gain-retention target on outer folds is part of the result; the subset is frozen
rather than repaired using confirmation data. See
[docs/feature-selection.md](docs/feature-selection.md) for the leakage controls,
selection rule, and exact lock.

## Scientific controls

- A SHA-256-derived seed-stable split assigns whole games to train, validation, or test.
- Stability resampling treats games, never individual positions, as the independent grouping unit.
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
