# April deeper-oracle preregistration

This protocol is frozen before downloading, selecting, labeling, or evaluating
the April 2013 corpus.

## Question

Does the March-confirmed Searched Locked-3 advantage survive an untouched human
domain when Stockfish depth increases from 8 to 12?

## Frozen model and search

Fit Material-only, Locked-3, and Full-16 coefficients on the deduplicated
January/February depth-8 development union under the unchanged ridge alpha and
target clip. Do not use March or April labels for fitting. Searched Locked-3 uses
the exact March search implementation:

- checks, promotions, and non-pawn captures outside check;
- every legal evasion in check;
- two plies and at most 128 expanded child positions;
- deterministic ordering and stand-pat outside check;
- ±2,000 cp terminal wins/losses and compact-formula leaf evaluation.

## April domain

Verify and stream the official CC0 April 2013 Lichess archive. Select 120 eligible
games by seed-20260826 reservoir sampling with the unchanged filters and position
sampler. Label only with Stockfish 18 depth 12, MultiPV 1, one thread, and 16 MB
hash. Exclude every April position hash observed in January, February, or March;
March influenced candidate promotion even though it did not fit coefficients.

## Decision

The primary contrast is Searched Locked-3 minus static Locked-3 MAE in the frozen
forcing proxy. The search gain survives only if the paired source-game-bootstrap
mean is negative and its 95% interval excludes zero. Report overall MAE,
correlation, sign accuracy, ≥500 cp errors, phase/forcing strata, expanded
positions, and latency for every candidate regardless of the primary result.

This gate validates position-value prediction only. Move-selection work remains
separate because stand-pat does not always return a legal root move.
