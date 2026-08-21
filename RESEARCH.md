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

## 2026-08-21 — Experiment 010: UCI playing-strength pilot

### Hypothesis

The frozen Searched Locked-3 policy can operate correctly through UCI with zero illegal moves, crashes, or timeouts, and a color-balanced opening-paired pilot can quantify its playing strength relative to static compact controls and constrained Stockfish without assuming a positive result.

### Method

Commit the UCI engine, referee, 20-opening suite, opponent pool, adjudication, resources, metrics, and decision rule at `badc98c` before any scored game. Confirm protocol behavior with an external `python-chess` handshake and an explicitly unscored short game. Then play every immutable eight-ply opening twice with candidate colors reversed against static Locked-3, static Full-16, and Stockfish 18 at 100 nodes per move: 40 games per opponent, 120 total.

The candidate retains the exact May formula, exhaustive legal-root enumeration, lexical tie-breaking, two forcing plies, and 128 expanded children per root candidate. Use a five-second UCI operation timeout, one Stockfish thread and 16 MB hash, claimable chess draws, a 160-total-ply draw cap, no evaluation adjudication, and immediate loss for an engine exception, timeout, live-position null move, or illegal move. Report 10,000-bootstrap intervals by complete reversed-color opening pair and logistic engine-pool Elo differences, explicitly not human FIDE Elo.

### Result

| Opponent | W-D-L | Score [95%] | Engine-pool Elo [95%] |
|---|---:|---:|---:|
| Static Locked-3 | 17-23-0 | 71.25% [63.75%, 78.75%] | +158 [+98, +228] |
| Static Full-16 | 17-23-0 | 71.25% [62.50%, 80.00%] | +158 [+89, +241] |
| Stockfish-100n | 0-9-31 | 11.25% [6.25%, 16.25%] | −359 [−470, −285] |

The protocol gate passes: all 120 games have zero candidate illegal moves, timeouts, crashes, and null moves. All generated PGNs parse without error. Candidate scores against each static control are 72.5% as White and 70.0% as Black. Against Stockfish they are 7.5% as White and 15.0% as Black; the candidate wins no game.

Candidate latency ranges from 79.22 to 90.94 ms/move across matches, with 253.05–285.93 reported legal-root-plus-forcing states per move. Static controls take 4.27–5.52 ms/move. Stockfish takes 0.78 ms/move and reports 107.62 nodes/move, although Stockfish nodes and candidate states are not equivalent operations. The complete run takes 355.94 seconds.

### Interpretation

Selective computation converts the same three-feature formula into a materially stronger player than static evaluation. The move-regret advantage survives complete-game interaction, both colors, repeated positions, and rule-based termination. Static Full-16 does not overcome the missing continuation search.

The 0-9-31 Stockfish result marks a steep efficiency and strength boundary. A modern alpha-beta/NNUE engine at only 100 nodes per move is far stronger while using less wall time. This does not isolate whether the compact engine is limited primarily by forcing-only move vocabulary, two-ply horizon, move ordering, static information, or Python implementation. Nominal node counts cannot answer that because the engines perform different work per node.

The +158/−359 estimates are conditional on 20 opening pairs, this resource control, and this opponent pool. They are neither universal ratings nor human FIDE Elo. The pilot is sufficient to establish direction and expose the next bottleneck, not to calibrate broad chess strength.

### What failed

No protocol failure occurred. One game against Stockfish reached the frozen 160-ply draw cap; all other games ended by checkmate, threefold repetition, or stalemate. Fresh UCI processes per game prevented state carryover but added startup overhead. The referee did not persist the probed Stockfish identity inside the generated metrics, although the invoked binary was independently verified as Stockfish 18; future reports should capture engine identity directly.

### Next experiment

Treat the 31 Stockfish losses as development-only failure data. Locate each game's first large irreversible swing and classify missed quiet moves, pawn captures, exchanges, king threats, and horizon failures. Hold the three-feature formula fixed while comparing a small search breadth/depth/resource frontier. Freeze any candidate and a new opening suite before confirmation, reporting both playing strength and state/wall-time costs.

## 2026-08-21 — Experiment 011: UCI loss audit

### Hypothesis

The first persistent large errors in the 31 Stockfish-100n losses can distinguish failures caused by excluded opponent replies, excluded candidate continuations, and the two-ply horizon without changing the accepted three-feature formula.

### Method

Commit the complete development-only audit at `6f0a83e` before analyzing the losses. Label every candidate turn after the frozen eight-ply opening with Stockfish 18 at depth 12, MultiPV 1, one thread, and 16 MB hash. Define a major error as at least 150 cp mover-oriented regret. Prefer the earliest such error that leaves the candidate at least 300 cp adverse and remains at least 300 cp adverse at its next turn; otherwise use the earliest major error, then maximum regret. Classify Stockfish's played-move principal variation against the exact accepted vocabulary of checks, promotions, non-pawn captures, and all check evasions.

### Result

The audit labels 957 candidate turns. Every loss has a first persistent major error: mean selected regret is 318.10 cp, median regret is 270 cp, and median error ply is 16. The selected games comprise 17 White and 14 Black candidate losses.

| Refutation class | Games |
|---|---:|
| Excluded quiet opponent reply | 9 |
| Excluded pawn-capture opponent reply | 5 |
| Visible reply, quiet candidate continuation | 9 |
| Visible forcing line beyond two plies | 8 |

Stockfish's preferred replacement root is quiet in 29 games, a pawn capture in one, and a non-pawn capture in one. All 31 selections satisfy the persistent rule; no fallback is used. Across all turns, 179 have at least 150 cp regret, mean zero-clipped regret is 142.10 cp, and median regret is 40 cp.

The independent root and constrained searches invert on 102 turns before zero-clipping, but the inversion magnitude is small: median 14 cp, 94 at most 50 cp, and maximum 74 cp. These do not approach the 150 cp major-error threshold. A cache-only replay retrieves all 957 labels with zero new Stockfish calls.

### Interpretation

The loss mechanism is not one missing tactical rule. Four similarly sized groups identify opponent reply breadth, omitted pawn captures, quiet candidate continuations, and horizon depth. Because every legal root is already enumerated, the 29 quiet Stockfish replacements indicate a discrimination problem inside the continuation search rather than an excluded root-move class.

The result is deliberately diagnostic. It reuses games selected by losing, has only 31 game-level units, and cannot establish a playing-strength improvement. The three-feature formula and all prior confirmation claims remain frozen.

### What failed

No execution or protocol failure occurred. Depth-12 root and forced analyses show the expected small independent-search noise. The taxonomy describes the first three principal-variation moves and cannot prove a unique causal explanation for a loss.

### Next experiment

Preregister a development search-resource frontier mapped directly to the four observed classes: pawn-capture breadth, all opponent replies, all candidate continuations after a forcing reply, and a third forcing ply. Compare mover-oriented depth-12 regret, exact move agreement, expanded states, and wall time on all 957 loss-game turns. Select at most one candidate by a frozen strength-per-compute rule, then lock it before any new opening-suite games.

## 2026-08-21 — Experiment 012: search-resource frontier

### Hypothesis

At least one audit-mapped search extension can reduce mean depth-12 move regret by 10% with a 31-game grouped-bootstrap interval excluding zero, and a frozen cheapest-eligible rule can distinguish useful computation from indiscriminate breadth while keeping the Locked-3 formula unchanged.

### Method

Commit the complete frontier at `a739e62` before running any policy comparison. Replay all 957 candidate turns from the 31 Stockfish-100n losses and require the forcing/forcing baseline to reproduce every recorded move. Compare it with four deterministic schedules: all captures at both internal plies, all opponent replies followed by forcing continuations, forcing replies followed by all candidate continuations, and three forcing plies. Use a 128-child per-root cap for baseline/all-captures and 256 for the broader/deeper policies. Allow stand-pat at forcing and all-captures nodes but require a legal move at all-legal nodes.

Score every distinct selected move with Stockfish 18 at depth 12, one thread, and 16 MB hash. Orient regret to the mover and clip scores to ±2,000 cp. Bootstrap complete games 5,000 times. An extension is eligible only if it improves mean regret by at least 10% and the regret-delta interval is below zero. Select at most one eligible extension by lowest mean total states, then lower regret, then lexical label.

### Result

| Policy | Mean regret | Delta [95%] | Top-1 | ≥300 cp | Mean states | ms/position |
|---|---:|---:|---:|---:|---:|---:|
| Searched-3 baseline | 130.45 | — | 28.63% | 8.88% | 279.7 | 86.3 |
| All-captures-2 | 127.07 | −3.38 [−7.34, −0.61] | 28.53% | 8.67% | 434.4 | 140.0 |
| All-opponent-replies-2 | 106.48 | −23.97 [−33.38, −15.76] | **31.35%** | 7.31% | 2,303.7 | 794.4 |
| All-candidate-continuations-2 | 128.42 | −2.03 [−6.76, +2.61] | 28.84% | 8.67% | 865.7 | 259.8 |
| **Forcing-3** | **102.61** | **−27.84 [−39.59, −17.81]** | 30.93% | **6.17%** | **1,074.8** | **332.5** |

Forcing-3 and all-opponent-replies qualify. Forcing-3 advances under the frozen rule because it uses less than half the mean states and also has lower regret. Its 21.34% mean regret improvement exceeds the gate; all-opponent-replies improves 18.37%. All-captures has a resolved but only 2.59% improvement, and all-candidate-continuations improves 1.55% with an interval crossing zero.

Baseline replay agreement is 100%. The 1,525 distinct oracle requests reuse 388 root-best and 683 actually played scores; 454 alternative moves require new constrained analyses. A cache replay performs zero new analyses. On the 31 selected first-error boards, Forcing-3 changes 14 choices and reduces mean regret from 318.10 to 195.45 cp.

### Interpretation

The loss audit's horizon signal transfers across all turns in those games more strongly and efficiently than either narrow capture expansion or an all-legal ply. A third selective ply is not cheap—it uses 3.84 times the baseline states and latency—but it lies on the observed development strength/compute frontier. Full opponent replies offer slightly better top-1 agreement but use 8.24 times the baseline states and 2.14 times the selected candidate's states.

This remains selection on games chosen for baseline losses. The bootstrap measures variation among those 31 games, not independent confirmation. It cannot establish a new playing-strength or generalization result.

### What failed

The two locally obvious breadth patches do not qualify. Including every capture changes only 43 of 957 choices and fails the 10% improvement threshold. Allowing all candidate continuations changes only 33 choices, has a regret interval crossing zero, and is slower than the all-captures policy. Forcing-3 reaches its 256-child cap in 146 positions and 490 legal-root searches, so its result is conditional on the frozen ordering and cap. The full sequential Python run takes 1,549.93 seconds.

### Next experiment

Lock Forcing-3 exactly as tested and expose it through UCI. Before scored play, freeze a new color-reversed opening suite that excludes all 20 pilot openings, direct comparison against the accepted two-ply policy and Stockfish-100n, fault/adjudication rules, paired score and engine-pool Elo intervals, and explicit state/wall-time reporting. Do not tune from confirmation games.

## 2026-08-21 — Experiment 013: untouched Forcing-3 UCI confirmation

### Hypothesis

The loss-derived Forcing-3 policy improves complete-game score over the accepted Searched-3 baseline on untouched opening pairs, with a 95% paired-bootstrap lower bound above 50%, while retaining perfect UCI reliability.

### Method

Commit the complete policy, UCI runner, opening suite, opponents, resources, and decision rule at `df7c2da` before any scored game. The candidate keeps the exact Locked-3 coefficients and adds a third forcing ply, tactical-first ordering, stand-pat outside check, and a 256-child budget separately for each legal root.

Use 20 new eight-ply openings with 20 unique final rule states, suite SHA-256 `a4a8b749d8ad5fbbb8c21f2a297caab4576e2d4659e94b5d22c93f57b9324e85`, and zero final-state or move-sequence overlap with the pilot suite. Play each twice with candidate colors reversed against Searched-3 and Stockfish 18 at 100 nodes per move: 40 games per opponent, 80 total. Preserve the five-second timeout, 160-ply cap, claimable draws, no evaluation adjudication, immediate fault forfeits, and 10,000 complete-opening-pair bootstrap samples.

Confirm only with zero candidate faults, zero opponent forfeits, and a primary score lower bound above 50% against Searched-3. Treat Stockfish as an external anchor without a threshold. Before scoring, an external Forcing-3 UCI handshake and an unscored six-ply game completed legally. One initial handshake assertion incorrectly required more reported states than legal roots in the start position; legal stand-pat can make the counts equal. Correcting that smoke-only assertion changed no engine, protocol, or scored data.

### Result

| Opponent | W-D-L | Score [95%] | Engine-pool Elo [95%] |
|---|---:|---:|---:|
| Searched-3 baseline | 14-24-2 | **65.0% [58.75%, 72.5%]** | **+108 [+61, +168]** |
| Stockfish-100n | 0-14-26 | 17.5% [10.0%, 25.0%] | −269 [−382, −191] |

The preregistered gate passes. Against Searched-3, candidate score is 62.5% as White and 67.5% as Black. Against Stockfish it is 10.0% as White and 25.0% as Black. All 80 games have zero candidate illegal moves, timeouts, crashes, or null moves and zero opponent forfeits. All 80 PGNs parse without error and match the JSON records. Terminations are 42 checkmates, 36 threefold repetitions, and two 160-ply draws.

Forcing-3 averages 1,099.37 states and 329.10 ms/move against Searched-3, versus 220.19 states and 68.24 ms for the baseline: 4.99x states and 4.82x latency. Against Stockfish, candidate averages rise to 1,418.62 states and 427.09 ms because the games and positions differ. The full run takes 1,229.29 seconds.

### Interpretation

The loss-derived move-regret improvement generalizes across a clean opening boundary and complete adversarial games. The same three-feature formula becomes substantially stronger through one additional selective ply. Forcing-3 therefore replaces Searched-3 as the accepted compact policy.

The result also quantifies a steep computational trade: approximately +108 pool Elo against the baseline costs about five times its work. This supports compact evaluation plus selective search, not a claim that strong chess is captured by the four fitted coefficients alone. Stockfish remains decisively stronger and roughly 500 times faster per move in this Python comparison, although its nodes are not equivalent to candidate states.

The 17.5% external-anchor score is numerically above the prior pilot's 11.25%, but the opening suites differ. It is therefore contextual evidence, not a direct paired improvement estimate. Neither pool Elo number is a human FIDE rating.

### What failed

No scored protocol failure occurred. Two games against Stockfish reached the 160-ply cap. The primary match contains only 20 opening pairs, so its interval remains conditional on this suite. The selected candidate reaches its per-root cap on development positions, and the confirmation does not isolate depth from the doubled cap. Pure-Python latency is unsuitable for conventional real-time engine play without optimization.

### Next experiment

Build a fixed-budget search-efficiency curve around the confirmed policy. Hold the formula fixed and preregister forcing-search depth/cap combinations spanning approximately 100, 300, 1,000, and 3,000 mean states per decision. Use the completed games only for development, then freeze a new opening suite for any playing-strength claim. Determine whether most of the third-ply gain survives at materially lower computation.

## 2026-08-21 — Experiment 014: fixed-budget search-efficiency curve

### Hypothesis

Most of the confirmed Forcing-3 move-quality gain can be retained at materially lower computation by reducing its per-root cap, while a deeper forcing point reveals whether quality continues to improve above the accepted policy.

### Method

Commit the complete development protocol at `605b78c` before exposing move-quality or game results. Hold the accepted `material + space + tempo` formula, legal-root enumeration, forcing vocabulary, ordering, stand-pat semantics, and lexical ties fixed. Compare Forcing-1-64, Searched-3, Forcing-3-128, the confirmed Forcing-3/256 anchor, and Forcing-4-256.

Select three SHA-ranked candidate turns from each of the 80 completed confirmation games, then deduplicate to 240 rule states. Label every root and distinct selected move with Stockfish 18 at depth 12. Measure regret and computation, grouping 5,000 bootstrap samples by opponent/opening color pair. Separately play each non-anchor point for 40 games against Forcing-3 on the completed 20-opening suite, reversing colors and using 10,000 opening-pair bootstrap samples. This completed-suite reuse is development only.

A cheaper point advances only if it retains at least 80% of the anchor's regret gain over Forcing-1-64, has at most +10 cp mean and +15 cp bootstrap-upper regret versus the anchor, scores at least 47.5% head-to-head with a lower bound of at least 40%, and remains fault-free. Select at most one by lowest mean states. The more expensive four-ply point cannot advance.

### Result

| Policy | Mean states | Mean regret | Score vs Forcing-3 [95%] |
|---|---:|---:|---:|
| Forcing-1-64 | 106.5 | 166.18 cp | 35.00% [28.75%, 41.25%] |
| Searched-3 | 372.2 | 144.02 cp | 35.00% [27.50%, 41.25%] |
| Forcing-3-128 | 1,206.2 | 119.70 cp | 51.25% [47.50%, 56.25%] |
| **Forcing-3** | **1,360.9** | **105.05 cp** | anchor |
| Forcing-4-256 | 3,353.7 | 123.09 cp | 46.25% [41.25%, 51.25%] |

Forcing-3-128 is game-competitive but not eligible. It retains 76.02% of the anchor's regret gain, raises mean regret by 14.66 cp, and has a 31.56 cp grouped-bootstrap upper bound; the frozen limits are 80%, 10 cp, and 15 cp. It saves only 11.4% of mean states and 10.5% of measured position latency. Forcing-4-256 uses 2.46 times the anchor's mean states and 2.42 times its latency while increasing mean regret by 18.04 cp.

All 160 games complete with zero illegal moves, engine errors, timeouts, and opponent forfeits. All PGNs parse and match the JSON result and ply records. The oracle creates 240 root and 330 forced-move labels at the frozen settings. The complete run takes 3,619.24 seconds.

### Interpretation

No cheaper policy passes all gates, so Forcing-3 remains the accepted compact policy. Direct game score alone would have promoted the half-cap variant, but the prospective position criteria reject that noisy shortcut. The small state saving does not justify its larger and uncertain regret increase.

More forcing-only depth is not monotonically useful. The four-ply point spends far more work and is worse on both mean regret and direct score. This suggests a selective-horizon effect: extending the same narrow move vocabulary can expose a new frontier without resolving the quiet positions beyond it. The result argues against treating raw depth or state count as a sufficient complexity-to-strength law.

This is negative development evidence, not a new strength estimate. The accepted Forcing-3 confirmation remains unchanged, as does the four-parameter formula.

### What failed

The primary compression candidate fails three position gates even though it passes both game gates. Searched-3 and Forcing-1-64 are clearly cheaper but score only 35% and retain too little regret gain. The saturation point fails to improve quality. Ninety-six of 240 positions bind at least one Forcing-3-128 root budget, compared with 33 for the anchor and 146 for Forcing-4, so every deep result remains conditional on tactical ordering and per-root truncation.

### Next experiment

Move to an exact three-piece endgame laboratory, beginning with king-and-rook versus king and king-and-queen versus king. Freeze a complete legal-state census, symmetry canonicalization, exact tablebase provenance, component-level splits, and perfect-WDL/optimal-move/description-length metrics before evaluating compact candidates. Use the solved domain to distinguish exact rule compression from finite-depth oracle imitation.

## 2026-08-21 — Research direction decision: Branch-Law Discovery

This is a prospective change in research priority, not an experiment and not a
reinterpretation of prior evidence. Experiments 001–014, their protocols and
conclusions, all frozen datasets and benchmarks, and the accepted Locked-3
formula and Forcing-3 policy remain unchanged.

### Motivation

Selective search produced much larger gains than adding static handcrafted
terms, but Experiment 014 showed that more forcing-only computation is not a
monotonic solution. Forcing-4-256 used 2.46 times the accepted policy's mean
states while increasing mean regret by 18.04 cp. Halving the Forcing-3 cap saved
only 11.4% of states and failed three position-quality gates. This points toward
the structure of branch selection rather than routine depth expansion.

The loss audit supplies a related clue but requires precise interpretation. The
policy already enumerated every legal root move. Stockfish's quiet preferred
replacement in 29 of 31 losses therefore indicates misranking caused by
incomplete continuation/refutation search, not omission of quiet roots. Branch
importance is expected to depend on node role, root candidate, path, depth, and
budget rather than only `(position, move)`.

### Adopted question

The central new question is whether a compact branch law can identify which
legal continuations cannot safely be ignored. The target is

```text
A(P) = Search using branch law B and evaluation law E
```

where the description and computation of both `E` and `B` count. Candidate
desirability, regret-bounded viability, root-decision consequence, opponent
refutation necessity, and value of information will be computed as distinct
label families before any shared target is chosen.

### Success metric

For retained branch fraction `rho`, define `DPR_25(rho)` as the fraction of root
decisions whose pruning-induced oracle loss is at most 25 cp relative to the
same frozen search with all legal branches. The north-star is `rho_95`, the
smallest nested budget reaching 95% preservation at that and every larger
budget. The first branch-law milestone succeeds only if an untouched,
game-grouped confirmation shows at least a 25% reduction in `rho_95` versus the
forcing baseline, at least 10% lower mean root regret at the forcing-equivalent
budget with a grouped interval excluding zero, 100-cp catastrophic omissions
noninferior within a one-percentage-point margin, a resolved improvement in
refutation recall, and no increase in total selector-plus-search computation.
Description size and inference cost remain part of candidate selection.

For exact domains, `rho_perfect` is the minimum retained fraction preserving
tablebase WDL on every confirmation state; distance-aware optimality is a
secondary stricter criterion.

### Program structure

Future work is organized around three programs:

1. **Evaluation Compression:** compact static judgment, primitive
   representations, latent structure, and symbolic evaluation laws.
2. **Branch/Search Compression:** branch labels and datasets, equal-budget
   baselines, compact and symbolic selectors, recursive selection, and
   catastrophic-omission mining.
3. **Exact Chess Compression:** exact evaluation and branch necessity in three-,
   four-, and five-piece solved domains, including transfer as domain size grows.

The exact-endgame milestone remains active as Program C and becomes the first
ground-truth calibration environment for the branch-label machinery. KRK and
KQK validate legality, canonicalization, and tablebase handling; KPK follows
promptly as the richer three-piece test.

### Immediate gate

Before training any branch selector, freeze the label taxonomy, context-aware
dataset schema, oracle limits, overlap controls, equal-budget baselines,
counterfactual procedures, `rho_95` calculation, safety metrics, and advancement
rule. Then build the development dataset and establish the random, forcing,
capture, Locked-3, oracle, and all-legal branch-budget curves. At most one compact
candidate may advance to an untouched confirmation. Recursive search follows
only after branch prediction itself passes.

The complete specification is recorded in
[`docs/branch-law-discovery.md`](docs/branch-law-discovery.md), and the roadmap
now represents the three programs without deleting the historical phase map.

## 2026-08-21 — Experiment 015: exact branch-law measurement foundation

### Hypothesis

Exact branch necessity and retained-fraction curves can be measured
reproducibly in solved three-piece domains without conflating pruning loss with
an evaluator's error, while keeping all exact selection and confirmation
outcomes sealed.

### Method

Commit the complete protocol, schemas, legal-state census, symmetry rules,
sample digests, tablebase file hashes, baseline orderings, budgets, and integrity
gates at `771610b` before probing any Syzygy outcome. Enumerate legal KQvK and
KRvK under all eight board symmetries and direction-preserving KPvK under file
reflection. Assign whole canonical classes by seeded SHA-256 to 60%
development, 20% selection, and 20% confirmation.

Label only the 5,000 lowest SHA-ranked nonterminal development states in each
domain. Probe WDL50 and DTZ50 for every legal successor. Compare deterministic
random, forcing, all-capture, Locked-3, and nondeployable oracle orderings at
nested budgets 1, 2, 3, 4, 5, 8, 16, and all legal moves. Primary exact quality
is retaining at least one WDL-optimal move; DTZ-optimal retention is secondary.

### Result

The run emits 15,000 unique canonical development states and 155,576 unique
state/move records. All census counts and sample digests reproduce, all one-ply
WDL recurrences pass, DTZ recurrence mismatches are zero, and both selection
and confirmation outcome-probe counts are zero.

| Domain | Mean legal | Budget-1 forcing WDL | Budget-1 Locked-3 WDL | Budget-1 random WDL | Forcing / Locked-3 `rho_95_wdl` |
|---|---:|---:|---:|---:|---:|
| KQvK | 13.03 | 93.76% | **97.60%** | 94.12% | 15.09% / **7.68%** |
| KRvK | 11.27 | 89.52% | **96.16%** | 92.87% | 17.59% / **8.87%** |
| KPvK | 6.81 | 77.08% | **88.36%** | 83.35% | 70.52% / **57.55%** |

At budget one, Locked-3 also has the highest deployable DTZ-optimal retention:
42.66% in KQvK, 34.46% in KRvK, and 69.56% in KPvK. The oracle preserves both
WDL and DTZ at budget one in every state, and every all-legal endpoint preserves
WDL.

### Interpretation

The measurement foundation works, and quiet static state information orders
exact branches more effectively than the forcing vocabulary at equal budget in
all three domains. This is not a learned branch law and cannot advance a
selector because all outcomes are development-only.

WDL preservation is also demonstrably coarse. Random budget-one retention is
already 83% to 94% because many sampled positions have multiple outcome-
equivalent legal moves. The natural forcing category retains only 6.95% to
26.41% of branches and preserves WDL in 11.72% to 59.72% of positions; lexical
budget fill explains much of its equal-budget score. Exact WDL remains a hard
safety endpoint, but branch discovery must retain distance-aware labels and the
ordinary pruning-induced-loss, catastrophic-omission, and refutation metrics.

### What failed

No protocol or recurrence gate failed. The scientific limitation is metric
saturation: perfect WDL preservation on a development sample does not imply
retention of the most informative or fastest-progress branch. The exact sample
also contains only three-piece domains and cannot establish transfer to
ordinary chess or larger solved domains.

### Next experiment

Freeze the ordinary-position, context-aware branch dataset and counterfactual
labeling procedure. Measure pruning-induced loss relative to the same all-legal
reference, candidate viability, opponent-refutation necessity, catastrophic
omissions, and total selector-plus-search cost. Establish random, forcing,
all-capture, and Locked-3 ordinary branch-budget curves before training any
compact selector. Keep every confirmation set and the exact selection and
confirmation partitions untouched.

## 2026-08-21 — Experiment 016: ordinary context-aware branch foundation

### Hypothesis

With every legal root candidate retained, opponent-reply importance can be
measured separately from root breadth, and compact outcome-blind orderings will
preserve root decisions and refutations better than random selection at equal
reply budgets.

### Method

Commit the complete source identities, counterfactuals, oracle limits, schemas,
baselines, budgets, and integrity gates at `05bc169` before any new branch-oracle
query. Reuse only the 240 positions already frozen as development in Experiment
014, grouped across 80 source games and 40 opening/opponent pairs. Make those
games permanently ineligible for a future Branch-Law confirmation claim.

Analyze all legal moves at each source root and at all 6,683 nonterminal
opponent-parent contexts using Stockfish 18, 20,000 nodes, all-legal MultiPV,
one thread, 16 MB hash, and a new-game boundary per context. The all-reply
reference keeps all 6,689 root candidates and gives each the opponent-optimal
reply score. An independent source-root analysis grades the absolute regret of
full and pruned decisions.

Compare random, forcing, all-captures, Locked-3, and oracle reply orderings at
budgets 1, 2, 3, 4, 5, 8, 16, and all. Label each reply by opponent regret,
single-reply candidate-value consequence, and root-decision consequence. Repeat
24 roots and 134 parent contexts at 80,000 nodes as a frozen stability audit.

### Result

The run emits 240 unique root records, 6,689 root-candidate records, and 217,973
opponent-reply records. All 224,662 branch identities are unique and
development-only. Cache replay performs zero new analyses. Every all-legal
endpoint reproduces the reference choice with zero pruning loss, and the oracle
ordering reproduces it at budget one. No model is trained; selection and
confirmation probe counts are zero.

| Ordering | Budget-1 `DPR_25` | Candidate-refutation recall | Mean pruning loss | >100 cp omission | `rho_95` |
|---|---:|---:|---:|---:|---:|
| random | 34.94% | 6.01% | 220.90 cp | 47.69% | 100.00% |
| forcing | 44.58% | 25.60% | 138.73 cp | 32.50% | 100.00% |
| all captures | 46.25% | 26.20% | 132.47 cp | 30.83% | 100.00% |
| **Locked-3** | **57.92%** | **47.26%** | **77.14 cp** | **20.83%** | 100.00% |
| oracle | 100.00% | 100.00% | 0.00 cp | 0.00% | 3.07% |

At budget 16, or 45.93% of replies, Locked-3 reaches 93.33% `DPR_25`
versus 88.75% for forcing. The dataset contains 4,008 >25 cp candidate
refutations, 209 >25 cp root-critical replies, and 41 forced sole replies. The
all-reply child reference itself averages 54.38 cp direct-oracle regret, which
is why pruning-induced loss is reported separately from absolute regret.

### Interpretation

There is real compact branch-ordering signal. At the same one-reply budget,
Locked-3 recalls 1.85 times as many candidate refutations as forcing and lowers
mean pruning loss by 44%. This repeats the exact-domain finding that static,
often quiet state information contains useful branch structure missing from the
forcing vocabulary.

No deployable baseline reaches partial-tree `rho_95`, so this is not a compact
branch law. The large oracle/deployable gap says better ordering could matter;
it does not establish that the ordering is compressible.

### What failed

The binding failure is label stability. Comparing the 20,000-node labels with
the preregistered 80,000-node audit gives only 79.17% top-move agreement at 24
roots and 55.97% top-reply agreement at 134 opponent parents. The corresponding
within-25-cp set Jaccards are 69.32% and 55.05%, and parent common-move scores
differ by 69.68 cp on average. A total-node MultiPV budget shared over an average
32.62 replies appears too noisy for hard rank and threshold targets. That causal
explanation remains a hypothesis, not a result of this experiment.

### Next experiment

Do not train the planned compact selector yet. Preregister an oracle-convergence
calibration on the frozen development contexts, comparing increased total-node
and per-legal-reply budgets with prospective top-set, regret-label, and cost
gates. Select the cheapest sufficiently stable reference before rebuilding
labels or defining model classes. Keep all selection and confirmation outcomes
sealed.

## 2026-08-21 — Experiment 017: ordinary branch-oracle convergence

### Hypothesis

Ordinary root and opponent-reply ranks and regret-threshold labels will reach a
reproducible plateau as Stockfish computation increases, permitting selection
of the cheapest stable development training reference.

### Method

Commit the complete sample, two compute curves, stability metrics, multi-part
gate, cost rule, and selection rule at `b5295e5` before any new Experiment 017
query. Reuse exactly the 24 root and 134 opponent-parent SHA-selected
development contexts from Experiment 016 and its frozen 20,000- and
80,000-node records.

Run Stockfish 18 with all-legal MultiPV, one thread, 16 MB hash, and a new-game
boundary per context. Compare fixed total budgets of 20,000, 80,000, 320,000,
and 1,280,000 nodes with per-legal-reply rates of 625, 2,500, 10,000, and
40,000 nodes. Require top-move, top-3, within-25-cp-set, threshold-label, and
median-regret stability for both root and parent contexts, plus agreement
between the two deepest cost-rule endpoints.

### Result

The run completes 1,264 analyses: 948 new and 316 exactly reused from
Experiment 016. Selection and confirmation probe counts and model count remain
zero.

Both cost curves improve with computation but fail to plateau. Against their
family maxima, the 320,000-total-node and 10,000-node-per-reply tiers preserve
the opponent top reply in only 70.90% and 74.63% of contexts; their within-25-cp
set Jaccards are 73.12% and 73.81%.

At the two deepest endpoints, mean context costs are comparable: 1,280,000
fixed nodes versus 1,331,392 nodes under the per-reply rule. Root top-move
agreement is 87.50% and opponent top-reply agreement is 83.58%. The latter is
the sole failure against the cross-rule gate's 85% boundary. Root and parent
within-25-cp set Jaccards are 95.14% and 89.66%; 25-cp per-move label agreements
are 99.41% and 98.80%; median regret differences are 0 and 1 cp.

### Interpretation

The hypothesis is rejected under the frozen budget range. No reference tier is
selected, and training remains blocked. Aggregate regret-threshold labels at
the deepest endpoints are much more stable than exact top replies, but the
gate cannot be changed after observing that result.

An explicitly exploratory disagreement audit finds that the deepest cost rules
choose different opponent replies in 22 contexts. Ten are mutually within 25
cp and 18 within 100 cp, but the largest reciprocal regret is 720 cp. The
instability is therefore partly near-tie behavior and partly material search
disagreement.

### What failed

Increasing shared all-legal MultiPV computation by another factor of four did
not make the reply rankings sufficiently reproducible. A shared total search
budget—even when scaled by legal-move count—still lets Stockfish distribute
effort unevenly across its MultiPV lines. The experiment cannot tell whether
the remaining disagreement is caused by insufficient horizon, internal
allocation, or both.

### Next experiment

Do not train a compact branch selector yet. Preregister a branch-separable
oracle calibration in which each legal move receives an independent
constrained-root node budget. Compare increasing per-move budgets and preserve
exact top replies, near-best sets, and conservative ambiguity labels as
separate outcomes. This should distinguish branch-value convergence from
shared MultiPV allocation effects while keeping every selection and
confirmation outcome sealed.

## 2026-08-21 — Experiment 018: branch-separable oracle calibration

### Hypothesis

Ordinary branch ranks and regret-threshold labels will stabilize when every
legal move receives an independent constrained-root computation budget,
removing shared MultiPV allocation as a source of disagreement.

### Method

Commit the complete protocol, 158-context and 5,259-branch identities, record
schema, per-move budgets, ambiguity accounting, stability gate, and selection
rule at `d552404` before any new Experiment 018 query. Analyze every legal move
independently with Stockfish 18, one thread, 16 MB hash, a new-game boundary per
branch, and exactly 2,500, 10,000, 40,000, or 160,000 nodes. Make the maximum
tier audit-only. A cheaper tier must pass against both its next tier and the
audit maximum.

### Result

The run completes all 21,036 independent branch analyses with no malformed or
missing records. All contexts are development-only; model, selection-probe, and
confirmation-probe counts remain zero.

Against the 160,000-node audit, opponent top-reply agreement rises from 61.19%
at 2,500 nodes to 69.40% at 10,000 and 76.87% at 40,000. At 40,000 nodes,
top-3 Jaccard is 69.48%, within-25-cp set Jaccard is 77.69%, 25-cp label
agreement is 96.62%, and median branch-regret difference is 22 cp. It fails the
85% top-reply and 80% top-3 gates. Roots pass those criteria but fail the frozen
100-cp label gate at 88.66%. No tier is eligible.

The matched allocation diagnostic compares independent 40,000-node-per-move
search with Experiment 017's shared MultiPV tier at the same nominal rate. They
agree on only 76.12% of opponent top replies, 68.73% of top-3 sets, and 75.66%
of within-25-cp sets. Their 25-cp per-move labels agree at 96.11%. Compute
allocation materially changes the oracle output but does not identify which
output is closer to chess truth.

### Interpretation

The hypothesis is rejected under the frozen compute range. Independent
allocation does not stabilize exact branch rankings enough for training.
Finite horizon within each forced branch remains a binding source of oracle
uncertainty.

The uncertainty is nevertheless structured. Between 40,000 and 160,000 nodes,
343 opponent replies are stable-important at 25 cp, 4,082 are stable-
unimportant, and 155 are ambiguous, a 3.38% ambiguity rate. A conservative
union retains pooled `rho = 10.87%` of parent replies, or 13.59% when context
fractions are equally weighted. Thirty-one contexts change their
top reply; 17 changes are mutually within 25 cp and 25 within 100 cp, but the
maximum reciprocal regret is 1,049 cp. Thus ambiguity includes both near ties
and rare material search discoveries.

### What failed

Equalizing computation among sibling branches removes one confound but not the
deeper one: Stockfish still performs finite selective search inside each forced
branch. The exact top reply and top-three set continue changing well beyond the
tested lower budgets. The audit endpoint cannot validate itself, and the gate
cannot be relaxed after observing more favorable threshold-label agreement.

### Next experiment

Do not train a branch selector yet. Preregister an uncertainty-aware
adjudication using every development context with a 40k-to-160k top-reply
change or 25-cp ambiguity plus SHA-selected stable controls. Analyze all legal
moves at a new deeper independent budget. Test prospectively whether the
already frozen conservative union retains the new top reply and near-best set,
its catastrophic false-negative rate, and its branch fraction. Only a pass may
license uncertainty-aware labels for a later training experiment.

## 2026-08-21 — Experiment 019: uncertainty-aware branch adjudication

### Hypothesis

The unchanged conservative union of the independent 40,000- and 160,000-node
within-25-cp labels will contain every important branch under a new independent
640,000-node-per-move audit while preserving substantial branch compression.

### Method

Commit the complete protocol, implementation, source checksums, frozen
555-branch union and its digests, metrics, and firm advancement gate at
`1ec7aea` before any new oracle query. Give every one of 5,259 legal moves in
all 158 frozen development contexts its own Stockfish 18 constrained-root
search of exactly 640,000 nodes. Measure exact top recall, complete
within-25-cp-set recall, decision preservation, 100/300-cp false-negative
consequences, and retained branch fraction. Probe no selection or confirmation
outcome and train no model.

### Result

The strict gate fails. Root top recall is 95.83%, within-25-cp micro recall is
83.67%, and complete-set recall is 91.67%. Opponent-parent top recall is
90.30%, within-25-cp micro recall is 78.40%, and complete-set recall is 84.33%.
The union therefore does not contain every newly important branch and cannot
license training.

Decision-level performance is substantially stronger. All 24 roots retain an
audit-co-best move, producing zero pruning loss. At opponent parents, 133 of
134 contexts retain a move within 25 cp. It retains 498 of 4,580 parent
branches, pooled `rho = 10.87%`; the equally weighted mean-context fraction is
13.59%. The union has 0.47 cp mean loss, zero median loss, one 31-cp miss, and
no loss over 100 or 300 cp. The sole unsafe context is preserved under key
`parent:6116f207af30ada6658fc7c13d679690732de0981eabac4a1498cfa8b93470fd`:
the audit selects `c7d7`, while the best retained reply `c7b7` is 31 cp worse.

### Interpretation

Reject the literal completeness hypothesis and keep the frozen gate failed.
The result nevertheless supplies strong evidence that exact near-best-set
recovery and decision-sufficient branch recovery are different targets. Deep
search can place many moves inside a 25-cp band; omitting some of them often
has no effect when an equally good retained move remains. This is evidence for
compression under a finite Stockfish audit, not a learned branch law and not
proof of chess truth. It is also not a deployable selector, recursive-tree
experiment, or measurement of final root-decision preservation.

### Next experiment

Do not train yet and do not add a handcrafted exception for the missed move.
Preregister Experiment 020 as a population-level test of whether value
trajectory across computation budgets identifies branches deserving further
work. Freeze the generic 10k/40k/160k temporal union across all contexts and
audit every legal move at 2.56M nodes. Make decision sufficiency primary and
complete-set recall diagnostic. Only a new frozen pass may reopen compact
selector training.
