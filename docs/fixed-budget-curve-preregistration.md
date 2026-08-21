# Fixed-budget search-efficiency curve preregistration

This is a development experiment around the confirmed Forcing-3 policy. It
reuses completed confirmation games and cannot create a new strength claim.

## Fixed formula and policies

Every point uses the unchanged `material + space + tempo` formula, exhaustive
legal-root enumeration, forcing vocabulary, tactical ordering, stand-pat rule,
and lexical root ties. Only forcing depth and the per-root child cap vary:

| Policy | Forcing plies | Per-root cap | Calibration mean states |
|---|---:|---:|---:|
| Forcing-1-64 | 1 | 64 | 94 |
| Searched-3 | 2 | 128 | 323 |
| Forcing-3-128 | 3 | 128 | 1,028 |
| Forcing-3 anchor | 3 | 256 | 1,183 |
| Forcing-4-256 | 4 | 256 | 2,845 |

Calibration used a seed-stable 80-position slice only to set resource points;
it exposed no move-quality or game outcome.

## Development positions and oracle

From each of the 80 completed confirmation games, rank candidate turns after
the supplied opening by SHA-256 of seed, game identity, and rule-state hash.
Select three per game, then deduplicate rule states. Require at least 230 unique
positions. Label root-best and every distinct policy-selected move with
Stockfish 18 at depth 12, one thread, and 16 MB hash. Cache labels resumably.

Report regret, exact best-move agreement, thresholded mistakes, states, cap
binding, and Python wall time. Bootstrap regret differences by complete
opponent/opening color pair 5,000 times.

## Development game curve

Each non-anchor policy plays the confirmed Forcing-3 anchor on all 20 completed
confirmation openings with colors reversed: 40 games per policy. Preserve the
five-second timeout, 160-ply cap, claimable draws, fault forfeits, no evaluation
adjudication, and 10,000 opening-pair bootstrap samples.

## Frozen advancement rule

A policy cheaper than the anchor is eligible only if all conditions hold:

1. at least 80% of the anchor's mean-regret gain over Forcing-1-64 is retained;
2. mean regret is no more than 10 cp above the anchor;
3. the grouped-bootstrap 97.5th percentile regret increase is at most 15 cp;
4. head-to-head score against the anchor is at least 47.5%; and
5. its paired score lower bound is at least 40%.

Select at most one eligible policy by lowest mean states, then lower regret,
then lexical label. Forcing-4 is a saturation probe and cannot advance because
it is more expensive. If nothing qualifies, keep Forcing-3. Any selected policy
must be frozen before a completely new opening-suite confirmation.
