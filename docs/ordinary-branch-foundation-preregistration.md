# Experiment 016 preregistration — ordinary context-aware branch foundation

## Status and scope

Freeze this protocol and its implementation before making any new Stockfish
query for ordinary branch labels. Experiment 016 is development-only. It trains
no selector, cannot advance a branch law, and cannot alter the accepted
Locked-3 formula or Forcing-3 policy. Exact selection/confirmation partitions
and every future ordinary confirmation set remain untouched.

The 80 games used as sources were confirmation games for an earlier, already
completed question. Experiment 014 prospectively converted three deterministic
positions per game into a development-only search curve. Experiment 016 reuses
those same 240 frozen positions only as development. They are permanently
ineligible for a future Branch-Law confirmation claim.

## Question

When every legal root candidate remains available, how much opponent-reply
breadth is required to preserve the root decision? Do compact, outcome-blind
orderings preserve refutations better than the current forcing rule at equal
reply budgets?

This isolates the failure class most strongly motivated by the loss audit:
quiet or pawn-capture opponent replies that make a root candidate worse than a
selective search believes.

## Frozen source audit

Verify the source file byte-for-byte and reproduce these outcome-free counts
before oracle labeling:

- 240 valid, unique, nonterminal source positions;
- 80 complete source-game keys and 40 opening/opponent pair groups;
- 6,689 legal root-candidate contexts;
- six root candidates that terminate immediately;
- 6,683 nonterminal opponent-parent contexts; and
- 217,973 legal opponent-reply records.

The config freezes source, position-key, source-game-key, parent-key, and
stability-sample SHA-256 digests. Fail closed on any mismatch.

## Counterfactual design

Retain all legal root candidates. For each candidate move, analyze the resulting
opponent-to-move position with all legal replies under one frozen oracle call.
The all-reply candidate value is the opponent-optimal reply score. The root's
all-reply reference choice maximizes or minimizes those candidate values for
the original mover.

For a retained reply set, recompute each candidate value using only the replies
in that set, then choose among all root candidates. This changes only opponent-
reply information; legal root breadth is never pruned.

Independently analyze each source root with all-legal MultiPV. These direct root
scores define candidate rank, 10/25/50/100-cp viability, and the absolute regret
of both the all-reply and pruned choices. Define pruning-induced loss as

```text
L_branch = max(0, direct_oracle_regret(pruned choice)
                  - direct_oracle_regret(all-reply choice))
```

The independent root oracle prevents the child-context minimax score from
grading its own changed decision. Record negative raw differences as oracle
inversions before clipping them to zero.

## Reply importance labels

For every opponent reply, store opponent-oriented rank and regret. Separately
remove that reply while retaining every other reply in the same candidate
context.

- Candidate-refutation importance measures how much better the candidate looks
  to the root mover when the reply is omitted.
- Root-decision consequence recomputes the root choice after the single-reply
  omission and measures pruning-induced root loss with the independent oracle.
- A sole legal reply is structurally necessary and cannot be omitted.

Keep 10, 25, 50, and 100 cp thresholds distinct. Do not collapse candidate
viability, opponent refutation, and root consequence into one target.

## Oracle and stability audit

Use Stockfish 18 with one thread, 16 MB hash, a 20,000-node limit, all-legal
MultiPV, and a new-game boundary for every context. Store White-relative raw
scores and mate distances; clip only derived regret metrics to ±2,000 cp.

Repeat the outcome-free SHA-selected 24 root contexts and 134 opponent-parent
contexts at 80,000 nodes. Report top-reply agreement and common-move score MAE
separately for root and parent contexts. The stability audit measures label
sensitivity; it does not replace or tune the frozen base oracle.

## Baselines and budgets

At every opponent-parent context, produce a complete deterministic reply
ordering:

1. 20 seeded random orderings;
2. current forcing replies, then lexical fill;
3. checks, all captures, promotions, and evasions, then lexical fill;
4. opponent-oriented Locked-3 successor evaluation, then lexical ties; and
5. oracle reply ordering as a nondeployable upper reference.

Retain the top 1, 2, 3, 4, 5, 8, 16, and all legal replies independently in
every candidate context. Category baselines also report their natural unfilled
branch fraction and refutation recall. Do not add handcrafted move categories
in response to the result.

## Measurements

For every baseline and budget report retained reply fraction, `DPR_25`, exact
root-choice agreement with the all-reply reference, pruning-induced loss,
absolute direct-oracle regret for full and pruned choices, 100/300-cp
catastrophic omissions, candidate-refutation recall, root-critical reply recall,
positions retaining every critical reply, selector operations, and latency.

The north-star is `rho_95`, the smallest tested retained fraction with
`DPR_25 >= 95%` at that and every larger nested budget. The all-legal endpoint
must reproduce the all-reply decision and zero pruning loss for every baseline.
The oracle ordering must reproduce the all-reply candidate values at budget
one.

## Decision

Experiment 016 succeeds if it produces a complete, reproducible development
dataset and valid ordinary branch-budget curves. It does not select a winner.
Only after this result is recorded may a later preregistration define primitive
representations and compact model classes. No selection or confirmation outcome
may be inspected in this experiment.
