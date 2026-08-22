# April deeper-oracle robustness

The frozen Searched Locked-3 result survives an untouched April human-game
domain labeled by Stockfish at depth 12. This is a position-value result, not a
move-selection or playing-strength result.

## Provenance and integrity

The source is the official CC0 Lichess standard-rated April 2013 archive:

- archive: `lichess_db_standard_rated_2013-04.pgn.zst`;
- reported games: 157,871;
- exact size: 23,299,559 bytes;
- SHA-256: `11c795d3c81c49fa97cd958b0984c044410c78ad90f454ed08abb57ab7d00d52`;
- official index: <https://database.lichess.org/standard/>;
- official checksum list: <https://database.lichess.org/standard/sha256sums.txt>.

The complete verified stream contained all 157,871 games. The unchanged
eligibility filters admitted 10,174 games. Seed-20260826 reservoir sampling
selected 120 games with ratings from 1800 to 2388 (mean 1959.18) and game
lengths from 41 to 154 plies. The selected PGN SHA-256 is
`280c81787826e2827f84b444ef180d7528ec762f0eafacdada2d1426e34ca133`.

Ingestion produced 2,228 unique sampled positions, balanced 1,102 White to move
and 1,126 Black to move. Fifty-one rule-state hashes previously observed in
January, February, or March were excluded, leaving 2,177 positions across all
120 games. This includes 1,377 forcing-proxy and 800 quiet positions.

## Frozen protocol

The executable protocol was committed before April data access at `13ae92e`.
Material-only, Locked-3, and Full-16 coefficients were fit only on the 2,170
deduplicated January/February positions labeled at depth 8. March influenced
candidate promotion but supplied no coefficient-fitting data. April labels use
Stockfish 18 at depth 12, MultiPV 1, one thread, and 16 MB hash; their engine
cache key is `563559fd75a1850633ba`.

Searched Locked-3 is unchanged from March: deterministic selective minimax over
checks, promotions, and non-pawn captures; all evasions while in check; at most
two plies and 128 expanded children; stand-pat outside check; ±2,000 cp terminal
values; and the compact formula, never Stockfish, at leaves.

## Result

| Candidate | Params | Overall MAE | Forcing MAE | Correlation | Sign | ≥500 cp | Mean expanded |
|---|---:|---:|---:|---:|---:|---:|---:|
| Material-only | 2 | 154.66 | 185.79 | 0.4392 | 69.55% | 4.27% | 0.00 |
| Locked-3 | 4 | 150.52 | 177.04 | 0.5128 | 69.50% | 3.40% | 0.00 |
| Full-16 | 17 | 145.74 | 173.67 | 0.5299 | 70.46% | 3.35% | 0.00 |
| Searched Locked-3 | 4 + search | **134.89** | **152.34** | **0.6364** | **71.15%** | **2.02%** | 5.30 |

Across 1,000 paired source-game bootstrap samples, Searched Locked-3 minus
static Locked-3 forcing MAE is −24.53 cp with a 95% interval of
[−30.26, −18.60]. The preregistered deeper-oracle gate therefore passes.
Searched Locked-3 also improves overall MAE over static Locked-3 by 15.50 cp
[11.72, 19.09] and over Full-16 by 10.77 cp [4.49, 16.33].

Search expands 5.30 child positions per root on average (p95 19, maximum 46),
never reaches the 128-child cap, and takes 2.19 ms per evaluated position in the
current Python implementation. These timings describe this implementation; they
are not an optimized engine comparison.

## Interpretation and limits

All formulas have higher absolute error against the deeper April target than
against the shallower March target, but the searched formula's advantage remains
large and statistically resolved. The March gain is therefore not explained by
using the same shallow oracle depth for development and confirmation, within the
tested domains and depth change. A few deterministic forcing continuations add
more predictive value here than thirteen additional static features.

The evaluator still does not always emit a legal root move because stand-pat can
be its preferred action. The next experiment must wrap the frozen evaluator in a
deterministic legal-move policy and test move agreement and centipawn regret on a
new untouched corpus. It must not reinterpret this evaluation result as move
prediction.

## Reproduction

After preparing and labeling all configured databases:

```bash
chess-formula --config configs/april-depth-robustness.json validate-depth \
  --stockfish "$(command -v stockfish)"
```

The accepted generated report is
`results/2026-08-21_april_depth_robustness_001/report.md`.
