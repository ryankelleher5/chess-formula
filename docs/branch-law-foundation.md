# Exact branch-law measurement foundation

Experiment 015 completes the development-only measurement foundation for
Branch-Law Discovery. It does not fit or select a branch law, and it does not
inspect either frozen selection or confirmation outcomes.

## Scope

The protocol was committed at `771610b` before any Syzygy outcome was probed.
It completely enumerates legal KQvK, KRvK, and KPvK states, canonicalizes valid
board symmetries, assigns complete canonical classes to development, selection,
or confirmation, and then labels a deterministic 5,000-position development
sample from each domain.

The run produced 15,000 exact states and 155,576 legal-move records. Every
record is from the development partition. Local Syzygy WDL50 and DTZ50 files
matched the frozen byte counts and SHA-256 manifest identity
`1c2834ba4a2bd62f2408a9c48cc4f183aa7451df21651948fcb51c97110b4c8f`.

## Equal-budget result

The table below reports the single retained-move point. The retained fraction
differs by domain because their mean legal-move counts differ. `WDL kept` asks
whether the retained move preserves the exact root WDL; `DTZ-optimal kept` is
the stricter secondary test of whether it retains a WDL-optimal move with best
measured DTZ.

| Domain | Mean legal | Ordering | Retained fraction | WDL kept | DTZ-optimal kept |
|---|---:|---|---:|---:|---:|
| KQvK | 13.03 | random | 7.68% | 94.12% | 36.45% |
| KQvK | 13.03 | forcing | 7.68% | 93.76% | 32.78% |
| KQvK | 13.03 | Locked-3 | 7.68% | **97.60%** | **42.66%** |
| KRvK | 11.27 | random | 8.87% | 92.87% | 27.47% |
| KRvK | 11.27 | forcing | 8.87% | 89.52% | 27.88% |
| KRvK | 11.27 | Locked-3 | 8.87% | **96.16%** | **34.46%** |
| KPvK | 6.81 | random | 14.67% | 83.35% | 59.88% |
| KPvK | 6.81 | forcing | 14.67% | 77.08% | 61.80% |
| KPvK | 6.81 | all captures | 14.67% | 80.12% | 64.84% |
| KPvK | 6.81 | Locked-3 | 14.67% | **88.36%** | **69.56%** |

The nondeployable oracle retains a WDL- and DTZ-optimal move at budget one in
every state, as required. All-legal retains one in every state for every
ordering.

At the preregistered 95% WDL threshold, Locked-3 requires 7.68% of branches in
KQvK, 8.87% in KRvK, and 57.55% in KPvK. The forcing ordering requires 15.09%,
17.59%, and 70.52%, respectively. These are discrete development-sample
measurements, not confirmation estimates.

## Main scientific result

Primitive branch importance is measurable reproducibly, and a three-term
static evaluator orders exact branches better than the current forcing rule at
the same one-move budget in all three domains. That is evidence that apparently
quiet state information matters to branch selection. It is not yet evidence
for a new compact branch law because Locked-3 is an existing evaluator, no
selector was learned, and no held-out outcomes were exposed.

The experiment also reveals that exact WDL preservation is too coarse to stand
alone as a discovery target. Random budget-one retention is already 83% to 94%
because many sampled states have multiple WDL-equivalent legal moves. The
natural forcing category itself retains only 6.95% to 26.41% of branches and
preserves WDL in only 11.72% to 59.72% of states; its much higher equal-budget
score often comes from lexical budget fill, not the forcing category. DTZ
optimality separates the orderings more strongly, but remains secondary under
the frozen protocol.

The ordinary-position north-star therefore remains unchanged: pruning-induced
centipawn loss relative to the same all-legal reference, summarized by
`rho_95`, with catastrophic-omission and opponent-refutation guardrails. Exact
WDL remains a hard safety endpoint, while DTZ and later exact-distance labels
must accompany it.

## Integrity

- Expected complete censuses and development sample digests reproduced.
- Exactly 15,000 unique canonical state hashes were emitted.
- Exactly 155,576 unique `(state hash, legal move)` pairs were emitted.
- Every emitted state and branch record has partition `development`.
- One-ply WDL recurrence passed for every state.
- DTZ recurrence mismatches: zero.
- Selection outcomes probed: zero.
- Confirmation outcomes probed: zero.
- Runtime: 170.07 seconds.
- Result Git revision: `771610b81dc2d213b72abf97f71b682bb47fbd6e`.
- State-record SHA-256: `3938a020ddb33c1e630e16b3f5f10af2b0d937f1bf35f1cc0a728006c8b64ca2`.
- Branch-record SHA-256: `1d84f7043dc92a7ef844470f0f6b76a830b8cd05e48a6aa468b57120006c20be`.

Generated records and plots remain ignored by Git in
`results/2026-08-21_branch_law_foundation_001/`.

## Decision and next experiment

The measurement foundation passes, but no branch selector advances. Experiment
016 should freeze and build the ordinary-position development dataset needed to
measure candidate viability and context-dependent opponent refutations. It must
compare pruned search with the same all-legal frozen reference so evaluation
and horizon error are not mislabeled as branch-removal error. Random, forcing,
all-capture, and Locked-3 orderings should establish the ordinary `rho_95`
curve before any compact learned selector is trained. Exact selection and
confirmation partitions remain sealed.
