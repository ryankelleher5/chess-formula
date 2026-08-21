# Research Roadmap

The working cadence remains **hypothesis → frozen experiment → measurement →
conclusion → next experiment**. The project now organizes future work around
three mutually informing research programs rather than treating engine
development as a single linear ladder. The chronological evidence remains in
[`RESEARCH.md`](RESEARCH.md); completed experiments and their contemporaneous
conclusions are never rewritten.

## Preserved foundation

Experiments 001–016, all frozen benchmarks and datasets, the reproducibility
infrastructure, Git history, and generated artifacts remain valid. The accepted
evaluation law remains `material + space + tempo`, and Forcing-3 remains the
accepted policy until an independently frozen experiment replaces it.

The central object is now

```text
A(P) = Search using branch law B and evaluation law E
```

The scientific target is not merely a better engine. It is the smallest
description of `E`, `B`, and the resulting examined tree that preserves strong
or perfect chess decisions.

## Program A — Evaluation Compression

**Question:** how much chess judgment can be represented statically?

This program contains the existing handcrafted formulas and their transfer
tests, primitive occupancy representations, tiny learned evaluators, latent
bottlenecks, symbolic evaluation laws, disagreement mining, and adversarial
evaluation counterexamples. Every candidate is measured by predictive or move
quality together with parameters, source/serialized size, operations, memory,
and latency.

## Program B — Branch/Search Compression

**Question:** how little of the game tree must actually be examined?

This program contains the accepted forcing search, formal branch-importance
labels, context-aware `(position, legal move)` datasets, equal-budget baselines,
compact learned selectors, recursive selection, symbolic branch laws, and
catastrophic-omission mining. It does not automatically promote conventional
engine mechanisms merely because they increase Elo.

The north-star is

```text
rho_95 = minimum fraction of legal branches required to preserve at least
         95% of root decisions within 25 cp of the full reference
```

Reports must also show the complete retained-branch fraction versus decision-
quality curve, catastrophic omission rates, refutation recall, and total
selector-plus-search complexity. See the dedicated
[`Branch-Law Discovery specification`](docs/branch-law-discovery.md).

## Program C — Exact Chess Compression

**Question:** how compactly can mathematically perfect behavior be represented
in solved domains?

This program starts with complete KRK and KQK enumeration to validate legality,
symmetry, and tablebase machinery, then moves promptly to the richer KPK domain,
followed by four- and five-piece domains. It measures exact WDL preservation,
distance-aware move optimality, exact branch necessity, description length, and
transfer as domain size grows. Its branch north-star is `rho_perfect`, the
minimum retained fraction that preserves tablebase-perfect play on every
confirmation state.

## Shared controls and convergence

- Split ordinary data by complete source game and audit rule-state, sequence,
  and valid-symmetry overlap.
- Split exact domains by canonical symmetry class or connected component, not
  random individual positions.
- Keep selection and confirmation domains separate until hypotheses, models,
  and advancement gates are committed.
- Treat larger neural models as diagnostic instruments rather than final laws;
  attempt to compress any successful predictor.
- Count both evaluation and branch-selector description and inference cost.
- Prefer experiments that reveal structure over engineering improvements with
  no generalizable explanatory value.
- Preserve negative results and mine catastrophic false negatives as discovery
  material.

The programs may converge if the same compact quantity predicts evaluation,
branch necessity, and exact play across different representations and oracles.

## Immediate execution order

1. **Completed in Experiment 015:** freeze the branch-label taxonomy,
   context-aware dataset schema, exact oracle limits, symmetry-class split
   rules, exact metrics, and advancement boundaries.
2. **Completed in Experiment 015:** validate complete exact enumeration and
   development labels in KQvK, KRvK, and KPvK without probing exact selection
   or confirmation outcomes.
3. **Completed in Experiment 016:** build the ordinary-position development
   dataset with candidate and opponent-refutation counterfactuals while probing
   no selection or confirmation outcome.
4. **Completed in Experiment 016:** establish random, forcing, capture,
   Locked-3, oracle, and all-legal opponent-reply baselines at equal budgets.
5. **Completed in Experiment 016:** measure the first ordinary development
   `rho_95` curve. All deployable baselines require the all-legal endpoint under
   the frozen reference; the oracle requires 3.07%.
6. **Completed in Experiment 017:** calibrate the branch oracle on 158 frozen
   development contexts across four fixed-total and four per-legal-reply
   budgets. The stability gate fails; no training reference is selected.
7. **Completed in Experiment 018:** give each of 5,259 legal development
   branches an independent 2,500-to-160,000-node constrained-root search. The
   40,000-node tier reaches only 76.87% opponent top-reply agreement with the
   audit endpoint, so no training reference advances.
8. **Completed in Experiment 019:** audit the unchanged 555-branch 40k/160k
   conservative union against independent 640,000-node searches of all 5,259
   legal branches. The literal complete-recall gate fails. Nevertheless, the
   union preserves a within-25-cp reply in 133 of 134 opponent contexts while
   retaining pooled `rho = 10.87%` of replies (13.59% mean-context fraction),
   with one 31-cp miss and no loss over 100 cp.
9. **Completed in Experiment 020:** audit the frozen 10k/40k/160k temporal
   union against independent 2.56M-node searches of all 5,259 branches. It
   retains pooled `rho = 11.66%` of parent replies and preserves a within-25-cp
   reply in 133 of 134 parent contexts, but one genuinely late-emerging branch
   causes a 61-cp loss. The frozen gate fails; no selector discovery is
   licensed.
10. **Current — Experiment 021 draft awaiting preregistration review:** move
    branch-law calibration to KPKP exact-domain ground truth. The draft makes
    five-valued WDL preservation the absolute safety condition, uses DTZ and
    unique-saving strata to prevent equivalence saturation, predicts at least
    one optimal branch rather than every redundant optimum, and keeps exact
    selection and confirmation outcomes technically sealed. No new tablebase
    outcome is authorized until the outcome-free census, manifests, metrics,
    candidate caps, and final protocol are reviewed and committed.
11. Train compact ordinary-position selectors only after an exact-domain or
    alternative-oracle experiment supplies a separately frozen training
    license.
12. Test recursive selection only after branch prediction itself passes.

## Historical phase map — preserved

The original phase map is retained below as project lineage. It no longer sets
future priority where it conflicts with the three-program structure.

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

## Completed evidence and active gate

The summaries below preserve the sequence that motivated the research fork.

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

**Completed milestone — exact branch-law measurement foundation:** Experiment 015 labels 15,000 deterministic development states and 155,576 legal branches across KQvK, KRvK, and KPvK with zero WDL/DTZ recurrence failures and zero selection or confirmation probes. At one retained move, Locked-3 preserves exact WDL in 97.60%, 96.16%, and 88.36%, beating forcing in all three domains. Random already reaches 94.12%, 92.87%, and 83.35%, showing that WDL alone saturates because many legal moves are outcome-equivalent. The natural forcing category preserves WDL in only 59.72%, 55.00%, and 11.72%; equal-budget fill supplies much of its apparent performance. This is a validated measurement baseline, not a learned law or confirmation claim.

**Completed milestone — ordinary context-aware branch foundation:** Experiment 016 emits 240 root records and 224,662 context-aware branch records while retaining every legal root candidate and varying only opponent replies. At the 3.07% budget-one point, Locked-3 reaches 57.92% `DPR_25`, 47.26% candidate-refutation recall, and 77.14 cp mean pruning loss; forcing reaches 44.58%, 25.60%, and 138.73 cp. No deployable ordering reaches 95% decision preservation at a partial tested budget. The 4×-node audit finds only 55.97% opponent top-reply agreement and a 55.05% within-25-cp set Jaccard, so no model is trained or advanced.

**Completed milestone — branch-oracle convergence:** Experiment 017 runs 1,264 analyses on the frozen 24 root and 134 opponent-parent development contexts. At comparable deepest mean cost, fixed-total and per-legal-reply allocation agree on 87.50% of root moves but only 83.58% of opponent top replies, missing the frozen 85% cross-rule gate; all other cross-rule criteria pass. The penultimate-to-maximum opponent top-reply agreements are only 70.90% and 74.63%, so neither curve has plateaued. No reference is selected and no model is trained. The next calibration isolates every legal move under its own compute budget.

**Completed milestone — branch-separable oracle calibration:** Experiment 018 completes 21,036 independent constrained-root analyses across four budgets and 5,259 legal branches per tier. The 40,000-node tier agrees with the 160,000-node audit on only 76.87% of opponent top replies and has 69.48% top-3 Jaccard, so the frozen gate fails. Its 25-cp labels agree in 96.62% of parent branches, leaving 155 ambiguous moves; treating those conservatively retains pooled `rho = 10.87%` of parent replies, or 13.59% when context fractions are equally weighted. Matched independent and shared 40,000-node allocation agree on only 76.12% of parent top replies, confirming allocation matters but does not explain all instability. No model is trained; uncertainty-aware labels require a new deeper adjudication.

**Completed milestone — uncertainty-aware branch adjudication:** Experiment 019 audits the frozen 555-branch 40k/160k union with 5,259 new independent 640,000-node searches across all 158 development contexts. The strict gate fails: root/parent top recall is 95.83%/90.30%, and within-25-cp recall is 83.67%/78.40%. Yet local reply decision preservation is 100.00% at roots and 99.25% at opponent parents. The union retains pooled `rho = 10.87%` of parent replies; its equally weighted mean-context fraction is 13.59%. It has 0.47 cp mean loss, one 31-cp miss, and zero losses over 100 or 300 cp. This expensive oracle-built set is neither deployable nor recursive and does not measure final root decisions. The result does not license training; it motivates a prospective distinction between complete near-best-set recovery and decision-sufficient branch recovery.

**Completed milestone — temporal computation-allocation adjudication:** Experiment 020 audits the frozen 594-branch 10k/40k/160k temporal union with 5,259 new independent 2.56M-node searches. Roots preserve a co-best branch in every context. Opponent parents retain pooled `rho = 11.66%` (14.39% mean-context fraction) and preserve a within-25-cp reply in 133 of 134 contexts, but the sole miss costs 61 cp and fails the frozen maximum-loss gate. The omitted `a4c6` branch was 124, 59, and 69 cp behind at the three selector checkpoints before becoming best at 640k and 2.56M. Previous computational promise is therefore useful but insufficient as a complete allocation law. No model is trained or licensed; the Stockfish budget ladder ends and the next calibration moves to exact-domain or alternative-oracle truth.
