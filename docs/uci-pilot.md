# UCI playing-strength pilot

The frozen Searched Locked-3 policy now runs as a real UCI subprocess and
completed 120 color-balanced games without an illegal move, timeout, crash, or
null move. It decisively beats both static formula controls but loses decisively
to Stockfish 18 constrained to only 100 nodes per move.

## Frozen protocol

The complete UCI engine, referee, opening suite, opponent pool, resource limits,
adjudication, uncertainty method, and reporting rules were committed at
`badc98c` before any scored game. Before that commit, 50 tests passed with
Stockfish enabled, including an external UCI handshake and an explicitly
unscored 12-ply smoke game.

The candidate is the exact May Searched Locked-3 policy: four fitted parameters,
all-legal-root enumeration, ascending-UCI tie-breaking, and two forcing plies
with a 128-child budget per root candidate. It plays every one of 20 immutable
eight-ply openings twice against each opponent with colors reversed.

The opponents are frozen static Locked-3, frozen static Full-16, and Stockfish
18 with one thread, 16 MB hash, and 100 nodes per move. Games honor normal and
claimable chess draws and stop as draws at 160 total plies. No evaluation-based
adjudication or post-opening book moves are used. The accepted run took 355.94
seconds.

## Result

| Opponent | W-D-L | Score [95%] | Engine-pool Elo [95%] |
|---|---:|---:|---:|
| Static Locked-3 | 17-23-0 | 71.25% [63.75%, 78.75%] | +158 [+98, +228] |
| Static Full-16 | 17-23-0 | 71.25% [62.50%, 80.00%] | +158 [+89, +241] |
| Stockfish-100n | 0-9-31 | 11.25% [6.25%, 16.25%] | −359 [−470, −285] |

Uncertainty uses 10,000 bootstrap samples of complete reversed-color opening
pairs. All intervals against both static controls exclude a 50% score, as does
the negative result against Stockfish-100.

The candidate scored 72.5% as White and 70.0% as Black against each static
formula. Against Stockfish-100 it scored 7.5% as White and 15.0% as Black. It
never won a game against Stockfish: eleven opening pairs produced two losses and
nine produced one loss plus one draw.

Termination was rule-based. The static Locked-3 match ended in 17 checkmates and
23 threefold repetitions. Full-16 produced 17 checkmates, 22 threefold draws,
and one stalemate. The Stockfish match produced 31 checkmates, eight threefold
draws, and one 160-ply draw.

## Resources

Candidate resource use varies with the positions reached:

| Opponent | Candidate ms/move | Candidate states/move | Opponent ms/move | Opponent reported nodes/move |
|---|---:|---:|---:|---:|
| Static Locked-3 | 79.22 | 253.05 | 4.27 | 11.40 |
| Static Full-16 | 90.94 | 285.93 | 5.52 | 15.52 |
| Stockfish-100n | 79.71 | 255.51 | 0.78 | 107.62 |

Candidate “nodes” are legal root states plus selective forcing expansions;
Stockfish nodes are engine search nodes. They measure different operations and
must not be compared as equal-cost units. Wall time is also implementation-
specific: Python feature extraction is not optimized, while Stockfish is a
compiled engine.

## Interpretation

The playing result corroborates the May move-regret result in the direction that
matters: selective continuation search converts the same three-feature formula
into a materially stronger player than either static evaluator. The identical
17-23-0 aggregate scores against Locked-3 and Full-16 arise from different
opening-pair outcomes, so they are not duplicate games.

The Stockfish result is an equally important boundary. A 100-node modern
alpha-beta/NNUE engine wins 31 of 40 games despite reporting fewer nominal nodes
than the candidate's inspected states. The compact policy's search vocabulary,
depth, ordering, evaluator information, or all four remain substantial limiting
factors. The experiment does not identify which one.

Engine-pool Elo is conditional on this exact opening suite, resource control,
adjudication, and opponent pool. It is not human FIDE Elo, and 20 opening pairs
are a pilot rather than a broad strength calibration.

## Next experiment

Use the 31 Stockfish losses as development-only failure material. Record the
first large irreversible evaluation swing and classify missed quiet moves,
pawn captures, exchanges, king threats, and horizon failures. Then freeze a
small search-resource frontier—rather than immediately expanding the static
formula—and confirm it on a new opening suite with explicit state, wall-time,
and game-strength tradeoffs.

The accepted generated artifacts are
`results/2026-08-21_uci_playing_pilot_001/report.md` and
`results/2026-08-21_uci_playing_pilot_001/games.pgn`.
