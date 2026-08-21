# Experiment 019 — uncertainty-aware branch adjudication

## Question and frozen protocol

Experiment 019 asks whether the unchanged conservative union of the
independent 40,000- and 160,000-node labels from Experiment 018 contains every
important branch under a new, substantially deeper oracle. The complete
protocol, implementation, source identities, 555-branch union, metrics, and
advancement gate were committed at `1ec7aea` before any 640,000-node query.

The audit gives every one of 5,259 legal moves in all 158 frozen development
contexts an independent Stockfish 18 search of exactly 640,000 nodes. The
union retains a move only when its mover-oriented regret was at most 25 cp at
40,000 or 160,000 nodes. No move was added after viewing the new audit.

## Result

The frozen gate **fails**. The union does not literally contain every audit
top move or every move within 25 cp of the audit best. It therefore does not
license branch-label training.

| Context | Mean retained | Top recall | Within-25 recall | Decision preserved within 25 cp | Maximum loss | Losses >100 / >300 cp |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Root (24) | 26.07% | 95.83% | 83.67% | 100.00% | 0 cp | 0 / 0 |
| Opponent parent (134) | 13.59% | 90.30% | 78.40% | 99.25% | 31 cp | 0 / 0 |

At roots, the selector misses one exact top move and eight of 49 moves in the
full within-25-cp sets, but every context retains an audit-co-best move: mean,
median, and maximum pruning loss are all zero.

At opponent parents, it misses 13 exact top moves and 116 of 537 moves in the
full within-25-cp sets. Most omissions are redundant near-equivalent moves.
The retained set still contains an audit move within 25 cp in 133 of 134
contexts. Its mean pruning loss is 0.47 cp, median loss is zero, and maximum
loss is 31 cp. There are no losses over 100 or 300 cp.

The sole decision-level false negative is
`parent:6116f207af30ada6658fc7c13d679690732de0981eabac4a1498cfa8b93470fd`.
The 640,000-node audit prefers `c7d7`; the best frozen-union reply is `c7b7`,
31 cp worse. This counterexample is preserved unchanged for the next
experiment.

## Interpretation

The literal hypothesis is rejected: the 40k/160k union is not a complete set
of all branches later judged important. The preregistered gate remains failed
even though the practical decision result is much stronger than the exact-set
metrics.

This difference matters. Deep search sometimes places many legal moves inside
a narrow 25-cp band. Failing to retain every member of that band is not the
same as failing to retain enough information to choose safely. Experiment 019
therefore supplies evidence for substantial branch compression—especially at
opponent nodes—but not yet for a deployable branch law. The evidence is finite
Stockfish agreement, not proof that no still-deeper continuation changes the
answer.

The union also materially outperforms either source tier alone on decision
consequences. The 40k-only parent selector has three losses over 25 cp, one
over 100 cp, and a maximum loss of 114 cp. The 160k-only selector has two
losses over 25 cp, one over 100 cp, and a maximum loss of 136 cp. Their union
reduces this to one 31-cp miss while remaining below the frozen 20% mean parent
branch budget.

## Decision and next experiment

- Do not train a model from these labels.
- Do not redefine Experiment 019's gate after observing the result.
- Preserve exact-set recall and decision sufficiency as separate scientific
  outcomes.
- Preregister Experiment 020 around the 31-cp counterexample and frozen stable
  controls. Test whether the miss persists under a deeper or cross-oracle
  audit and whether a compact, prospectively defined uncertainty signal can
  recover decision-sufficient branches without manually adding the missed
  move or a chess-specific category.
- Only after that prospective gate should compact selector training be
  reconsidered.

## Reproducibility

- Result artifact: `results/2026-08-21_uncertainty_adjudication_001`
- Frozen code revision: `1ec7aeab93ff61e5a4573bc3f7284b057d8b0748`
- Oracle identity: `43d86c38843962f27cc6`
- Metrics SHA-256: `13108ab6053108850e6a3d27384315c206dc70b7033910c0486bf529c0b8ceac`
- Record/cache SHA-256: `b87dd167cf6d7c321eae56dde7fb32e9ab216b77be6b017a21ac01d6abcb1d75`
- Cache-metadata SHA-256: `a099e8c4ad98efab40463dddfe4e1e61a8f72835bb101d50674962ee744cf45b`
- Cached replay: 5,259 hits, zero new analyses
- Models trained: zero
- Selection outcomes probed: zero
- Confirmation outcomes probed: zero
