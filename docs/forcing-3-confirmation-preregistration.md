# Forcing-3 UCI confirmation preregistration

This protocol is frozen before scored games. The 31 Stockfish losses selected
Forcing-3, so neither those games nor the frontier metrics count as confirmation.

## Candidate

The candidate retains the exact Locked-3 formula:

```text
6.709046 + 75.698112 material + 13.073405 space + 70.024384 tempo
```

It enumerates every legal root in UCI lexical order. After each root, it uses
the accepted forcing vocabulary and ordering for exactly three internal plies,
allows stand-pat outside check, and caps expansion at 256 children per legal
root. UCI `go` arguments do not change this computation.

## Untouched openings

Use the 20 immutable eight-ply positions in
`configs/forcing-3-confirmation-openings.json`. The executable gate verifies 20
unique final rule states, no final-state overlap with the pilot, and no identical
eight-ply move sequence. Every opponent pairing reverses candidate colors,
making the complete opening pair the bootstrap unit.

## Opponents and games

Run two 40-game matches, 80 games total:

- the accepted Searched-3 two-ply/128-child policy through UCI;
- Stockfish 18 at 100 nodes per move, one thread, and 16 MB hash.

Both policy engines receive `go nodes 1` but execute their frozen computation.
Every UCI operation has a five-second timeout. Record the probed Stockfish name,
author, path, and configured resources.

## Termination and faults

Honor checkmate, stalemate, insufficient material, automatic draws, and
claimable threefold or fifty-move draws. Draw at 160 total plies. Do not use
evaluation or tablebase adjudication. An exception, timeout, null move in a live
position, or illegal move forfeits immediately.

## Metrics and decision

Report W-D-L, paired score and logistic engine-pool Elo intervals, termination
reasons, faults, mean move time, reported states/nodes, and candidate-to-baseline
state and latency ratios. Use 10,000 opening-pair bootstrap samples.

Forcing-3 confirms only if both conditions hold:

1. candidate faults and opponent forfeits are zero; and
2. the 95% paired-bootstrap score lower bound against Searched-3 is above 50%.

Stockfish-100n is an external anchor with no pass threshold. If the primary gate
fails, Searched-3 remains the accepted policy. Report the result without tuning
the candidate, openings, resources, or rule. Pool Elo is not human FIDE Elo.
