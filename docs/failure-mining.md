# February failure mining

`failure-mining-v1` uses the frozen February confirmation predictions to generate
new hypotheses without changing the accepted confirmation result.

## Candidate definition

A position enters the exploratory set if either:

- Locked-3 absolute error is at least 300 cp; or
- absolute disagreement between Locked-3 and Full-16 is at least 150 cp.

The union contains 157 positions from 55 games: 101 high-error positions, 74
high-disagreement positions, and 18 satisfying both criteria. Four deterministic
farthest-first k-means clusters use the 13 features omitted by Locked-3,
standardized with January training means and scales.

## Main finding: forcing positions dominate large errors

Ninety-one of 101 high-error positions (90.1%) satisfy the forcing proxy, compared
with 730 of 1,079 positions (67.7%) in the full confirmation set. Full-16 improves
70.3% of these high-error cases, but its mean error remains 537.3 cp versus 572.3
cp for Locked-3. The remaining error is much larger than Full-16's ordinary
February MAE of 141.8 cp. This points toward a small, bounded forcing search rather
than simply restoring every static term.

## Secondary finding: passed-pawn imbalance

Cluster 3 contains 33 positions from 12 games. Its passed-pawn difference is
−3.62 January-standardized units at the centroid, with connected pawns (−1.28z)
and king safety (−1.02z) as smaller associations. It is 84.8% forcing; Full-16 is
better on 63.6% of its positions and reduces mean error from 410.2 to 376.5 cp.
This motivates testing exactly one additional static feature, `passed_pawns`, but
does not validate that feature.

Cluster 2 is larger (74 positions/29 games) and emphasizes isolated and doubled
pawn imbalance. Cluster 4 (49 positions/28 games) is mostly openings and has only
weak centroid deviations led by mobility and bishop pair. Cluster 1 is a singleton
outlier and is explicitly excluded as a basis for a rule.

## Research UI

The experiment emits `failure_explorer.html`, a self-contained local explorer with:

- board diagrams and FENs;
- Stockfish, Locked-3, and Full-16 evaluations;
- error and disagreement flags;
- cluster, phase, and criterion filters; and
- error/disagreement sorting.

It is generated under `results/YYYY-MM-DD_failure_mining_NNN/` and intentionally
ignored by Git because it embeds the derived candidate data. The generator is
versioned and deterministic.

## Reproduction

```bash
chess-formula --config configs/failure-mining.json mine-failures
```

February is now development data for hypothesis generation. Neither the cluster
labels nor post-hoc subgroup measurements count as confirmation. The frozen March
protocol is documented in [march-preregistration.md](march-preregistration.md).
