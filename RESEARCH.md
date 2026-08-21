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

## 2026-08-20 — Experiment 004: nested minimum-subset selection

### Hypothesis

A substantially smaller handcrafted subset can retain at least 90% of full-16's January MAE gain over material-only when feature selection is repeated without game leakage.

### Method

Reuse the frozen 60-game, 1,091-position January human corpus and Stockfish labels. Perform 30 outer game-grouped resamples with 25% of games held out. Inside each outer training set, begin with material and perform greedy forward selection over eight additional 25% game-grouped validation resamples. Stop at the smallest path subset whose inner mean MAE retains 90% of full-16's improvement over material. Evaluate the freshly selected subset only on that outer fold's untouched games.

Before examining a second month, lock the upper-median selected feature count. Fill that budget by selection frequency across outer training folds, then mean selected rank and feature name. The resulting confirmation lock is `material`, `space`, and `tempo`—three features plus an intercept.

### Result

| Formula | Median parameters | Mean outer MAE ± sd | Correlation | Sign accuracy | ≥500 cp error |
|---|---:|---:|---:|---:|---:|
| Material-only | 2 | 154.00 ± 11.08 cp | 0.6473 | **72.98%** | 3.58% |
| Nested-selected | 4 | 150.76 ± 13.07 cp | 0.6638 | 71.07% | 3.32% |
| Full-16 | 17 | **141.25 ± 12.00 cp** | **0.7050** | 72.72% | **2.47%** |

Selected feature counts were 2 in 9 folds, 3 in 12, 4 in 7, and 6 in 2. `space` appeared in 60.0% of selections, `tempo` in 36.7%, and `piece_activity` in 30.0%; no other optional feature exceeded 23.3%.

### Interpretation

The hypothesis is rejected on the leakage-safe outer estimate. The selection procedure improves MAE by only 3.23 cp over material, recovering 25.3% of full-16's 12.75 cp gain rather than 90%. Its correlation improves by 0.0165, but sign accuracy falls by 1.91 percentage points. Inner-fold decisions are therefore too optimistic and unstable to establish a sufficient minimum subset from this January sample.

The frozen three-feature lock remains useful as a prospective test of whether even the weak January compression gain transfers. It must not be revised after viewing February labels or metrics. A poor confirmation result would reject this selection rule, not authorize choosing a different subset on the same confirmation corpus.

### What failed

The preregistered stopping threshold was satisfied on inner folds but did not generalize to outer folds. Optional features also had low selection frequencies, so the apparent three-feature consensus is not structurally stable. This is a statistical/scientific failure rather than a data-pipeline failure.

### Next experiment

Apply the frozen `material + space + tempo` formula, material-only, and full-16 to a deterministic 60-game sample from the independently verified CC0 Lichess February 2013 archive. Train coefficients only on January, exclude exact positions duplicated across months, and report game-clustered confirmation intervals. Do not tune on February.

## 2026-08-20 — Experiment 005: frozen February transfer confirmation

### Hypothesis

The prospectively locked `material + space + tempo` subset preserves a meaningful majority of full-16's MAE gain over material when its coefficients are trained only on January and evaluated unchanged on independent February games.

### Method

Before accessing February labels, freeze `transfer-confirmation-v1` at Git revision `7dc772a`. Verify the official CC0 Lichess February 2013 standard-rated archive (123,961 games; 18,151,480 bytes; SHA-256 `c136acdf343293c45252906fee91e3b561fb26a936979f52dbe04bb649a2fd86`) and stream all games. With seed 20260823 and the unchanged January eligibility rules, select 60 of 8,966 eligible games. The sample spans ratings 1802–2208 and has PGN SHA-256 `08f4a02582b9d5c131b1475dbea1b06647f8136981d456985967c2fd8724cd5b`.

Use the unchanged position sampler and Stockfish 18 depth-8 oracle. Sampling yields 1,106 unique balanced-side positions (551 White/555 Black). Exclude 27 exact rule-state hashes present in January, leaving 1,079 confirmation positions. Fit material-only, locked-3, and full-16 coefficients on all 1,091 January positions only. Report fixed February metrics and 1,000 source-game bootstrap intervals.

### Result

| Formula | Parameters | February MAE | Correlation | Sign accuracy | ≥500 cp error |
|---|---:|---:|---:|---:|---:|
| Material-only | 2 | 149.09 cp | 0.5637 | **73.68%** | 3.80% |
| Locked-3 | 4 | 142.85 cp | 0.6330 | 70.71% | 3.43% |
| Full-16 | 17 | **141.76 cp** | **0.6473** | 72.01% | **3.15%** |

Locked-3 improves point MAE by 6.24 cp over material and captures 85.2% of full-16's 7.32 cp gain. The paired bootstrap mean for locked minus material is −6.31 cp with a 95% interval of [−12.33, −1.08]. Full minus locked is only −1.10 cp [−8.41, +6.08], leaving the incremental MAE value of the extra 13 parameters unresolved on this sample.

The January-trained locked formula is `13.1843 + 78.2224·material + 11.7123·space + 68.8036·tempo`. Relative to material, it improves forcing-proxy MAE by 10.96 cp, middlegame MAE by 14.64 cp, and endgame MAE by 26.76 cp. It is 3.64 cp worse on quiet-proxy positions and loses 2.97 percentage points of overall sign accuracy.

### Interpretation

The hypothesis is supported in its deliberately modest form. A four-parameter evaluator transfers a substantial majority of the 17-parameter evaluator's MAE gain to an untouched month, and the paired game bootstrap supports an improvement over material. This prospective result is stronger evidence for compression than January's unstable inner selections alone.

The result does not establish that Locked-3 is universally sufficient or strictly superior. It misses the preselection target of 90% by point estimate, performs worse on sign accuracy and quiet positions, and full-16 retains slightly better MAE, correlation, and catastrophic-error frequency. Because full-minus-locked uncertainty crosses zero, the current sample cannot justify those 13 extra parameters on MAE alone.

### What failed

The January nested procedure predicted only a 3.23 cp outer-fold gain for its varying selected subsets, substantially underestimating the frozen consensus lock's 6.24 cp February gain. Conversely, the lock did not quite reach its nominal 90% gain-retention target. Metric choice matters: material-only still has the best sign accuracy. These tensions prevent a single “best formula” claim.

### Next experiment

Mine the already-frozen February failures without changing the confirmation result: identify game-grouped clusters where Locked-3 has ≥300 cp error or disagrees sharply with full-16, and test which omitted concepts describe those failures. Any proposed new compact rule must be preregistered and evaluated on a new March corpus; February may generate hypotheses but not validate them.

## 2026-08-20 — Experiment 006: failure-directed compact-rule discovery

### Hypothesis

Large Locked-3 confirmation failures form recurring, interpretable structural groups that can motivate compact rules more specific than restoring all 13 omitted features.

### Method

Freeze `failure-mining-v1` before inspecting individual boards. Select the union of February positions with Locked-3 absolute error at least 300 cp or Locked-3/Full-16 disagreement at least 150 cp. Standardize the 13 omitted features using January training means and scales, then apply deterministic farthest-first four-cluster k-means. Report source-game counts, phase, forcing status, signed error, Full-16 improvement frequency, and top centroid deviations. Generate a local interactive board explorer; do not refit on February or treat cluster summaries as validation.

### Result

The union contains 157 positions from 55 games: 101 high-error cases, 74 high-disagreement cases, and 18 meeting both criteria. Of the high-error cases, 91/101 (90.1%) have a forcing option, versus 67.7% of the full February set. Full-16 improves 70.3% of high-error positions but still has 537.3 cp mean error, compared with Locked-3's 572.3 cp.

Three clusters contain multiple games. Cluster 2 has 74 positions/29 games and emphasizes isolated (+1.60z), doubled (+1.06z), and disconnected pawn structure (−1.04z). Cluster 3 has 33 positions/12 games, is 84.8% forcing, and is dominated by a signed passed-pawn imbalance (−3.62z); Full-16 lowers its mean error from 410.2 to 376.5 cp. Cluster 4 has 49 positions/28 games, is 87.8% forcing and mostly openings, but its largest centroid deviations are all below 0.75z. Cluster 1 contains one position and cannot support a rule.

### Interpretation

The hypothesis is supported for hypothesis generation, with an important distinction. The broad, replicated signal is not another static feature: forcing positions dominate the catastrophic tail, and even Full-16 remains badly wrong there. This supports testing a strictly bounded forcing search around the compact formula. The narrower passed-pawn cluster supports a secondary one-feature extension, consistent with the stable positive human-domain passed-pawn coefficient, but its signed and cluster-selected nature makes March validation essential.

The pawn-structure and opening/activity clusters are too diffuse to justify separate rules. Cluster 1 is discarded as a singleton. No February metric is used to claim that either retained hypothesis improves unseen positions.

### What failed

Static Full-16 does not repair the dominant tactical extremes; adding all omitted terms reduces mean high-error-case error by only 35.0 cp. K-means also isolates one extreme position as a singleton, showing that a fixed cluster count does not guarantee four meaningful structures. The candidate set is threshold-selected and cannot estimate general-population prevalence beyond the explicitly reported full-set forcing comparison.

### Next experiment

Run the frozen `march-compact-rules-v1` protocol on 120 independently sampled March games. Train static coefficients on the deduplicated January/February union. Compare material-only, Locked-3, Locked-4-passed, two-ply/128-child forcing-search versions of both compact models, and Full-16. Candidate A advances only with a paired overall-MAE interval excluding zero; Candidate B advances only with a paired forcing-stratum-MAE interval excluding zero. Do not alter the protocol after viewing March.

## 2026-08-20 — Experiment 007: untouched March compact-rule validation

### Hypothesis

Two February-derived candidates can be distinguished prospectively: a passed-pawn term may improve overall compact-formula MAE, while a strictly bounded forcing search may improve forcing-stratum MAE.

### Method

Commit the complete executable protocol at `79b8787` before accessing March. Stream and verify the official CC0 March 2013 Lichess archive (158,635 games; 23,590,691 bytes; SHA-256 `89da64fc3c1fe3bfd571d7f626232189f3259aa728b46ea81e5cb8f3fdb34b9e`). From 11,349 eligible games, select a seed-20260825 reservoir sample of 120 games. The selected ratings span 1800–2313 and the PGN SHA-256 is `3cfc9f5b36343da68d4cce67bad364528faa3294bb972d634f7a26a6e98ae7c4`.

Sample 2,229 unique positions, balanced 1,108/1,121 by side to move, and label with the unchanged Stockfish 18 depth-8 oracle. Pool and deduplicate January/February into 2,170 development positions, averaging the 26 duplicate shallow labels that differ by at most 24 cp. Exclude 45 March/development overlaps, leaving 2,184 March positions. Fit static coefficients only on development data. Evaluate the preregistered static models and two-ply/128-child selective minimax, using compact formulas—not Stockfish—at leaves. Use 1,000 paired source-game bootstrap samples.

### Result

| Candidate | Params | Overall MAE | Forcing MAE | Correlation | Sign | ≥500 cp |
|---|---:|---:|---:|---:|---:|---:|
| Material-only | 2 | 134.98 | 162.27 | 0.5291 | **72.12%** | 2.66% |
| Locked-3 | 4 | 132.45 | 154.93 | 0.5933 | 69.32% | 2.20% |
| Locked-4-passed | 5 | 132.64 | 155.05 | 0.5973 | 69.41% | 2.06% |
| Full-16 | 17 | 125.77 | 147.72 | 0.6400 | 71.84% | 2.15% |
| Searched Locked-3 | 4 + search | **115.91** | **128.18** | **0.7465** | 70.47% | 1.01% |
| Searched Locked-4-passed | 5 + search | 116.60 | 129.12 | 0.7446 | 70.60% | **0.87%** |

Candidate A does not advance: passed-pawn minus Locked-3 overall MAE is +0.21 cp with 95% interval [−1.20, +1.68]. Candidate B advances: searched minus static Locked-3 forcing MAE is −26.65 cp [−33.45, −20.11]. Search also improves overall MAE by 16.55 cp, correlation by 0.1532, and catastrophic-error frequency by 1.19 percentage points. It beats static Full-16 overall MAE by 9.86 cp.

The search expands a mean of 5.04 child positions per root (p95 18, maximum 60); no position reaches the 128-child cap. The Python implementation takes 2.18 ms/position including feature extraction.

### Interpretation

The passed-pawn cluster did not transfer as a useful one-term MAE improvement, validating the preregistered refusal to promote a February association without confirmation. The forcing pattern did transfer strongly. On this domain, a tiny amount of selective computation provides more predictive value than thirteen additional static coefficients.

This supports the project's “compact principles plus rare search-heavy exceptions” possibility, although “rare” is not yet established and the algorithm's rules/expanded positions count toward complexity. The result predicts a shallow engine evaluation; it is not evidence of move quality or playing strength. Material-only's sign-accuracy edge also remains.

### What failed

Candidate A failed its primary decision rule despite the apparently coherent February cluster and a positive fitted passed-pawn coefficient. This is precisely the kind of false lead prospective validation is meant to eliminate. The 128-child budget was never reached, so this experiment does not reveal behavior at the cap. Static and searched latency were not benchmarked in an optimized common implementation, so the recorded Python latency is descriptive rather than a fair speed ratio.

### Next experiment

Freeze Searched Locked-3 and test whether its gain survives a deeper Stockfish oracle on an untouched April human corpus. Keep the formula, forcing-move definition, two-ply depth, and 128-child cap unchanged. Add explicit move-choice evaluation only after depth robustness: the current stand-pat mechanism predicts position value but does not always select a legal root move.

## 2026-08-20 — Experiment 008: April deeper-oracle robustness

### Hypothesis

The March-confirmed Searched Locked-3 forcing-stratum advantage remains negative with a 95% paired source-game-bootstrap interval excluding zero on an untouched April human corpus labeled by a deeper Stockfish oracle.

### Method

Commit the complete executable protocol at `13ae92e` before April data access. Stream and verify the official CC0 April 2013 Lichess archive (157,871 games; 23,299,559 bytes; SHA-256 `11c795d3c81c49fa97cd958b0984c044410c78ad90f454ed08abb57ab7d00d52`). From 10,174 eligible games, select a seed-20260826 reservoir sample of 120 games. The selected ratings span 1800–2388 and the PGN SHA-256 is `280c81787826e2827f84b444ef180d7528ec762f0eafacdada2d1426e34ca133`.

Sample 2,228 unique positions, balanced 1,102/1,126 by side to move, and label with Stockfish 18 at depth 12, MultiPV 1, one thread, and 16 MB hash. Exclude all 51 hashes previously observed in January, February, or March, leaving 2,177 April positions across all 120 games. Fit Material-only, Locked-3, and Full-16 only on the deduplicated 2,170-position January/February depth-8 development union. Apply the exact March two-ply/128-child Searched Locked-3 algorithm and use 1,000 paired source-game bootstrap samples.

### Result

| Candidate | Params | Overall MAE | Forcing MAE | Correlation | Sign | ≥500 cp |
|---|---:|---:|---:|---:|---:|---:|
| Material-only | 2 | 154.66 | 185.79 | 0.4392 | 69.55% | 4.27% |
| Locked-3 | 4 | 150.52 | 177.04 | 0.5128 | 69.50% | 3.40% |
| Full-16 | 17 | 145.74 | 173.67 | 0.5299 | 70.46% | 3.35% |
| Searched Locked-3 | 4 + search | **134.89** | **152.34** | **0.6364** | **71.15%** | **2.02%** |

The preregistered gate passes. Searched Locked-3 minus static Locked-3 forcing MAE is −24.53 cp with a 95% interval of [−30.26, −18.60]. Its overall improvement over Locked-3 is 15.50 cp [11.72, 19.09], and its overall improvement over Full-16 is 10.77 cp [4.49, 16.33]. Search expands 5.30 children per root on average (p95 19, maximum 46), never reaches the cap, and takes 2.19 ms/position in the current Python implementation.

### Interpretation

The deeper target raises absolute error for every formula, as expected, but the relative search gain remains large and statistically resolved. Within the tested domain and depth change, the March result is not a shallow-oracle artifact. A small selective forcing computation again provides more predictive value than thirteen additional static features, while using the compact formula rather than Stockfish at its leaves.

This remains evidence about position-value approximation. Because stand-pat can be preferred at the root, Searched Locked-3 is not yet a move predictor and has no measured playing strength.

### What failed

The first post-label validation command stopped before computing any metrics because the prior-position hash query attempted to iterate a DuckDB connection directly. Commit `f4819e3` changed the query to consume `fetchall()` and added a two-database regression test. The failure exposed no April metrics, changed no analysis choice, and the complete frozen protocol then ran successfully. The child cap again was not reached, and the Python timing remains descriptive rather than an optimized engine comparison.

### Next experiment

Freeze the accepted evaluator and build a deterministic legal-root-move wrapper. Preregister root enumeration, fixed computation budget, tie-breaking, oracle depth, top-1/top-k agreement, centipawn regret, legal coverage, and latency before accessing an untouched May human corpus. Use April only for implementation development; do not use it for the final move-policy claim.

## 2026-08-20 — Experiment 009: untouched May legal move-policy validation

### Hypothesis

A deterministic wrapper that evaluates every legal root move with frozen Searched Locked-3 achieves 100% legal coverage and lower mean clipped Stockfish regret than the equivalent static Locked-3 policy, with a 95% paired source-game-bootstrap interval excluding zero.

### Method

Commit the complete protocol at `0fd3c9b` before downloading May. Verify and stream the official CC0 May 2013 Lichess archive (179,550 games; 26,545,457 bytes; SHA-256 `f044607c9f565831524dbedfd474100c8604dba008600bfaf1b7a48ced74c17b`). From 11,013 eligible games, select a seed-20260827 reservoir sample of 120 games. The selected ratings span 1800–2301 and the PGN SHA-256 is `4d9f5f27bda163bde7f977868c3a6ac45cfa319af7c2faea49f93dcb85e2d9b1`.

Ingest 2,199 unique positions, balanced 1,093/1,106 by side to move, with zero parse errors. Exclude 68 hashes observed in January through April, leaving 2,131 positions across all 120 games. Fit coefficients only on the 2,170-position January/February depth-8 development union. Compare all-legal-root-move static Locked-3, static Full-16, and Searched Locked-3 policies with deterministic UCI-lexical tie-breaking. For Searched Locked-3, apply the unchanged two-ply forcing search with a 128-child budget separately after every root candidate.

Label roots using Stockfish 18 depth 12, MultiPV 3, one thread, and 16 MB hash. Evaluate policy choices outside the oracle's best move with root-move-constrained searches at the same depth/options. Clip best and chosen scores to ±2,000 cp, orient regret to the mover, clamp independent-search inversions to zero, and use 1,000 paired source-game bootstrap samples.

### Result

| Policy | Mean regret | Median | p95 | Top-1 | Top-3 | ≥100 cp | ≥300 cp |
|---|---:|---:|---:|---:|---:|---:|---:|
| Locked-3 | 312.96 | 282 | 784 | 15.81% | 24.92% | 66.87% | 48.33% |
| Full-16 | 274.46 | 206 | 742.5 | 17.03% | 27.73% | 61.38% | 41.53% |
| Searched Locked-3 | **125.02** | **61** | **456** | **24.12%** | **38.95%** | **38.06%** | **13.80%** |

Every policy has 100% legal coverage. The primary gate passes: Searched Locked-3 minus static Locked-3 mean regret is −188.08 cp with a 95% interval of [−199.93, −176.33]. The secondary contrast against Full-16 is −149.55 cp [−162.72, −136.38]. Search improves mean regret in opening, middlegame, endgame, forcing-proxy, and quiet-proxy strata.

The policy evaluates 34.34 legal root moves per position on average. Searched Locked-3 expands another 215.11 forcing children (p95 629.5; maximum 3,612 aggregated across candidates) and takes 90.00 ms/position in Python, versus roughly 10.3 ms for either static policy. The requested oracle set contains 4,000 unique position/move pairs: 592 root-best values and 3,408 constrained analyses.

### Interpretation

The compact searched evaluator now supports legal move choice, and its prospective move regret is dramatically better than either static formula's. Exact top-1 agreement remains only 24.12%, but top-3 agreement, regret, and large-mistake rates all move in the same direction. The result supports a compact formula plus selective computation rather than a static equation alone.

The accepted computational object is substantially larger than April's average five-child position evaluator: exhaustive root enumeration plus selective continuations inspects roughly 249 states per decision. That cost must accompany every claim. Move regret still does not measure Elo, clock handling, error accumulation over games, or opponent interaction.

### What failed

The first post-cache command stopped before computing or exposing metrics because the scorer omitted its already-loaded root-oracle map. Commit `0560b14` supplied the argument and added a regression test for root-best reuse and constrained-score retrieval. It changed no policy, cached oracle score, metric, threshold, or analysis choice. The accepted rerun used all cached constrained labels. Negative regret from independent root and forced searches occurred on 1.69% of searched-policy positions and was handled by the preregistered zero clamp.

### Next experiment

Expose the frozen Searched Locked-3 policy through a minimal UCI process. Before rated games, freeze a color-balanced, opening-paired match protocol with fixed resources, opponents/baselines, adjudication, timeout and illegal-move handling, and win-rate/Elo uncertainty. Validate UCI correctness and zero illegal moves before interpreting any game result as playing strength.
