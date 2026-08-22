# Search-resource frontier

The development frontier compares four search extensions derived from the 31
Stockfish-100n losses while holding the accepted Locked-3 formula exactly fixed.
It selects at most one candidate for a future confirmation; it does not make a
new playing-strength claim.

## Frozen protocol

Commit `a739e62` fixed the implementation, five policies, budgets, oracle, and
decision rule before the comparison ran. Every policy enumerates all legal root
moves. Added non-forcing moves follow the accepted tactical ordering and then
UCI lexical order.

| Policy | Internal schedule | Per-root cap |
|---|---|---:|
| Searched-3 baseline | forcing, forcing | 128 |
| All-captures-2 | all captures, all captures | 128 |
| All-opponent-replies-2 | all legal, forcing | 256 |
| All-candidate-continuations-2 | forcing, all legal | 256 |
| Forcing-3 | forcing, forcing, forcing | 256 |

The domain is all 957 candidate turns in the 31 lost games. Stockfish 18 at
depth 12 scores each distinct selected move with a root-move constraint. An
extension is eligible only when its mean regret improves by at least 10% and
its 31-game grouped-bootstrap 95% delta interval is below zero. Among eligible
extensions, the policy with the lowest mean root-plus-internal state count wins;
remaining ties use lower mean regret and then lexical label.

## Result

| Policy | Mean regret | Delta [95%] | Top-1 | ≥300 cp | Mean states | ms/position |
|---|---:|---:|---:|---:|---:|---:|
| Searched-3 baseline | 130.45 | — | 28.63% | 8.88% | 279.7 | 86.3 |
| All-captures-2 | 127.07 | −3.38 [−7.34, −0.61] | 28.53% | 8.67% | 434.4 | 140.0 |
| All-opponent-replies-2 | 106.48 | −23.97 [−33.38, −15.76] | **31.35%** | 7.31% | 2,303.7 | 794.4 |
| All-candidate-continuations-2 | 128.42 | −2.03 [−6.76, +2.61] | 28.84% | 8.67% | 865.7 | 259.8 |
| **Forcing-3** | **102.61** | **−27.84 [−39.59, −17.81]** | 30.93% | **6.17%** | **1,074.8** | **332.5** |

All-opponent-replies-2 and Forcing-3 clear both eligibility conditions.
Forcing-3 advances because it uses less than half the mean states of the other
eligible policy while also achieving the lower mean regret. Pawn-capture
breadth has a resolved but only 2.6% mean improvement, below the frozen 10%
minimum. All-candidate-continuations-2 clears neither condition.

The baseline reproduces all 957 recorded game moves exactly. The oracle request
set contains 1,525 distinct position/move pairs: 388 root-best and 683 actually
played values are reused, and 454 alternatives require new constrained calls.
A cache-only rerun recovers all 454 alternatives with zero new Stockfish calls.

## First-error diagnostic

On the 31 previously selected error boards, Forcing-3 changes 14 moves, matches
Stockfish's exact best move four times, and reduces mean regret from 318.10 to
195.45 cp. Its mean regret by original reply class is 203.2 cp for beyond-two-ply,
220.8 for excluded pawn captures, 255.4 for excluded quiet replies, and 114.4
for quiet second plies. These class summaries are descriptive because the same
games selected the candidate.

## Cost and guardrails

Forcing-3 examines 3.84 times as many mean states as baseline and takes 3.85
times as long in the current Python implementation. Its 256-state per-root cap
is reached somewhere in 146 of 957 positions (490 legal roots), so the exact cap
and ordering are part of the selected algorithm. All-opponent-replies-2 reaches
its cap in 140 positions and is roughly 9.2 times slower than baseline. The
complete sequential run takes 1,549.93 seconds.

Forcing-3 is now a locked development candidate. It must be exposed through UCI
without changing its formula, move vocabulary, depth, ordering, stand-pat rule,
or cap, and tested on a new opening suite before any strength claim advances.

Reproduce the frontier with:

```bash
chess-formula --config configs/search-frontier.json run-search-frontier \
  --stockfish /path/to/stockfish
```
