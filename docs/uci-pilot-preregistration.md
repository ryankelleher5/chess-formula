# UCI playing-strength pilot preregistration

This protocol is frozen before any scored games are played. Protocol smoke tests
may use unscored positions and short games, but no opponent result may alter the
opening suite, resources, adjudication, game count, or reporting.

## Candidate

The candidate is the exact May Searched Locked-3 policy: intercept `6.709046`,
coefficients `75.698112 × material + 13.073405 × space + 70.024384 × tempo`,
all-legal-root-move enumeration, ascending-UCI tie-breaking, and the unchanged
two-ply forcing search with a 128-child budget separately for every root move.
The UCI `go` arguments do not alter this fixed computation.

Before scored play, an external `python-chess` client must complete `uci`,
`isready`, `ucinewgame`, `position`, `go`, and `quit` interactions and verify a
legal `bestmove`. Any later candidate null or illegal move, process exception, or
timeout is a loss and a protocol failure.

## Opponents and resources

Run three separate matches:

- frozen static Locked-3 through the same UCI wrapper;
- frozen static Full-16 through the same UCI wrapper;
- Stockfish 18 with one thread, 16 MB hash, and exactly 100 nodes per move.

Policy engines receive `go nodes 1`, but intentionally ignore that request and
execute their frozen computation. Each UCI operation has a five-second wall
timeout. No pondering or opening-book moves occur after the supplied opening.

## Openings and colors

Use the 20 immutable eight-ply positions in
`configs/uci-pilot-openings.json`. Each candidate/opponent pairing plays every
opening twice, reversing candidate colors. This yields 40 games per opponent and
120 games total. Opening-pair identity, rather than individual game, is the
uncertainty-resampling unit.

## Termination and adjudication

Honor checkmate, stalemate, insufficient material, automatic draws, and
claimable threefold-repetition or fifty-move draws. Declare a draw when the
complete game reaches 160 plies. Use no evaluation-based or tablebase
adjudication. An engine exception, timeout, null move in a live position, or
illegal move forfeits the game immediately.

## Metrics and interpretation

For each opponent report wins/draws/losses, score rate, a 10,000-repeat paired
opening bootstrap 95% score interval, and the score's logistic engine-pool Elo
difference with interval. Also report move times, reported nodes, termination
reasons, illegal moves, crashes, and timeouts.

The protocol gate passes only if the candidate has zero illegal moves, crashes,
and timeouts. Playing strength has no pass threshold in this pilot: report the
result whether positive or negative. Engine-pool Elo is conditional on this
opening/resource/opponent pool and must never be called human FIDE Elo.

## Outcome

The protocol gate passed across all 120 games with zero candidate illegal moves,
timeouts, crashes, or null moves. Searched Locked-3 scored 71.25% against each
static control and 11.25% against Stockfish at 100 nodes/move. See
[UCI playing-strength pilot](uci-pilot.md) for paired intervals, engine-pool Elo,
resources, interpretation, and limitations.
