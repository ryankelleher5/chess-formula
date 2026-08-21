# Research Log

This file is append-only. Corrections should be added as dated notes rather than erasing earlier interpretations.

## 2026-08-20 — Experiment 001: first linear pipeline

### Hypothesis

A small, inspectable linear combination of human-readable features can preserve a measurable portion of shallow Stockfish judgment on positions from unseen games.

### Method

Ingest a six-game local PGN; sample every fourth ply after ply four; assign games deterministically to train/validation/test; deduplicate rule-relevant FEN state; label positions with a locally recorded Stockfish configuration; fit a ridge-linear model to 16 White-relative features; evaluate on the frozen `baseline-v1` test split.

### Result

The verified run `2026-08-21_baseline_linear_001` ingested 6 games without parse errors and produced 101 unique sampled positions: 55 train, 18 validation, and 28 test. Stockfish 18 labeled all positions at depth 10, MultiPV 3, one thread, and 16 MB hash. The fitted equation has 16 feature coefficients plus an intercept (17 parameters; approximately 33 arithmetic operations per evaluation).

On the frozen 28-position test split, clipped at ±2,000 cp:

- MAE: 192.08 cp
- RMSE: 405.37 cp
- Pearson correlation: 0.4271
- sign accuracy: 64.29%
- catastrophic error rate at 500 cp: 7.14% (2 positions)
- measured matrix-only inference latency: approximately 0.055 µs/position

The accepted run records Git revision `49b0397`. Generated artifacts, including plots and the complete formula, are local under `results/2026-08-21_baseline_linear_001/` and intentionally excluded from Git.

### Interpretation

The pipeline is operational, but the numerical result is not evidence of chess strength. Correlation is positive but weak, the test set contains only two source games, and related positions within a game are not independent observations. Several coefficients are implausible in isolation: material is worth only 19.14 cp per pawn-unit, while passed pawns and the bishop-pair indicator receive large negative weights. This strongly suggests small-sample confounding and coefficient instability rather than newly discovered chess principles.

The two catastrophic errors occur in related forcing positions from the same held-out game. One is a mate sequence scored by Stockfish at the +2,000 cp clip while the static formula predicts only +156 cp. The other is a large tactical advantage (+658 cp) predicted as -43 cp. This is consistent with the hypothesis that a compact static description may explain quiet judgment better than forcing tactics, but two related observations cannot establish that conclusion.

### What failed

An initial dry run exposed an illegal continuation in one synthetic sample game and a deterministic seed that placed all six games in training. The sample was truncated at its last verified legal move, results were corrected to match the movetext, and seed 20 was frozen only after confirming a 3/1/2 game split. A later report-query regression was caught after labeling and training; cached labels allowed the report to resume without recomputation, and a regression test was added. These failed runs were not accepted as experiments.

### Next experiment

Before adding features or symbolic machinery, expand to a still-small but diverse corpus (at least dozens of games) and measure **coefficient stability under repeated game-grouped resampling**. Compare material-only, a small stable subset, and the current 16-feature ridge model; report game-clustered uncertainty intervals and how often coefficient signs change. This directly tests whether the apparent linear signal is reproducible or a split artifact. Preserve `baseline-v1`; create a new benchmark version for the expanded corpus. If forcing-position errors persist across independent games, the following experiment should compare the unchanged formula against the same formula plus a strictly budgeted forcing-line search.
