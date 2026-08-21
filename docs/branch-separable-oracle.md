# Branch-separable oracle calibration

Experiment 018 asks whether ordinary branch labels stabilize when every legal
move receives its own independent constrained-root Stockfish search. They do
not stabilize enough under the frozen range. No training reference is selected
and compact branch-selector training remains blocked.

## Frozen design

The complete protocol was committed at `d552404` before any new Experiment 018
query. It reuses only the 24 root and 134 opponent-parent development contexts
frozen before Experiment 016, containing 5,259 legal branches per tier.

For every `(context, legal move)` independently, Stockfish 18 receives one
thread, 16 MB hash, a fresh game boundary, the move as its sole permitted root,
and exactly one of these node budgets:

- 2,500;
- 10,000;
- 40,000; or
- 160,000.

The 160,000-node endpoint is audit-only and cannot select itself. A cheaper
tier must pass the frozen root and parent gates against both its next tier and
the audit endpoint.

## Convergence toward the audit endpoint

The table reports opponent-parent agreement with the independent 160,000-node-
per-move audit.

| Independent tier | Top reply | Top-3 Jaccard | Within-25-cp Jaccard | 25-cp labels | Median regret difference |
|---|---:|---:|---:|---:|---:|
| 2,500 nodes/move | 61.19% | 55.82% | 63.29% | 94.15% | 46 cp |
| 10,000 nodes/move | 69.40% | 60.82% | 71.78% | 95.52% | 33 cp |
| 40,000 nodes/move | **76.87%** | **69.48%** | **77.69%** | **96.62%** | **22 cp** |

The 40,000-node tier passes the parent within-25-cp, threshold-label, and
median-regret gates, but fails top-reply agreement (76.87% versus 85%) and
top-3 Jaccard (69.48% versus 80%). At roots it passes top-move, top-3,
within-25-cp, 25-cp-label, 50-cp-label, and median-regret gates, but its
100-cp-label agreement is 88.66%, below 90%. Therefore it is not eligible.

## What independent allocation changed

Experiment 017's deepest per-reply tier nominally requested 40,000 nodes times
the legal-move count but allowed one all-legal MultiPV search to distribute the
shared total internally. Experiment 018's matched tier gives each move exactly
40,000 nodes in a separate call.

Those two nominally matched procedures agree on only:

| Metric | Root | Opponent parent |
|---|---:|---:|
| Top move | 83.33% | 76.12% |
| Top-3 set Jaccard | 75.42% | 68.73% |
| Within-25-cp set Jaccard | 79.50% | 75.66% |
| 25-cp label agreement | 95.73% | 96.11% |
| Median regret difference | 19 cp | 21 cp |

Thus compute allocation is not a minor implementation detail: it changes the
chosen opponent reply in 32 of 134 contexts at the same nominal per-move cost.
The median larger reciprocal regret among those changes is 38 cp and the
maximum is 1,145 cp. Neither allocation can be declared correct from this
comparison alone.

## Uncertainty structure

Comparing independent 40,000- and 160,000-node tiers gives a more useful
picture than a forced binary label:

- 31 of 134 opponent contexts change their top reply;
- 17 of those changed replies are mutually within 25 cp;
- 25 are mutually within 100 cp;
- the median larger reciprocal regret is 24 cp;
- the maximum is 1,049 cp.

At the 25-cp branch label, 343 parent moves are stable-important, 4,082 are
stable-unimportant, and 155 are ambiguous. The ambiguity rate is only 3.38%.
A conservative union that treats ambiguity as important retains 13.59% of
legal opponent replies on average. At roots, 35 moves are stable-important,
622 stable-unimportant, and 22 ambiguous; the conservative union retains
26.07% on average.

This is promising but not an advancement result. The audit endpoint is still a
finite selective search, and the conservative union is defined using outcomes
already observed here. It must be prospectively validated against a new,
deeper measurement before it can become a training target.

## Interpretation

The allocation hypothesis is only partially supported. Independent per-move
search removes sibling competition and materially changes the measurements,
but the top-reply and top-3 identities remain far below the frozen gates.
Search horizon inside each branch—not only allocation among branches—is a
binding source of oracle uncertainty.

This result reinforces the project's central distinction. The branch-law goal
is not necessarily to imitate one unstable top-1 label. It is to avoid omitting
any branch that could matter after more computation. A three-way target—stable
important, stable unimportant, and ambiguous—may better express that question,
provided its conservative union survives a genuinely new deeper audit.

## Integrity and reproducibility

- Contexts: 158 development-only.
- Legal branches per tier: 5,259.
- Independent oracle analyses: 21,036.
- New analyses: 21,036; cache replay adds zero.
- Models trained: zero.
- Selection outcomes probed: zero.
- Confirmation outcomes probed: zero.
- Oracle runtime: 1,581.15 seconds; total runtime: 1,583.54 seconds.
- Oracle cache SHA-256:
  `b66e0a017b807408dcda9c40bbc5eba1083decd2a31bfcbdd29c990c96c32d26`.
- Record SHA-256:
  `36b25327cc399ecb2d012b055c3278071f39d8c3bebcab2e4adcfe0ac9e43107`.
- Metrics SHA-256:
  `bcd926826a2c242f433d869fcc5003b81eca7eb0423d97df7ab1c95274021a28`.

Generated records, metrics, and the plot remain ignored by Git under
`results/2026-08-21_branch_separable_oracle_001/`.

## Decision and next experiment

The stability gate fails. Do not train a selector and do not retroactively
remove exact-rank criteria from Experiment 018.

Experiment 019 should preregister an **uncertainty-aware adjudication**. Freeze
the identities of all development contexts exhibiting a 40k-to-160k top-reply
change or 25-cp ambiguity, add SHA-selected stable controls, and evaluate every
legal move under a new deeper independent budget. Measure whether the frozen
40k/160k conservative union retains the new top reply and near-best set, its
catastrophic false-negative rate, and its retained branch fraction. Only a
prospective pass should license uncertainty-aware labels for later training.
