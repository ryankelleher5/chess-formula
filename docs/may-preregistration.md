# May legal move-policy preregistration

This protocol is frozen before downloading, selecting, labeling, or evaluating
the May 2013 corpus. April may inform implementation and tests but cannot support
the confirmation claim.

## Question

Does wrapping the frozen compact evaluator in deterministic legal root-move
enumeration produce lower Stockfish centipawn regret than choosing moves with
the static compact formula?

## Frozen policies

Fit static coefficients only on the deduplicated January/February depth-8
development union, using the unchanged ridge alpha and ±2,000 cp target clip.
The three policies are:

- **Locked-3:** enumerate every legal root move, evaluate its resulting position
  with `material + space + tempo`, and select the maximum for White or minimum
  for Black;
- **Full-16:** use the identical root wrapper with the static 16-feature formula;
- **Searched Locked-3:** enumerate every legal root move, then evaluate its
  resulting position with the exact March/April selective search.

Legal moves are visited in ascending UCI order, which also breaks exact score
ties. Checkmate, loss, and draw after the root move score +2,000, −2,000, and 0
cp. Searched Locked-3 retains checks, promotions, and non-pawn captures outside
check; all evasions while in check; deterministic ordering; stand-pat outside
check; two plies; and a 128-expanded-child cap **for each legal root candidate**.
It uses the compact formula, never Stockfish, at leaves.

## Untouched May domain

Verify and stream the official CC0 Lichess May 2013 archive. Select 120 eligible
games by seed-20260827 reservoir sampling under the unchanged rating, length, and
position-sampling rules. Exclude every rule-state position hash observed in
January through April.

Label May roots with Stockfish 18 at depth 12, MultiPV 3, one thread, and 16 MB
hash. Measure each distinct policy-selected move not equal to Stockfish's root
best move using a cached root-move-constrained analysis at the same depth and
engine options. Convert all scores to White's perspective, clip both best and
chosen-move scores to ±2,000 cp, orient regret to the side to move, and clamp
negative differences caused by independent-search noise to zero. Report the
frequency of those inversions.

## Metrics and decision

For every policy report 100% legal coverage; top-1 and top-3 Stockfish agreement;
mean, median, p95, and maximum regret; within-10 cp rate; 50, 100, and 300 cp
mistake rates; phase and forcing-proxy strata; legal root moves evaluated;
forcing children expanded; and descriptive Python latency.

The primary paired contrast is Searched Locked-3 minus static Locked-3 mean
regret over 1,000 source-game bootstrap samples. The searched policy advances
only if legal coverage is exactly 100%, the paired mean is negative, and its 95%
interval excludes zero. Searched Locked-3 versus Full-16 is secondary and does
not control the primary decision.

## Guardrail

Low regret can establish useful legal move selection, but not game strength.
Root enumeration and every forcing expansion count toward computation. UCI play
testing begins only after this prospective gate.

## Outcome

The gate passed on 2,131 non-overlapping May positions with 100% legal coverage.
Searched Locked-3 reduced mean clipped regret by 188.08 cp relative to static
Locked-3, with a 95% paired game-bootstrap interval of [176.33, 199.93] cp. See
[May legal move-policy validation](may-move-policy.md) for provenance, complete
metrics, computation, the execution-only repair, and limitations.
