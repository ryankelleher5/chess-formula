# Evaluation convention

Every stored target and prediction is from White's point of view:

- positive: White is better;
- negative: Black is better;
- zero: balanced according to the oracle/model.

The UCI score returned by `python-chess` is explicitly converted with `score.pov(chess.WHITE)`, independent of whose turn it is. A mate for White is positive and a mate for Black is negative. Mate scores retain their signed mate distance and also receive a configurable finite centipawn sentinel (100,000 cp by default) for storage.

The initial ridge model trains on labels clipped to ±2,000 cp. Its benchmark uses the same clip so one forced mate does not dominate aggregate error. Raw oracle values remain unchanged in `engine_analysis`; reports state both the raw distribution and the benchmark clip.

