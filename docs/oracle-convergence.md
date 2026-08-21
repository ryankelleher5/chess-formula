# Ordinary branch-oracle convergence

Experiment 017 tests whether the ordinary branch labels from Experiment 016
become stable as Stockfish receives more computation. The answer is **not yet**:
the preregistered stability gate fails, so no training reference is selected
and compact-selector training remains blocked.

## Frozen design

The protocol was committed at `b5295e5` before any new Experiment 017 query.
It reuses exactly 24 root and 134 opponent-parent development contexts selected
before Experiment 016. No selection or confirmation outcome is inspected.

Stockfish 18 analyzes every legal move with one thread, 16 MB hash, all-legal
MultiPV, and a new-game boundary per context. The two frozen compute curves are:

| Cost rule | Tiers |
|---|---|
| Fixed total nodes | 20,000; 80,000; 320,000; 1,280,000 |
| Nodes per legal reply | 625; 2,500; 10,000; 40,000 |

The second rule requests the listed rate times the legal-move count. Its tiers
therefore average 20,803; 83,212; 332,848; and 1,331,392 nodes per context. The
deepest fixed-total tier averages 1,280,000 nodes, making the two deepest
endpoints similar in mean cost while distributing that cost differently.

## Convergence toward each family maximum

The table reports opponent-parent stability against the deepest endpoint in
the same family. The family maximum compared with itself is omitted.

| Tier | Top-reply agreement | Top-3 Jaccard | Within-25-cp Jaccard | Median regret difference |
|---|---:|---:|---:|---:|
| total 20,000 | 55.97% | 52.76% | 57.68% | 60.0 cp |
| total 80,000 | 67.91% | 60.82% | 68.54% | 37.0 cp |
| total 320,000 | 70.90% | 66.79% | 73.12% | 26.0 cp |
| per-reply 625 | 55.22% | 51.79% | 57.42% | 55.0 cp |
| per-reply 2,500 | 65.67% | 61.57% | 67.82% | 40.0 cp |
| per-reply 10,000 | 74.63% | 66.72% | 73.81% | 26.0 cp |

Both curves improve with computation, but neither reaches a plateau by its
penultimate tier. From 320,000 to 1,280,000 fixed nodes, the opponent's top
reply still changes in 39 of 134 contexts. From 10,000 to 40,000 nodes per
reply, it changes in 34 of 134.

## Deepest cross-cost-rule check

The strongest comparison asks whether the two deepest, similarly priced
endpoints agree when computation is allocated differently.

| Metric | Root contexts | Opponent-parent contexts | Frozen gate |
|---|---:|---:|---:|
| Top-move agreement | 87.50% | **83.58%** | at least 85% |
| Top-3 set Jaccard | 95.83% | 86.72% | at least 80% |
| Within-25-cp set Jaccard | 95.14% | 89.66% | at least 75% |
| 25-cp label agreement | 99.41% | 98.80% | at least 90% |
| 50-cp label agreement | 98.97% | 98.65% | at least 90% |
| 100-cp label agreement | 99.71% | 98.28% | at least 90% |
| Median regret difference | 0.0 cp | 1.0 cp | at most 25 cp |

Only opponent top-reply agreement fails the cross-rule gate: 112 of 134
contexts agree, while the frozen 85% boundary requires at least 114. This is a
near miss numerically, but it cannot be waived after seeing the result. More
importantly, the much weaker penultimate-to-maximum comparisons show that the
curves themselves have not stabilized.

## Interpretation

The negative result is useful. Most regret-threshold labels at the two deepest
endpoints agree, but the identity of the single best reply remains sensitive to
how Stockfish spends a comparable amount of computation. Exact top-1 labels are
therefore still unsafe training targets.

An exploratory post-result audit helps separate harmless ties from material
changes. The deepest cost rules disagree on 22 opponent top replies. In 10 of
those, each chosen reply is within 25 cp under the other allocation; in 18,
both are within 100 cp. The median larger reciprocal regret is 36 cp, but the
maximum is 720 cp. Thus some disagreement is near-equivalence, while some is
large enough that it cannot be dismissed as tie noise. This audit does not
alter the frozen gate or create a new training target.

This supports the project's central caution: finite Stockfish search is an
instrument, not chess truth. Increasing raw compute helps, but all-legal
MultiPV also decides internally how to distribute that compute across moves.
The current data cannot distinguish remaining search horizon from that
allocation effect.

## Integrity and reproducibility

- Oracle analyses: 1,264 across eight tiers and 158 contexts.
- New Experiment 017 analyses: 948.
- Exact Experiment 016 records reused: 316.
- Models trained: zero.
- Selection outcomes probed: zero.
- Confirmation outcomes probed: zero.
- Oracle runtime: 687.78 seconds; total runtime: 690.15 seconds.
- Oracle cache SHA-256:
  `d1667f9cecca41d624a6d47f6ec012e9f298864c57847408f2aa81c6c1a977ee`.
- Metrics SHA-256:
  `eeb15c4f0939e4b360db508e7b4e44ef1e93c6ad2c297bd460cd386bc545cb20`.
- Cache replay performs zero new oracle analyses.

Generated metrics and the convergence plot remain ignored by Git under
`results/2026-08-21_oracle_convergence_001/`.

## Decision and next experiment

The gate fails. Do not train on the 20,000-node, 80,000-node, or newly computed
labels, and do not retrospectively replace exact top-reply stability with the
more favorable aggregate label metrics.

The next calibration should test **branch-separable oracle computation**:
analyze each legal move independently with a frozen constrained-root node
budget, rather than asking one all-legal MultiPV call to divide a shared budget.
Compare increasing per-move budgets, exact top replies, near-best sets, and
conservative ambiguity labels. Freeze that protocol before making any new
query. This directly tests whether the instability comes from insufficient
depth, internal MultiPV allocation, or both.
