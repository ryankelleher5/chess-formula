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

## 2026-08-20 — Experiment 002: coefficient stability and first complexity comparison

### Hypothesis

The predictive gain of the 16-feature formula over material alone is stable across source-game splits and large enough to justify its additional description complexity.

### Method

Generate 36 deterministic legal games from six guided-random opening plies followed by Stockfish 18 self-play constrained to 100 nodes/move. Sample every third ply after ply four, capped at 20 positions/game. This yielded 691 unique positions balanced between White and Black to move (347/344). Label with Stockfish 18 at depth 8, MultiPV 1, one thread, and 16 MB hash. Across 30 deterministic resamples, hold out 25% of whole games and fit identical ridge models for material-only, compact-5 (`material`, `mobility`, `king_safety`, `threat_pressure`, `game_phase`), and full-16 features. Clip labels to ±2,000 cp.

### Result

| Formula | Parameters | Mean MAE ± sd | Mean correlation ± sd | Sign accuracy | ≥500 cp error |
|---|---:|---:|---:|---:|---:|
| Material-only | 2 | 183.84 ± 25.67 cp | 0.6112 ± 0.1717 | 74.03% | 2.78% |
| Compact-5 | 6 | **179.61 ± 26.39 cp** | 0.6482 ± 0.1220 | 78.12% | 3.33% |
| Full-16 | 17 | 182.46 ± 24.37 cp | **0.6526 ± 0.1110** | **78.55%** | 4.00% |

In the full model, material, mobility, center control, king safety, passed pawns, isolated pawns, tempo, and game phase retained the same sign in at least 96.7% of resamples. Development, connected pawns, bishop pair, piece activity, and several other terms crossed zero frequently. The full model's stable passed-pawn coefficient was unexpectedly negative (median -59.35 cp/unit), which may reflect conditional correlation, feature definition, or the synthetic domain rather than a chess principle.

### Interpretation

The hypothesis was not supported in its strong form. Moving from material-only to five features yields a modest average gain: 4.23 cp MAE and 0.037 correlation. Expanding from five to all 16 features makes MAE 2.85 cp worse, increases catastrophic errors, and buys only 0.0044 correlation. These differences are much smaller than between-split variation. The compact-5 model is therefore the current Pareto candidate; the full formula is not justified by this experiment.

Material alone is an unusually strong baseline in this synthetic domain and has the lowest catastrophic-error rate. That is scientifically important but not yet evidence that real chess judgment is nearly reducible to material: the self-play construction and shallow oracle may heavily favor positions where material tracks evaluation.

### What failed

The first attempted run sampled every fourth ply from an even starting ply, selecting only White-to-move positions and forcing the tempo coefficient to zero. That run was invalidated and deleted. The frozen stability benchmark now samples every third ply; ingestion and reports record side-to-move counts, and a regression test ensures odd-cadence sampling covers both sides. A PGN exporter instance also retained prior output when reused, duplicating games triangularly; a deterministic parse test caught this before corpus acceptance.

### Next experiment

Validate the material-only and compact-5 frontier on an **independent, non-synthetic, license-verified human-game corpus** with the same game-grouped resampling and a new frozen benchmark version. Stratify errors by tactical/quiet character and game phase. This is more valuable than adding another feature now: it tests whether the compact result transfers outside the distribution that created it. If it transfers, compare compact-5 with and without a strictly fixed forcing-line search budget.

## 2026-08-20 — Experiment 003: independent human-domain transfer

### Hypothesis

The compact-5 formula identified on synthetic games retains essentially all useful signal from full-16 when evaluated on independently sourced human games.

### Method

Use the official CC0 Lichess January 2013 standard-rated archive (121,332 games; 17,761,302 compressed bytes; SHA-256 `aa40b3671fa3cf1072eb182892cd90b0e1e003a4a5943492f64b77e7f3fd1635`). Stream the complete verified archive and select a seed-20260822 reservoir sample of 60 completed non-BOT standard games with both ratings at least 1800 and lengths of 40–160 plies. The selected games span ratings 1800–2189 and have PGN SHA-256 `d9797fd5d6867268c8304b6adb954e6058738cac133940e254a8a13c342e305d`.

Sample every third ply after ply four, capped at 20 positions/game. After deduplication, label 1,091 positions (542 White-to-move, 549 Black-to-move) with the same Stockfish 18 depth-8, MultiPV-1, one-thread, 16 MB oracle as Experiment 002. Compare material-only, compact-5, and full-16 over 30 seeded 25% game-grouped holdouts. Stratify by opening/middlegame/endgame and a preregistered forcing proxy: in check or a legal check, promotion, or non-pawn capture exists.

### Result

| Formula | Parameters | Mean MAE ± sd | Mean correlation ± sd | Sign accuracy | ≥500 cp error |
|---|---:|---:|---:|---:|---:|
| Material-only | 2 | 154.00 ± 11.08 cp | 0.6473 ± 0.0848 | 72.98% | 3.58% |
| Compact-5 | 6 | 150.67 ± 10.76 cp | 0.6548 ± 0.0868 | **73.68%** | 3.58% |
| Full-16 | 17 | **141.25 ± 12.00 cp** | **0.7050 ± 0.0743** | 72.72% | **2.47%** |

Full-16 improves over compact-5 by 9.42 cp mean MAE, 0.0501 correlation, and 1.11 percentage points of catastrophic-error frequency. The gain is concentrated in middlegames (32.03 cp MAE) and forcing-proxy positions (11.24 cp), with little opening MAE gain (0.55 cp). Only 55 endgame positions were present; full-16 had worse endgame MAE but higher endgame correlation, so that stratum is inconclusive.

Several coefficients change materially across domains. Most notably, passed pawns change from a stable median −59.35 cp/unit in synthetic games to a stable +64.25 cp/unit in human games. Human-domain bishop pair, connected pawns, piece activity, and threat pressure are stably positive. These cross-domain reversals are stronger evidence about sampling artifacts than either domain's coefficient alone is evidence about chess law.

### Interpretation

The hypothesis is rejected. Compact-5 does not retain essentially all of full-16's useful human-domain signal. Full-16 is clearly preferable for evaluation MAE, correlation, and catastrophic-error frequency on this sample, although compact-5 retains a small sign-accuracy edge. The description remains tiny at 17 parameters, but the earlier claim that six parameters were the current general Pareto candidate was a synthetic-domain artifact.

The result also identifies where complexity buys value: not much in these openings, but substantially more in human middlegames and positions with forcing options. This supports investigating a minimum transferable subset rather than either discarding handcrafted structure or accepting all 16 features wholesale.

### What failed

The primary failure was scientific transfer, not pipeline execution: a conclusion that looked stable across 30 synthetic game splits failed on an independent human domain. The forcing proxy is intentionally broad (744/1,091 positions), and the endgame stratum is small, so neither should be treated as a precise tactical or endgame result. The sample is from one early Lichess month and remains a narrow human population.

### Next experiment

Use **nested game-grouped feature selection** on the January corpus to find the smallest handcrafted subset that retains the full-16 gain. Feature selection must occur inside each training fold. Lock the resulting subset and selection rule before testing it on a second CC0 Lichess month. This directly advances the complexity frontier while preventing the confirmation corpus from becoming tuning data.
