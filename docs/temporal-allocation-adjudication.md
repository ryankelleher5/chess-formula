# Experiment 020 — temporal computation-allocation adjudication

## Question and frozen protocol

Experiment 020 asks whether a branch's value trajectory across independent
computation budgets identifies branches that must receive further computation.
The generic candidate retains a move when it was within 25 cp of the best move
at any 10,000-, 40,000-, or 160,000-node checkpoint.

The complete protocol, implementation, source identities, 594-branch temporal
union, metrics, and decision-sufficiency gate were committed at `a64f17a`
before any 2,560,000-node query. The audit gives every one of 5,259 legal moves
in all 158 frozen development contexts its own independent Stockfish 18 search.
No model was trained and no selection or confirmation outcome was inspected.

## Result

The frozen gate **fails**. The temporal union preserves a move within 25 cp in
all 24 root contexts but only 133 of 134 opponent-parent contexts. Its maximum
parent pruning loss is 61 cp, exceeding the frozen 25-cp limit. Compact
selector discovery is therefore not licensed.

| Context | Pooled retained | Mean-context retained | Decision preserved within 25 cp | Mean loss | Maximum loss | Losses >100 / >300 cp |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Root (24) | 8.84% | 26.42% | 100.00% | 0.00 cp | 0 cp | 0 / 0 |
| Opponent parent (134) | 11.66% | 14.39% | 99.25% | 0.66 cp | 61 cp | 0 / 0 |

The diagnostic parent metrics are 91.04% exact-top recall, 70.21%
within-25-cp micro recall, and 79.10% complete within-25-cp-set recall. These
were prospectively declared diagnostics rather than advancement vetoes.

## Late-emerging counterexample

The sole decision-level failure is
`parent:d995ce6f9bebaf70a1c7e52cbbaac6f48d3c15177db9defb7cff9ee91d3f84d2`.
The omitted branch is `a4c6`; the best retained branch at 2.56M nodes is
`c5c6`.

| Independent budget | Best move | `a4c6` regret | `c5c6` regret | `f4e5` regret |
| ---: | --- | ---: | ---: | ---: |
| 2.5k | `c5c6` | 154 cp | 0 cp | 14 cp |
| 10k | `c5c6` | 124 cp | 0 cp | 15 cp |
| 40k | `f4e5` | 59 cp | 23 cp | 0 cp |
| 160k | `c5c6` | 69 cp | 0 cp | 1 cp |
| 640k | `a4c6` | 0 cp | 22 cp | 14 cp |
| 2.56M | `a4c6` | 0 cp | 61 cp | 98 cp |

This is not an exception to patch into a selector. It is evidence that a
branch can look consistently unpromising at every frozen early checkpoint and
become materially important only under much greater computation. Adding the
10k checkpoint fixes Experiment 019's 640k miss elsewhere, but it does not
solve late emergence in general.

## Interpretation

The tested law—previous near-best membership implies continued
computation—contains real signal but is insufficient as a complete allocation
law. It compresses opponent branches to pooled `rho = 11.66%` and is locally
decision-sufficient in 99.25% of sampled parents, yet the preregistered target
was 100% with maximum loss at most 25 cp.

This remains local opponent-reply calibration of an expensive oracle-built
set. It is not a deployable selector, recursive tree reduction, final
root-decision preservation, or a refutation of branch compression generally.
It specifically rejects this temporal-union rule under the tested finite
Stockfish path.

## Frozen consequence

Do not add another Stockfish node tier, relax the gate, hand-add `a4c6`, or
train a compact ordinary-position selector. Experiment 020 was preregistered
as the final deeper calibration on this Stockfish-only path.

Move the next branch-law experiment to exact-domain ground truth, with
alternative-oracle validation retained as a later cross-check. Exact
tablebases remove finite-search horizon from the label and can answer which
branches are mathematically necessary. The next protocol should use complete
game-group or symmetry isolation, keep selection and confirmation sealed, and
test whether any compact allocation signal transfers beyond the already
measured three-piece domains.

## Reproducibility

- Result artifact: `results/2026-08-21_temporal_allocation_adjudication_001`
- Frozen code revision: `a64f17a67bf2cc4342e24efd65e9101d8ef4c62c`
- Oracle identity: `35a573cf6f68157628e6`
- Complete analyses: 5,259
- Oracle runtime: 15,947.93 seconds
- Metrics SHA-256: `998089a35295a27fa9782a145bd6799fa62fd15702dc985643fbc577ed19d87e`
- Record/cache SHA-256: `53fca392f9b6316f8e91f665c785897933bbc23b121dbe2cda9701e7fb3558c8`
- Cache-metadata SHA-256: `790693050812d7055b781072ad632d74c33670720c7336df63ea225cdfdfe849`
- Cached replay: 5,259 hits, zero new analyses
- Models trained: zero
- Selection outcomes probed: zero
- Confirmation outcomes probed: zero
