# Forcing-3 UCI confirmation

Forcing-3 passes its untouched complete-game confirmation. The policy keeps the
accepted three-feature formula unchanged and adds one forcing ply plus a larger
per-root cap. The result confirms a strength gain over the accepted two-ply
policy while making the computational price explicit.

## Frozen boundary

Commit `df7c2da` fixed the UCI engine, 20-opening suite, opponents, resources,
fault handling, bootstrap, and decision rule before any scored game. The suite
contains 20 unique eight-ply rule states, SHA-256
`a4a8b749d8ad5fbbb8c21f2a297caab4576e2d4659e94b5d22c93f57b9324e85`,
with zero final-state or move-sequence overlap with the pilot. Each opening was
played twice per opponent with candidate colors reversed.

The protocol required zero candidate faults and opponent forfeits plus a 95%
opening-pair-bootstrap score lower bound above 50% against Searched-3.
Stockfish-100n was an external anchor without a threshold.

## Result

| Opponent | W-D-L | Score [95%] | Engine-pool Elo [95%] |
|---|---:|---:|---:|
| Searched-3 baseline | 14-24-2 | **65.0% [58.75%, 72.5%]** | **+108 [+61, +168]** |
| Stockfish-100n | 0-14-26 | 17.5% [10.0%, 25.0%] | −269 [−382, −191] |

The primary gate passes. Forcing-3 scores 62.5% as White and 67.5% as Black
against Searched-3. Against Stockfish it scores 10.0% as White and 25.0% as
Black. Color-specific values are descriptive; the paired aggregate is primary.

All 80 games finish with zero illegal moves, timeouts, crashes, null moves, or
opponent forfeits. All 80 generated PGNs parse without error and match the JSON
game records. The referee records the opponent as Stockfish 18, one thread, and
16 MB hash.

## Strength per computation

Against Searched-3, Forcing-3 reports 1,099.37 root-plus-internal states and
329.10 ms per move. The baseline reports 220.19 states and 68.24 ms. The
confirmed gain therefore costs 4.99 times the states and 4.82 times the latency
in the current Python implementation.

Against Stockfish, longer and different games raise the candidate averages to
1,418.62 states and 427.09 ms per move. Stockfish reports 108.33 nodes and 0.84
ms per move. Candidate states and Stockfish nodes are not equivalent operations.

## Interpretation

The improvement discovered in loss-game move regret generalizes to untouched
openings and complete adversarial games against the prior policy. Forcing-3 is
now the accepted compact-policy default. This supports the project's
"compact formula plus selective computation" direction more strongly than the
development frontier alone.

The computation increase is steep. The result does not show that an extra ply
is efficient in an absolute sense, nor does it close the gap to modern search.
The 17.5% Stockfish score exceeds the old pilot's 11.25%, but the opening suites
differ, so it is not a paired or direct improvement estimate. Engine-pool Elo is
conditional on this protocol and is not human FIDE Elo.

## Reproduction

```bash
chess-formula --config configs/forcing-3-confirmation.json \
  confirm-forcing-3 --stockfish /path/to/stockfish
```

The generated artifact contains the frozen config, environment, metrics, all
game records, PGNs, and a Markdown report.
