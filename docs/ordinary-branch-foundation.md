# Ordinary context-aware branch foundation

Experiment 016 establishes the first ordinary-position branch-budget curve. It
finds a useful compact signal, but it also finds that the frozen 20,000-node
all-legal MultiPV labels are not stable enough to justify training a branch
selector yet.

## Scope

The protocol and implementation were committed at `05bc169` before any new
branch-oracle query. The source is the 240 development-only positions frozen in
Experiment 014, grouped across 80 completed games and 40 opening/opponent pairs.
Every legal root candidate remains available. Only the opponent replies visible
when valuing each candidate are varied.

Stockfish 18 analyzed all legal moves in 240 root contexts and 6,683
nonterminal opponent-parent contexts at 20,000 nodes, one thread, and 16 MB
hash. The result contains:

- 240 source-root records;
- 6,689 root-candidate records;
- 217,973 opponent-reply records; and
- 224,662 total context-aware branch records.

All records are development-only. No model was trained, and no selection or
confirmation outcome was probed.

## Equal-budget result

The budget-one point retains one reply in every nonterminal candidate context,
or 3.07% of all legal opponent replies.

| Ordering | `DPR_25` | Candidate-refutation recall | Root-critical recall | Mean pruning loss | >100 cp omission |
|---|---:|---:|---:|---:|---:|
| random, 20 repeats | 34.94% | 6.01% | 12.70% | 220.90 cp | 47.69% |
| forcing | 44.58% | 25.60% | 45.45% | 138.73 cp | 32.50% |
| all captures | 46.25% | 26.20% | 45.45% | 132.47 cp | 30.83% |
| **Locked-3** | **57.92%** | **47.26%** | **66.03%** | **77.14 cp** | **20.83%** |
| oracle reference | 100.00% | 100.00% | 100.00% | 0.00 cp | 0.00% |

At budget 16, retaining 45.93% of replies, Locked-3 reaches 93.33% `DPR_25`
with 6.25 cp mean pruning loss. Forcing reaches 88.75% with 16.58 cp loss;
all-captures reaches 89.58% with 14.62 cp loss. No deployable ordering reaches
the preregistered 95% threshold at a tested partial budget, so their development
`rho_95` is 1.0. The oracle reference has `rho_95 = 0.0307`.

The natural, unfilled forcing category retains 8.66% of replies and recalls
65.84% of >25 cp candidate refutations. Adding every capture raises retention
to 12.15% and recall to 70.41%. These category figures are branch recall only;
contexts with no selected reply prevent a clean root-decision comparison
without adding stand-pat evaluator error.

The dataset contains 4,008 >25 cp candidate-refutation replies, 209 replies
whose individual omission causes >25 cp root-decision loss, and 41 structurally
forced sole replies.

## What the result means

Locked-3 substantially outperforms forcing at the same tiny branch budget. Its
budget-one candidate-refutation recall is 1.85 times forcing's, and its mean
pruning loss is 44% lower. This independently supports the exact-domain clue:
quiet static state information contains branch-importance signal that the
checks/promotions/selected-captures vocabulary misses.

The result is not a compact branch law. Locked-3 is an existing evaluator, and
even it misses more than half the important candidate refutations at budget
one. No deployable ordering achieves partial-tree `rho_95`. The gap between
Locked-3 and the oracle reference shows that a better ordering could matter,
but it does not show that such an ordering is compressible.

The all-reply reference itself averages 54.38 cp absolute regret under the
independent root oracle. Experiment 016 therefore grades branch removal by the
*incremental* regret it causes; it does not claim the frozen child-context
minimax is globally optimal play.

## Oracle stability limitation

The preregistered 4×-node audit is the binding result:

| Context | Sample | Top-move agreement | Mean score difference | Within-25-cp set Jaccard |
|---|---:|---:|---:|---:|
| root | 24 | 79.17% | 42.36 cp | 69.32% |
| opponent parent | 134 | **55.97%** | **69.68 cp** | **55.05%** |

The 20,000-node budget is shared across all legal MultiPV lines, averaging 32.62
replies per opponent context. The observed instability is consistent with each
line receiving too little search, although Experiment 016 does not isolate the
cause. Training on these hard ranks or 25-cp labels would risk learning oracle
budget noise.

The baseline curve remains a valid result for the frozen 20,000-node reference,
but it is not a sufficiently stable target for model selection or
confirmation. No candidate advances.

## Integrity and reproducibility

- All 6,923 base contexts and 158 stability contexts are cached under oracle
  identity `a8fa5945837679976a48`.
- Cache replay performs zero new oracle analyses.
- All 240 root hashes are unique.
- All 224,662 `(root, role, candidate, move)` identities are unique.
- Every emitted record has partition `development`.
- Every all-legal endpoint reproduces the all-reply decision with zero pruning
  loss.
- Oracle ordering at budget one reproduces every all-reply decision.
- Selection outcomes probed: zero.
- Confirmation outcomes probed: zero.
- Runtime: 286.44 seconds.
- Root-record SHA-256:
  `4bdeedc319c6316af0c0e94f94ec7e29f6bf9cb2dac11746abfc99a665e5d633`.
- Branch-record SHA-256:
  `30c5598a488c1eacf6f132b97d23b82a88b49e0f0f9b90c1fb71e1eb77199c7c`.

Generated records and plots remain ignored by Git in
`results/2026-08-21_ordinary_branch_foundation_001/`.

## Decision and next experiment

The ordinary measurement foundation passes; model training remains blocked by
label instability. Experiment 017 should preregister an oracle-convergence
calibration over the already frozen development contexts. Compare increasing
total-node and per-legal-reply budgets, measure rank and threshold-label
stability, and select the cheapest reference that meets a prospective stability
gate. Do not train a branch selector, inspect confirmation data, or expand move
categories until that gate passes.
