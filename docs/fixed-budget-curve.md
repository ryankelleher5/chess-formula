# Fixed-budget search-efficiency curve

The completed development curve retains the confirmed Forcing-3 policy. No
cheaper policy passed every preregistered quality and game threshold, and the
more expensive four-ply point did not improve move quality.

## Scope

This experiment reuses the 80 completed Forcing-3 confirmation games. It is a
development comparison, not a new playing-strength claim. The formula remains

```text
6.709046 + 75.698112 material + 13.073405 space + 70.024384 tempo
```

Only forcing depth and the maximum expanded children per legal root vary.
Three deterministic candidate turns per completed game yielded 240 unique
positions. Stockfish 18 supplied depth-12 root and forced-move labels. Each
non-anchor policy also played 40 games against the confirmed Forcing-3 anchor
on the completed 20-opening, reversed-color suite.

## Position curve

| Policy | Mean states | Mean regret | Top-1 | >=300 cp mistakes | Time/position |
|---|---:|---:|---:|---:|---:|
| Forcing-1-64 | 106.5 | 166.18 cp | 27.08% | 15.00% | 35.53 ms |
| Searched-3 | 372.2 | 144.02 cp | 29.58% | 12.50% | 118.22 ms |
| Forcing-3-128 | 1,206.2 | 119.70 cp | 32.92% | 9.58% | 391.11 ms |
| **Forcing-3** | **1,360.9** | **105.05 cp** | **34.17%** | **8.33%** | **436.85 ms** |
| Forcing-4-256 | 3,353.7 | 123.09 cp | 30.83% | 12.08% | 1,057.13 ms |

Forcing-3-128 saves only 11.4% of the anchor's states and 10.5% of its measured
Python latency. Its mean regret is 14.66 cp higher, with a grouped-bootstrap
97.5th percentile of 31.56 cp. It retains 76.02% of the anchor's regret gain
over Forcing-1-64, below the frozen 80% requirement.

The four-ply saturation point uses 2.46 times the anchor's mean states and 2.42
times its latency, yet has 18.04 cp higher mean regret. More forcing-only depth
is therefore not monotonically beneficial under this evaluator, ordering, and
per-root budget.

The generated result directory is ignored by Git. A workspace containing the
completed artifact can inspect `budget_curve.png` alongside the machine-readable
metrics, choices, games, and PGNs.

## Game curve

| Candidate vs Forcing-3 | W-D-L | Score [95%] | Pool Elo [95%] | Candidate states/move |
|---|---:|---:|---:|---:|
| Forcing-1-64 | 0-28-12 | 35.00% [28.75%, 41.25%] | -108 [-158, -61] | 76.0 |
| Searched-3 | 2-24-14 | 35.00% [27.50%, 41.25%] | -108 [-168, -61] | 220.2 |
| Forcing-3-128 | 6-29-5 | 51.25% [47.50%, 56.25%] | +9 [-17, +44] | 928.8 |
| Forcing-4-256 | 2-33-5 | 46.25% [41.25%, 51.25%] | -26 [-61, +9] | 2,211.1 |

Forcing-3-128 passes both frozen game thresholds, but advancement required all
position and game conditions. It fails the regret-gain-retention, mean-regret,
and bootstrap-upper-regret gates, so it does not advance. All four matches are
protocol-clean.

## Integrity checks

- 160 of 160 PGNs parse without errors.
- Every policy has exactly 20 opening pairs and both candidate colors.
- PGN results and ply counts match `games.json` exactly.
- There are zero illegal moves, engine errors, timeouts, and opponent forfeits.
- The oracle produced 240 new root labels and 330 new forced-move labels using
  Stockfish 18 at the frozen settings.
- The complete run took 3,619.24 seconds.

## Decision

The preregistered selector found no eligible cheaper policy and retained
Forcing-3. This is useful negative evidence: the confirmed third-ply gain cannot
be recovered merely by halving the cap, and adding another forcing ply spends
substantially more computation without improving this curve.

The next milestone moves to exact three-piece endgames. Exact WDL and optimal
moves will separate compact-rule discovery from imitation of a finite-depth
Stockfish oracle and provide a domain where correctness, not average regret, is
measurable.
