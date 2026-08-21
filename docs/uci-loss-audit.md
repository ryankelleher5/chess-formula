# UCI loss audit

The 31 losses to Stockfish-100n in the frozen UCI pilot are development data,
not a new confirmation set. This audit asks where the first persistent large
move error occurs and whether the existing forcing-only, two-ply search could
represent Stockfish's refutation.

## Frozen method

Commit `6f0a83e` fixed the method before the losses were analyzed. Stockfish 18
at depth 12, one thread, and 16 MB hash evaluated every candidate turn after
the eight-ply opening. Regret is the mover-oriented difference between the
unrestricted root value and a search constrained to the played move, clipped
to ±2,000 cp. The preferred first error is the earliest move with at least 150
cp regret that leaves the candidate at least 300 cp worse and remains at least
300 cp worse at its next turn. The fallback is the first 150 cp error, then the
maximum-regret move.

The reply taxonomy is operational rather than subjective. It tests whether the
first two moves of Stockfish's played-move principal variation are in the
current search vocabulary: checks, promotions, captures of non-pawns, and all
legal check evasions.

## Result

All 957 candidate turns were labeled, and all 31 games had a persistent major
error under the frozen rule. The selected error had 318.10 cp mean regret, 270
cp median regret, and occurred at median ply 16. The selected games were
balanced across 17 White and 14 Black candidate losses.

| Stockfish continuation class | Games |
|---|---:|
| Excluded quiet opponent reply | 9 |
| Excluded pawn-capture opponent reply | 5 |
| Visible reply, quiet candidate continuation | 9 |
| Visible forcing line beyond two plies | 8 |

Stockfish's best replacement root move was quiet in 29 of 31 games; the other
two were one pawn capture and one non-pawn capture. This does not mean quiet
root moves are omitted—the policy already evaluates every legal root. It means
that the compact search often cannot distinguish the strategically necessary
quiet choice from the move it plays.

Independent root and constrained depth-12 searches produced 102 negative raw
regrets before the preregistered zero clamp. These were small relative to the
150 cp gate: median magnitude 14 cp, 94 at most 50 cp, and maximum 74 cp. Cache
replay recovered all 957 records with zero new engine analyses.

## Interpretation and next gate

No single omitted move class dominates. The failures divide across opponent
reply breadth, quiet second-ply continuations, and forcing horizon. The frozen
three-feature formula therefore remains unchanged while a development-only
frontier compares four targeted search extensions: include pawn captures,
include every opponent reply, include every candidate continuation after a
forcing reply, and add one forcing ply. Each candidate must report selected-move
regret, expanded states, and wall time. Any candidate chosen from these losses
must be locked before a new opening-suite confirmation.

Reproduce the audit with:

```bash
chess-formula --config configs/uci-loss-audit.json audit-uci-losses \
  --stockfish /path/to/stockfish
open results/YYYY-MM-DD_uci_loss_audit_NNN/loss_explorer.html
```

The generated `loss_explorer.html` is self-contained and provides boards,
played and best moves, principal variations, reply-class filters, color filters,
and regret sorting for all 31 selected errors.
