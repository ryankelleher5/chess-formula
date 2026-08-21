# Research Roadmap

The working cadence is **hypothesis → experiment → measurement → conclusion → next experiment**. Each phase has a question and an exit condition; later phases should not be started merely because they are technically appealing.

## Phase 0 — Trustworthy infrastructure

Build deterministic configuration, experiment IDs, structured records, benchmark versioning, environment capture, a CLI, and tests. **Exit:** a clean checkout can reproduce a recorded experiment.

## Phase 1 — Small position dataset

Ingest ordinary and compressed PGN streams, sample legal positions, preserve occurrences, deduplicate by rule-relevant state, and split at game level. **Question:** can the data lineage prevent obvious contamination? **Exit:** audited counts and stable splits.

## Phase 2 — Stockfish oracle

Cache resumable UCI labels using fixed depth, nodes, or time; record MultiPV, centipawn/mate/WDL values, depth, nodes, and engine identity. **Exit:** interrupted labeling resumes without recomputing completed work.

## Phase 3 — Frozen benchmark

Version a held-out set and progressively annotate opening, middlegame, endgame, tactical, quiet, imbalanced, king-exposed, closed, and open positions. Measure error, correlation, sign, move agreement, catastrophic errors, time, memory, parameters, and operations. Never silently change a benchmark.

## Phase 4 — Human-designed formula

Compare manual weights, least squares, ridge, and lasso on an explicit linear feature vocabulary. **Question:** what can a formula readable on one screen explain? **Exit:** formula, held-out metrics, and failure list.

## Phase 5 — Feature compression

Select 5, 10, 20, 50, and larger feature subsets and plot the Pareto frontier. **Question:** which judgment signals buy the most accuracy per term?

## Phase 6 — Primitive representation

Replace human concepts with occupancy planes and rule state. Train models at budgets from 100 to 1M parameters. **Question:** where does learned representation overtake handcrafted abstraction?

## Phase 7 — Latent structure

Constrain bottlenecks to dimensions 1, 2, 4, 8, 16, 32, and 64. Probe what evaluation and move information survives, without forcing human labels onto unexplained variables.

## Phase 8 — Symbolic discovery

Apply sparse polynomial regression, symbolic regression, expression search, genetic programming, and program synthesis to successful representations. Optimize chess quality minus a measured complexity penalty and publish the Pareto frontier.

## Phase 9 — Candidate invariants

Test clustering, contrastive representations, automated constructions, graph features, sparse latents, and valid board symmetries including reflection and color reversal. **Question:** what quantities generalize across visually different position classes?

## Phase 10 — Disagreement mining

Store and cluster positions where compact models sharply disagree with deep Stockfish. Attach evaluation gaps, moves, phase, material, king exposure, mobility, and tactical-depth proxies. Failures are discovery material, not merely bugs.

## Phase 11 — Iterative law discovery

Repeat: simplest model → catastrophic failures → clusters → compact explanatory rule → retrain → rebenchmark. Preserve the marginal contribution and description cost of every added rule.

## Phase 12 — Move policy

Separate evaluation from action. Compare direct policies, evaluators, hybrids, and shallow-search variants using top-k move accuracy and game outcomes.

## Phase 13 — Search efficiency

Wrap candidates in minimal minimax/alpha-beta at fixed 100, 1K, 10K, 100K, and 1M node budgets. Add iterative deepening, transpositions, quiescence, and selectivity only when an experiment needs them. Primary metric: playing strength per computation.

## Phase 14 — Engine matches

Expose candidates through UCI and estimate win/draw/loss rates, score, engine-pool Elo difference with confidence intervals, nodes, time, and memory against classical engines and constrained Stockfish. Do not call engine-pool estimates human FIDE Elo.

## Phase 15 — Exact endgame laboratory

Use solved 3-, 4-, then 5-piece domains to study how compactly perfect WDL and optimal moves can be represented. Exact domains separate oracle imitation from game-theoretic truth.

## Phase 16 — Careful scaling

Only after the laboratory produces useful evidence, expand to Lichess, high-level human and engine games, self-play, tactics, random legal states, and deliberately unusual positions. Scale diversity, not raw volume alone.

## Phase 17 — Adversarial positions

Search legal states that maximize compact-model error using mutations, evolution, Monte Carlo methods, or self-play. Feed recurring adversarial structures back into the law-discovery loop.

## Phase 18 — Minimum description length

Measure parameters, expression/source/executable size, operations, memory, latency, search nodes, predictive quality, and play. Produce the central figure: **description complexity → chess strength**.

## Phase 19 — Ultimate question

Only after the preceding evidence ask whether near-perfect chess may have a compact algorithm. Distinguish four plausible findings: broadly compressible chess; a steep complexity wall near optimality; compact principles plus rare search-heavy exceptions; or no meaningful compression. None constitutes a solution without proof.

## Immediate milestone

Phases 0–4 now support the first small-PGN linear experiment. Phase 5 has begun with a 30-repeat game-grouped comparison of 2-, 6-, and 17-parameter formulas. The compact-5 formula is the current Pareto candidate on synthetic data.

**Completed milestone — independent human-domain validation:** `human-transfer-v1` deterministically selected 60 rating-filtered games from the CC0 Lichess January 2013 archive and evaluated 1,091 unique balanced-side positions over 30 game-grouped resamples. Full-16 improved mean MAE by 9.42 cp and correlation by 0.0501 over compact-5 while reducing catastrophic errors from 3.58% to 2.47%. The synthetic compact-5 Pareto conclusion did not transfer. Provenance, source/license/checksums, integrity audits, phase strata, and a forcing-position proxy are recorded without changing `coefficient-stability-v1`.

**Active milestone — minimum transferable handcrafted subset:** use nested game-grouped feature selection on the January human corpus to identify the smallest subset that retains the full model's human-domain gain, then lock that subset before validating it on a second CC0 month. Do not choose features on the final confirmation month. Exit when a new complexity frontier reports selection frequency, nested held-out performance, and confirmation-domain performance without leakage.
