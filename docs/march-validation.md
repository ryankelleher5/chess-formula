# March compact-rule validation

`march-compact-rules-v1` is the untouched test of the two hypotheses generated
from February failure mining.

## Corpus and provenance

The verified source is the official CC0 Lichess March 2013 standard-rated archive:

- URL: `https://database.lichess.org/standard/lichess_db_standard_rated_2013-03.pgn.zst`
- advertised size: 23,590,691 bytes
- official SHA-256: `89da64fc3c1fe3bfd571d7f626232189f3259aa728b46ea81e5cb8f3fdb34b9e`
- advertised games: 158,635

The complete archive was streamed. Of 158,635 scanned games, 11,349 met the
frozen eligibility rules. The seed-20260825 reservoir sample contains 120 games,
ratings 1800–2313 (mean 1974.32), and lengths of 41–150 plies. Its PGN SHA-256 is
`3cfc9f5b36343da68d4cce67bad364528faa3294bb972d634f7a26a6e98ae7c4`.

Sampling and Stockfish depth-8 labeling yielded 2,229 unique positions with
1,108 White-to-move and 1,121 Black-to-move. Forty-five hashes present in the
January/February development union were excluded, leaving 2,184 positions from
all 120 games. The development union contains 2,170 unique positions.

## Frozen result

| Candidate | Params | Overall MAE | Forcing MAE | Correlation | Sign | ≥500 cp |
|---|---:|---:|---:|---:|---:|---:|
| Material-only | 2 | 134.98 | 162.27 | 0.5291 | **72.12%** | 2.66% |
| Locked-3 | 4 | 132.45 | 154.93 | 0.5933 | 69.32% | 2.20% |
| Locked-4-passed | 5 | 132.64 | 155.05 | 0.5973 | 69.41% | 2.06% |
| Full-16 | 17 | 125.77 | 147.72 | 0.6400 | 71.84% | 2.15% |
| Searched Locked-3 | 4 + search | **115.91** | **128.18** | **0.7465** | 70.47% | 1.01% |
| Searched Locked-4-passed | 5 + search | 116.60 | 129.12 | 0.7446 | 70.60% | **0.87%** |

Candidate A fails its preregistered rule. Adding `passed_pawns` changes paired
overall MAE by +0.21 cp with a 95% game-bootstrap interval of [−1.20, +1.68]. It
slightly improves RMSE and catastrophic-error rate, but does not establish an MAE
gain and will not advance.

Candidate B passes. Bounded search changes paired forcing-stratum MAE by −26.65
cp [−33.45, −20.11]. It improves overall MAE by 16.55 cp, correlation by 0.1532,
and catastrophic-error frequency from 2.20% to 1.01% relative to static Locked-3.
It also improves overall MAE by 9.86 cp over static Full-16.

## Computation cost

Searched Locked-3 expands a mean of 5.04 child positions per root, with p95 18
and maximum 60. No position reaches the frozen 128-child cap. The unoptimized
Python implementation takes 2.18 ms per position, including repeated feature
extraction. The algorithm therefore remains bounded, but it is not accurate to
describe it as “only four parameters”: the search rules and expanded positions
are part of its description and computational complexity.

## Interpretation

The February failure pattern transfers: a tiny amount of targeted computation
buys more evaluation fidelity than thirteen extra static coefficients. This
supports a “compact principles plus selective search” account more strongly than
either a purely static four-term law or unrestricted feature restoration.

The claim remains limited to predicting Stockfish depth-8 evaluations on sampled
human positions. It does not yet show that the method chooses strong moves or
plays strong chess. Material-only still has the best sign accuracy, illustrating
that metric tradeoffs remain.

## Reproduction

```bash
chess-formula --config configs/march-validation.json prepare-human-corpus
chess-formula --config configs/march-validation.json \
  ingest data/raw/lichess_march_validation_120.pgn
chess-formula --config configs/march-validation.json \
  label --stockfish "$(command -v stockfish)"
chess-formula --config configs/march-validation.json validate-march
```
