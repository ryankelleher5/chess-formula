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

**Completed milestone — minimum transferable handcrafted subset:** January's 30-repeat nested procedure recovered only 25.3% of full-16's outer-fold MAE gain, but it prospectively locked `material + space + tempo` before confirmation. Trained only on January, that four-parameter evaluator achieved 142.85 cp MAE on 1,079 non-overlapping February positions versus 149.09 for material and 141.76 for full-16. It captured 85.2% of full-16's gain; its paired game-bootstrap improvement over material excluded zero, while full-16's remaining 1.10 cp advantage did not. The lock loses sign accuracy and is not a universal winner. Selection frequencies, nested held-out performance, source provenance, exact overlap exclusion, and confirmation intervals are recorded without tuning on February.

**Completed milestone — failure-directed compact rule discovery:** the frozen audit identified 157 candidates across 55 February games. Forcing positions comprise 90.1% of ≥300 cp errors versus 67.7% of the full set, while Full-16 still averages 537.3 cp error on those extremes. A separate 33-position/12-game cluster has a −3.62z passed-pawn imbalance. Diffuse pawn/activity clusters and a singleton were not promoted. A generated local HTML explorer now supports board-level review without changing the accepted confirmation result.

**Completed milestone — preregistered March compact-rule test:** on 2,184 non-overlapping positions from 120 untouched March games, the passed-pawn extension failed (+0.21 cp paired overall MAE, 95% interval [−1.20, +1.68]) and does not advance. Bounded two-ply forcing search passed: it improved forcing-stratum MAE by 26.65 cp [20.11, 33.45], lowered overall MAE from 132.45 to 115.91, raised correlation from 0.5933 to 0.7465, and halved ≥500 cp errors from 2.20% to 1.01%. It also beat static Full-16 by 9.86 cp MAE while expanding 5.04 child positions on average. The algorithmic search rules and computation—not only four fitted parameters—are part of its complexity.

**Completed milestone — deeper-oracle robustness gate:** on 2,177 non-overlapping positions from 120 untouched April games labeled at Stockfish depth 12, the unchanged Searched Locked-3 improved forcing-stratum MAE over static Locked-3 by 24.53 cp [18.60, 30.26]. It lowered overall MAE from 150.52 to 134.89, raised correlation from 0.5128 to 0.6364, and reduced ≥500 cp errors from 3.40% to 2.02%. It also beat static Full-16 by 10.77 cp overall [4.49, 16.33] while expanding 5.30 children on average. Thus the March search gain survives the tested oracle-depth shift; this remains position-value prediction.

**Completed milestone — legal move-policy bridge:** on 2,131 non-overlapping positions from 120 untouched May games, all policies achieved 100% legal coverage. Searched Locked-3 reduced mean clipped regret from 312.96 to 125.02 cp relative to static Locked-3, a paired 188.08 cp improvement [176.33, 199.93], and beat Full-16 by 149.55 cp [136.38, 162.72]. It raised top-3 agreement from 24.92% to 38.95% and cut ≥300 cp mistakes from 48.33% to 13.80%. This bridge evaluates 34.34 legal root moves and another 215.11 forcing children on average, so the search policy—not four coefficients alone—is the accepted object. The result measures move quality, not playing strength.

**Completed milestone — UCI playing-strength pilot:** the frozen policy completed 120 real UCI games with zero illegal moves, timeouts, crashes, or null moves. It scored 17-23-0 (71.25%) against both static Locked-3 and static Full-16, approximately +158 engine-pool Elo with paired intervals excluding zero. Against Stockfish 18 at 100 nodes/move it scored 0-9-31 (11.25%), approximately −359 pool Elo [−470, −285]. Candidate policy latency was 79–91 ms/move and it inspected 253–286 root/forcing states on average. Selective search produces genuine playing strength over static evaluation, but a large gap remains to highly efficient modern search. These are pool-specific estimates, not human FIDE Elo.

**Completed milestone — game-failure audit:** the frozen depth-12 audit labels all 957 candidate turns in the 31 Stockfish-100 losses. Every game has a persistent ≥150 cp error, with median selected regret 270 cp at ply 16. First-error continuations split across nine excluded quiet replies, five excluded pawn captures, nine quiet second plies, and eight beyond-two-ply lines. Stockfish's preferred replacement root is quiet in 29 games. The result is development-only and changes neither the formula nor any confirmation claim.

**Completed milestone — search-resource frontier:** on all 957 loss-game turns, the unchanged Searched-3 baseline has 130.45 cp mean depth-12 regret at 279.7 mean states. Forcing-3 lowers regret to 102.61 cp, a paired −27.84 cp difference [−39.59, −17.81], while using 1,074.8 states. Full opponent-reply breadth also qualifies at 106.48 cp but costs 2,303.7 states, so Forcing-3 wins the frozen cheapest-eligible rule. Pawn-capture breadth and full candidate-continuation breadth fail the 10% gate. This is development selection, not a confirmation claim; the formula is unchanged.

**Completed milestone — untouched Forcing-3 playing confirmation:** on 20 new reversed-color opening pairs with zero pilot overlap, Forcing-3 scored 14-24-2 against the accepted two-ply policy: 65.0% [58.75%, 72.5%], approximately +108 engine-pool Elo [+61, +168]. The frozen lower-bound gate passes with zero candidate faults or opponent forfeits. It scored 0-14-26 (17.5%) against Stockfish-100n; this is not directly comparable with the old pilot because the openings differ. The confirmed gain costs 1,099.4 versus 220.2 mean states and 329.1 versus 68.2 ms/move, ratios of 4.99x and 4.82x. Forcing-3 is now the accepted compact policy; the formula remains unchanged.

**Completed milestone — fixed-budget search-efficiency curve:** on 240 deterministic development positions, the confirmed Forcing-3 anchor has the lowest mean depth-12 regret: 105.05 cp at 1,360.9 mean states. Halving its cap saves only 11.4% of states and raises regret by 14.66 cp; Forcing-3-128 retains 76.02% of the anchor's gain, below the frozen 80% gate, despite scoring 51.25% [47.5%, 56.25%] in 40 direct games. Four forcing plies use 3,353.7 states and worsen regret to 123.09 cp. Across 160 development games there are zero faults. No cheaper policy advances, and Forcing-3 remains accepted.

**Active milestone — exact three-piece endgame laboratory:** freeze a complete, symmetry-audited census of legal king-and-rook-versus-king and king-and-queen-versus-king states with exact WDL and distance-aware optimal moves. Measure static Locked-3, accepted Forcing-3, and progressively compact exact-rule candidates by perfect WDL classification, optimal-move coverage, description length, states, and latency. Split by canonical symmetry or connected state component—not random positions—to prevent reflected or one-move-adjacent leakage. Preregister the state generator, legality filters, tablebase provenance, canonicalization, metrics, and advancement rule before inspecting candidate results. The goal is to learn how compactly perfect behavior can be represented in a solved domain, not to tune another approximate Stockfish imitation.
