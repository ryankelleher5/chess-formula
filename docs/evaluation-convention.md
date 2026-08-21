# Evaluation convention

Every stored target and prediction is from White's point of view:

- positive: White is better;
- negative: Black is better;
- zero: balanced according to the oracle/model.

The UCI score returned by `python-chess` is explicitly converted with `score.pov(chess.WHITE)`, independent of whose turn it is. A mate for White is positive and a mate for Black is negative. Mate scores retain their signed mate distance and also receive a configurable finite centipawn sentinel (100,000 cp by default) for storage.

The initial ridge model trains on labels clipped to ±2,000 cp. Its benchmark uses the same clip so one forced mate does not dominate aggregate error. Raw oracle values remain unchanged in `engine_analysis`; reports state both the raw distribution and the benchmark clip.

## Move regret and branch loss

Stored position evaluations remain White-relative. Move regret is instead
oriented to the mover so that a larger nonnegative value is always worse for the
side choosing the move. Reports must state clipping and count apparent negative
regret as oracle instability before clamping it to zero for aggregate metrics.

Branch-Law Discovery additionally measures pruning-induced loss. The same frozen
search is run with all legal branches and with a retained subset; an external
frozen oracle scores both root choices. Pruning-induced loss is the nonnegative
increase in oracle regret caused by the retained subset. This separates branch
omission from errors already present in the evaluator or finite search horizon.
See [`branch-law-discovery.md`](branch-law-discovery.md) for `DPR_25`, `rho_95`,
catastrophic omission thresholds, and the exact-domain convention.
