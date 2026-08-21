# May legal move-policy validation

The deterministic legal wrapper around Searched Locked-3 passes its prospective
May gate. It chooses a legal move on every tested position and substantially
reduces Stockfish centipawn regret relative to both static Locked-3 and static
Full-16. This is move-quality evidence, not yet playing-strength evidence.

## Provenance and integrity

The source is the official CC0 Lichess standard-rated May 2013 archive:

- archive: `lichess_db_standard_rated_2013-05.pgn.zst`;
- reported games: 179,550;
- exact size: 26,545,457 bytes;
- SHA-256: `f044607c9f565831524dbedfd474100c8604dba008600bfaf1b7a48ced74c17b`;
- official index: <https://database.lichess.org/standard/>;
- official game counts: <https://database.lichess.org/standard/counts.txt>;
- official checksums: <https://database.lichess.org/standard/sha256sums.txt>.

The verified full stream contained all 179,550 games. The unchanged filters
admitted 11,013 games. Seed-20260827 reservoir sampling selected 120 games with
ratings from 1800 to 2301 (mean 1947.28) and lengths from 40 to 152 plies. The
selected PGN SHA-256 is
`4d9f5f27bda163bde7f977868c3a6ac45cfa319af7c2faea49f93dcb85e2d9b1`.

Ingestion had zero parse errors and produced 2,199 unique positions, balanced
1,093 White to move and 1,106 Black to move. Sixty-eight hashes observed in
January through April were excluded, leaving 2,131 positions across all 120
games: 1,327 forcing-proxy and 804 quiet-proxy positions.

## Frozen protocol

The complete protocol was committed at `0fd3c9b` before downloading the May
archive. Coefficients are fit only on the 2,170-position deduplicated
January/February depth-8 development union. The unchanged Locked-3 equation is:

```text
Evaluation_cp = 6.709046
              + 75.698112 × material
              + 13.073405 × space
              + 70.024384 × tempo
```

Every policy enumerates all legal root moves in UCI lexical order and maximizes
for White or minimizes for Black. Static Locked-3 and Full-16 score each child
directly. Searched Locked-3 applies the frozen two-ply forcing search after each
root move, with a separate 128-expanded-child allowance per root candidate.

Stockfish 18 labels each root at depth 12, MultiPV 3, one thread, and 16 MB hash.
Each distinct policy move outside Stockfish's root best receives a cached
root-move-constrained depth-12 analysis. Best and chosen scores are clipped to
±2,000 cp before side-to-move regret is computed. Negative regret caused by
independent-search noise is clamped to zero and counted; it occurs on 1.69% of
Searched Locked-3 positions.

## Result

| Policy | Mean regret | Median | p95 | Top-1 | Top-3 | ≥100 cp | ≥300 cp |
|---|---:|---:|---:|---:|---:|---:|---:|
| Locked-3 | 312.96 | 282 | 784 | 15.81% | 24.92% | 66.87% | 48.33% |
| Full-16 | 274.46 | 206 | 742.5 | 17.03% | 27.73% | 61.38% | 41.53% |
| Searched Locked-3 | **125.02** | **61** | **456** | **24.12%** | **38.95%** | **38.06%** | **13.80%** |

All three policies have 100% legal coverage. Across 1,000 paired source-game
bootstrap samples, Searched Locked-3 minus static Locked-3 mean regret is
−188.08 cp with a 95% interval of [−199.93, −176.33]. The primary gate passes.
The secondary contrast against Full-16 is −149.55 cp
[−162.72, −136.38].

The improvement appears in every reported domain stratum. Searched Locked-3
mean regret is 129.62 cp in openings, 118.17 in middlegames, 94.75 in endgames,
124.93 on forcing-proxy positions, and 125.19 on quiet-proxy positions. The
quiet-position result is notable: root enumeration still considers every legal
move even when the selective continuation later uses stand-pat.

## Computation

All policies evaluate 34.34 legal root moves per position on average. Searched
Locked-3 additionally expands a mean 215.11 forcing children (p95 629.5,
maximum 3,612 aggregated across root candidates). Its current Python policy
latency is 90.00 ms/position, compared with 10.26 ms for Locked-3 and 10.33 ms
for Full-16. Thus the accepted object is four fitted parameters plus root
enumeration and selective search—not a four-parameter-only move formula.

The May root oracle required 2,199 MultiPV analyses. The three policies requested
4,000 unique position/move pairs: 592 reused Stockfish's root-best value and
3,408 required constrained analyses. The accepted rerun reused all 3,408 cached
constrained scores and generated none anew.

## Execution failure and repair

The first post-cache command stopped before computing or displaying metrics
because the scoring call omitted its already-loaded root-score map. Commit
`0560b14` supplied that argument and added a regression test covering root-best
reuse and alternative-move cache retrieval. The failure changed no policy,
oracle score, metric, threshold, or analysis choice. The complete protocol then
ran successfully from the unchanged caches.

## Interpretation and limits

The compact searched system has crossed an important boundary: it can now choose
legal moves, and those moves are markedly closer to a depth-12 Stockfish policy
than either static evaluator's choices. Exact agreement remains modest because
chess frequently offers several reasonable moves, making regret more informative
than top-1 agreement alone.

The result does not establish Elo, win rate, time-management behavior, or
resilience across complete games. The next experiment should expose the frozen
policy through UCI and preregister a color-balanced, opening-paired playing test
with fixed computation and explicit illegal-move, timeout, adjudication, and Elo
uncertainty reporting.

## Reproduction

After preparing, ingesting, and root-labeling every configured database:

```bash
chess-formula --config configs/may-move-policy.json validate-moves \
  --stockfish "$(command -v stockfish)"
```

The accepted local report is
`results/2026-08-21_may_move_policy_001/report.md`.
