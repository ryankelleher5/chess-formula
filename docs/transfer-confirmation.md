# February transfer confirmation

`transfer-confirmation-v1` is the untouched test of the feature subset locked by
January's nested selection experiment.

## Source and provenance

The source is the official Lichess standard-rated February 2013 archive:

- URL: `https://database.lichess.org/standard/lichess_db_standard_rated_2013-02.pgn.zst`
- advertised size: 18,151,480 bytes
- official SHA-256: `c136acdf343293c45252906fee91e3b561fb26a936979f52dbe04bb649a2fd86`
- advertised games: 123,961
- license: Creative Commons CC0, as stated by the [Lichess open database](https://database.lichess.org/)

The complete archive was verified and streamed. Of 123,961 scanned games, 8,966
met the frozen rating, result, variant, title, and length requirements. A
seed-20260823 reservoir sample selected 60 games with ratings 1802–2208 (mean
1920.53) and lengths of 41–141 plies. The selected PGN SHA-256 is
`08f4a02582b9d5c131b1475dbea1b06647f8136981d456985967c2fd8724cd5b`.

Sampling produced 1,106 unique labeled positions with 551 White-to-move and 555
Black-to-move. Twenty-seven exact rule-state hashes also occurred in January and
were excluded before evaluation, leaving 1,079 confirmation positions.

## Frozen comparison

All coefficients were fit once on the complete January corpus. February affected
neither the features nor the coefficients.

| Formula | Parameters | February MAE | Correlation | Sign accuracy | ≥500 cp error |
|---|---:|---:|---:|---:|---:|
| Material-only | 2 | 149.09 cp | 0.5637 | **73.68%** | 3.80% |
| Locked-3 | 4 | 142.85 cp | 0.6330 | 70.71% | 3.43% |
| Full-16 | 17 | **141.76 cp** | **0.6473** | 72.01% | **3.15%** |

The locked evaluator captures 6.24 cp, or 85.2%, of full-16's 7.32 cp MAE gain
over material. Across 1,000 source-game bootstrap samples, locked minus material
has mean MAE difference −6.31 cp with a 95% interval of [−12.33, −1.08]. Full
minus locked is −1.10 cp [−8.41, +6.08], so this sample does not resolve whether
the extra 13 parameters improve MAE.

The four-parameter fitted formula is:

```text
Evaluation_cp = +13.184331
  +78.222382 * material
  +11.712326 * space
  +68.803559 * tempo
```

The compression tradeoff is not uniform. Locked-3 improves MAE in forcing,
middlegame, and endgame strata relative to material, but is 3.64 cp worse in the
quiet proxy and loses 2.97 percentage points of overall sign accuracy.

## Reproduction

```bash
chess-formula --config configs/transfer-confirmation.json prepare-human-corpus
chess-formula --config configs/transfer-confirmation.json \
  ingest data/raw/lichess_transfer_confirmation_60.pgn
chess-formula --config configs/transfer-confirmation.json \
  label --stockfish "$(command -v stockfish)"
chess-formula --config configs/transfer-confirmation.json confirm-subset
```

The generated archive, selected PGN, provenance, database, labels, and result
artifacts are ignored by Git. Configuration, source checksum, lock, and benchmark
protocol are versioned.
