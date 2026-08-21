# March compact-rule preregistration

This protocol is frozen before downloading, selecting, labeling, or evaluating
the March 2013 Lichess corpus.

## Development and confirmation domains

January and February become development data. Deduplicate their union by the
rule-state position hash and fit all static coefficients with ridge alpha 10 and
the existing ±2,000 cp target clip. March is an untouched confirmation domain.
Exclude any March position hash found in the development union before evaluation.

The March corpus will be a seed-20260825 reservoir sample of 120 eligible games
from the verified CC0 Lichess March 2013 standard-rated archive. Eligibility,
position sampling, and Stockfish depth-8 labeling remain unchanged.

## Candidate A — one-term pawn extension

Add only `passed_pawns` to the locked vocabulary:

```text
material + space + tempo + passed_pawns
```

Fit its four coefficients and intercept on pooled January/February development
positions. The primary comparison is paired March game-bootstrap MAE versus the
pooled-data refit of Locked-3. Secondary metrics are correlation, sign accuracy,
≥500 cp error, and the preregistered endgame and forcing strata.

## Candidate B — bounded forcing search

Wrap each static candidate in the same deterministic selective minimax:

- maximum depth: two plies;
- maximum expanded child positions: 128 per root;
- if in check, search every legal evasion;
- otherwise search legal checks, promotions, and non-pawn captures;
- deterministic order: checks, promotions, captures by captured piece value,
  then UCI text;
- at non-check nodes, include the static evaluation as a stand-pat option;
- White maximizes and Black minimizes the White-relative evaluation;
- checkmate returns ±2,000 cp and other terminal positions return 0;
- use the static evaluator at the depth or node boundary.

The primary comparison is forcing-stratum MAE for searched Locked-3 versus static
Locked-3. Secondary outcomes are overall MAE, ≥500 cp error, evaluation latency,
expanded positions, and the same comparison for the passed-pawn candidate.

## Frozen comparison set

The March report will include:

1. material-only;
2. static Locked-3;
3. static Locked-4-passed;
4. searched Locked-3;
5. searched Locked-4-passed; and
6. static Full-16.

All static models use pooled January/February training and identical ridge/clip
settings. Search does not call Stockfish; it uses the compact formula at leaves.

## Decision rules

- Candidate A advances only if its paired mean March MAE is lower than Locked-3
  and its 95% game-bootstrap interval does not cross zero.
- Candidate B advances only if its paired forcing-stratum mean MAE is lower than
  static Locked-3 and its 95% game-bootstrap interval does not cross zero.
- Report every metric and complexity cost even if a primary rule fails.
- Do not alter features, search rules, thresholds, or coefficients after viewing
  March results. Failed candidates remain recorded as failures.
