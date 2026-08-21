# Branch-Law Discovery research specification

## Status

This direction is adopted after completion of Experiment 014, the frozen
fixed-budget search-efficiency curve. It changes future priorities without
changing any previous protocol, result, accepted policy, dataset, benchmark,
artifact, or conclusion.

The accepted evaluation law remains

```text
E(P) = 6.709046
     + 75.698112 material(P)
     + 13.073405 space(P)
     + 70.024384 tempo(P)
```

The accepted playing policy remains Forcing-3 until an independently frozen
experiment replaces it. Branch-Law Discovery does not retroactively reinterpret
its confirmation.

## Central question

Can a compact law identify the small fraction of the chess game tree that must
be examined to preserve strong or perfect decisions?

The target algorithm is

```text
A(P) = Search using branch law B and evaluation law E
```

Evaluation compression asks how small `E(P)` can be. Branch compression asks
how small both `B` and the tree selected by `B` can be. Exact compression asks
the same questions in solved domains.

## Context-dependent branch importance

The simple notation `B(P, m)` is a useful headline, but it is not the complete
experimental object. A move can be irrelevant as a global candidate and still
be essential as a refutation of one particular parent move. Importance can
also vary with remaining depth and branch budget.

Initial datasets and models must therefore support

```text
B(P, m | node role, root candidate, path context, remaining depth, budget)
```

This does not require every first model to use every field. It prevents the
dataset from discarding context before experiments can determine whether that
context is necessary.

The existing loss audit must also be described precisely. Every legal root move
was already enumerated, including quiet moves. The finding that Stockfish's
preferred replacement root was quiet in 29 of 31 audited losses shows that the
continuation search often misranked quiet candidates; it does not show that the
quiet root candidates were absent. The branch-law question is especially acute
at internal reply and continuation nodes.

## Branch-importance definitions

No single label is assumed to be correct in advance. The first experiment must
compute and compare the following label families wherever the oracle budget
permits.

### A. Candidate desirability

A legal move is positive when the reference oracle ranks it in its top 1, top
3, or top 5. These are simple and reproducible labels, but they measure global
move desirability rather than branch necessity.

### B. Regret-bounded viability

For side-to-move-oriented value, define

```text
R(P, m) = V(P, m*) - V(P, m)
```

with signs oriented so that nonnegative regret is worse for the mover. Record
labels at 10, 25, 50, and 100 cp. Preserve raw and clipped oracle scores and
record oracle inversions separately.

### C. Root-decision consequence

A branch is consequential when excluding it changes the selected root move or
increases root regret beyond a frozen threshold. This is a counterfactual label
over a retained set, not an intrinsic property of one move.

### D. Refutation necessity

At an opponent node, a reply is a refutation when omitting it makes its parent
candidate appear materially better than it is. Store the parent/root candidate,
the value with all reference replies, the value with the reply removed, and the
resulting root decision consequence.

### E. Value of information

Measure how revealing a branch changes root evaluation or move ordering. This
can be continuous and set-dependent. It is an exploratory label until a later
protocol freezes a particular estimator.

Candidate viability and refutation necessity must be reported separately before
any experiment attempts a shared label or shared model.

## Dataset unit and lineage

The basic record is a legal transition plus its search context, not merely a
position:

```text
(source position, context, legal move, successor position, oracle evidence)
```

Each record should retain at least:

- source and successor FENs and rule-state hashes;
- legal move, side to move, source/destination squares, and changed squares;
- source game, occurrence, ply, phase, and dataset split;
- root candidate, path moves, node role, remaining depth, and branch budget;
- oracle rank, evaluation, regret, top-k and regret-threshold labels;
- counterfactual root-decision and refutation labels when computed;
- oracle engine, version, limit, depth, nodes, hash, threads, and cache key;
- representation version and label-definition version.

Split ordinary positions by complete source game before model fitting. Audit
exact rule-state, move-sequence, and valid-symmetry overlap across splits. Keep
all existing confirmation datasets untouched. Exact domains must split by
canonical symmetry class or connected state component rather than random
individual positions.

## Representations

The discovery representation should make few chess-theory assumptions:

- piece occupancy before and after the move;
- raw occupancy planes by color and piece identity;
- source, destination, and changed-square encodings;
- attack and defense maps before and after;
- legal-move sets before and after;
- ray, blocker, and pairwise-distance relationships;
- local board geometry around changed squares;
- material occupancy, side to move, castling, en-passant, and promotion state.

Human concepts such as check, capture, promotion, pin, fork, passed pawn, and
king safety remain useful named baselines or probes. They must not be the only
inputs to the discovery model.

## Baselines

Every first-milestone comparison uses equal retained-branch budgets and includes:

- deterministic random-k with repeated or analytic uncertainty;
- the current forcing rule: checks, promotions, selected captures, and evasions;
- checks plus all captures and promotions;
- current Locked-3 successor ranking;
- oracle top-k as a nondeployable upper reference;
- all legal moves as the full-reference endpoint.

Selector inference cost counts toward total computation. Stockfish work used to
create labels does not count as deployable selector cost, but it must be recorded.

## Primary metric

For a selector and branch budget, let `S(P)` be the retained branches and `L(P)`
all legal branches. Selectors produce a deterministic ordering; tested budgets
retain nested top 1, 2, 3, 4, 5, 8, 16, and all-legal sets with lexical tie
resolution. The measured retained fraction is

```text
rho = sum_P |S(P)| / sum_P |L(P)|
```

The full reference uses the same frozen evaluator, horizon, terminal rules, and
search semantics while retaining all legal branches. An external frozen oracle
scores both its root choice and the choice produced by the pruned search. Define
pruning-induced root loss as

```text
L_branch(P) = max(0, oracle_regret(pruned choice)
                     - oracle_regret(full-reference choice))
```

This isolates information lost through branch removal from errors already made
by the evaluator or finite horizon. Absolute oracle regret for both choices must
also be reported. Define decision preservation at 25 cp as

```text
DPR_25(rho) = mean_P [L_branch(P) <= 25 cp]
```

The north-star scalar is

```text
rho_95 = minimum tested rho for which DPR_25(rho) >= 95% at that budget
         and every larger nested budget
```

Lower `rho_95` is better. Its reciprocal is an interpretable branch-compression
factor, but reports must show the complete branch-retention curve rather than
only the scalar. Requiring the threshold to hold at all larger budgets prevents
a single non-monotonic point from defining success.

The current project has no measured `rho_95`; Experiment 014 measured move
regret against expanded states, not systematic retained-branch fractions. The
first branch-budget experiment establishes the forcing baseline.

## Safety and complexity guardrails

The north-star cannot stand alone. Every candidate must also report:

- mean and percentile absolute root regret and pruning-induced loss;
- catastrophic branch-omission rates at 100 and 300 cp pruning-induced loss;
- candidate top-1/top-3/top-5 and 10/25/50/100-cp viability recall;
- opponent-refutation recall;
- positions preserving every labeled necessary branch;
- mean and distribution of retained branches and recursive states;
- learned parameters, serialized and source size, operations, memory, latency;
- oracle instability and label disagreement where available.

Top-1 agreement is secondary because several legal moves can be equivalent.
ROC accuracy is secondary because class imbalance can conceal rare catastrophic
false negatives.

## First-milestone advancement rule

The first milestone asks whether compact information predicts branch importance
substantially better than the current forcing heuristic. A candidate advances
to recursive testing only if an untouched, game-grouped confirmation shows all
of the following:

1. `rho_95` is at least 25% lower than the forcing baseline, and the grouped-
   bootstrap 95% upper bound for the candidate/baseline ratio is below 1.0;
2. at the forcing-equivalent retained-branch budget, mean root regret is at
   least 10% lower and the grouped-bootstrap 95% interval for the regret
   difference excludes zero in the improving direction;
3. the grouped-bootstrap 95% upper bound for the change in 100-cp catastrophic
   omission rate is no more than a one-percentage-point noninferiority margin;
4. opponent-refutation recall is higher at the same branch budget and its
   grouped-bootstrap 95% interval excludes zero in the improving direction;
5. selector inference plus retained-tree computation does not exceed the
   forcing baseline's total measured computation; and
6. model description, inference operations, and latency are completely
   reported and the candidate lies on the observed description/quality Pareto
   frontier.

The selection stage may advance at most one candidate by lower `rho_95`, then
lower catastrophic omission, then smaller measured description. Failure to
qualify is a valid negative result. Exact confirmation data and ordinary-game
confirmation data remain untouched until the candidate and gate are committed.

## Exact-domain metric

For tablebase domains, replace the 25-cp tolerance with exact outcome
preservation:

```text
rho_perfect = minimum branch fraction preserving tablebase WDL on every
              confirmation state
```

Report distance-to-zero or distance-to-mate optimality as a stricter secondary
criterion. KRK and KQK validate enumeration, symmetry, and label machinery.
KPK follows promptly because wins, draws, promotion races, opposition, and
zugzwang provide a more discriminating three-piece branch problem.

## Execution order

1. Preserve Experiments 001–014 and the accepted formula and policy.
2. Freeze label definitions, context schema, oracle limits, split rules, and
   branch-budget metrics before inspecting predictive results.
3. Validate enumeration and labels in KRK/KQK, then add KPK as the first richer
   exact three-piece domain.
4. Construct the ordinary-position development branch dataset without touching
   confirmation games.
5. Run random, forcing, capture, Locked-3, oracle, and all-legal baselines.
6. Produce the first `rho -> decision quality` curve and establish `rho_95`.
7. Fit only compact initial models: logistic/sparse linear, a small decision
   tree, and at most one modest nonlinear diagnostic model if justified.
8. Freeze at most one candidate and an untouched confirmation protocol.
9. Apply branch selection recursively only after the selector itself passes.
10. Use larger learned models only as scientific instruments, then attempt
    pruning, distillation, sparse rules, symbolic regression, expression search,
    or program synthesis.
11. Mine and cluster catastrophic false negatives after every compact law.
12. Test cross-depth, cross-engine, and exact-domain transfer only after a law
    has genuine held-out evidence.

## Anti-goal

Do not introduce sophisticated alpha-beta enhancements, large transposition
systems, killer/history heuristics, NNUE-scale evaluators, large opening books,
ordinary-play tablebase lookup, or expanding handcrafted move categories merely
because they improve Elo. A mechanism may be tested when a frozen experiment
needs it to isolate a question. Strength that adds complexity without revealing
generalizable structure is not the primary objective.

## Breakthrough discipline

Ordinary Elo or regret improvements are not breakthroughs. A result becomes a
potentially fundamental finding only with evidence such as dramatic branch
collapse without decision collapse, compact symbolic approximation of a larger
predictor, recurrence across independent representations, transfer across
oracles and exact domains, persistence as solved-domain size grows, and
resistance to adversarial counterexample search.

The first required visualization is the complete

```text
fraction of branches retained -> decision quality preserved
```

curve, accompanied by a board-level explorer for catastrophic omitted branches.
