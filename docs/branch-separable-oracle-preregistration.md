# Experiment 018 preregistration — branch-separable oracle calibration

## Status and scope

Freeze this protocol, implementation, configuration, schema, tests, and roadmap
entry in Git before making any new Experiment 018 oracle query. Use only the 24
root and 134 opponent-parent development contexts frozen before Experiment 016.
Do not inspect selection or confirmation outcomes, train a selector, change the
Locked-3 formula or Forcing-3 policy, or add a handcrafted move category.

## Question

Do ordinary branch values stabilize when every legal move receives an
independent constrained-root compute budget? How much of Experiment 017's
instability came from Stockfish dividing one shared all-legal MultiPV budget,
rather than from finite search horizon itself?

This experiment calibrates a measurement instrument. It does not assume that
the deepest Stockfish result is perfect chess truth.

## Frozen source and oracle

Fail closed on the Experiment 017 protocol, cache, and metadata bytes and
SHA-256 checksums; its oracle identities; the 158 context identities; all 5,259
`(context, legal move)` identities; and the expected record counts.

Use Stockfish 18 with one thread and 16 MB hash. Analyze exactly one legal root
move in each call using the UCI constrained-root mechanism. Give every branch a
new-game boundary so hash state and search history cannot leak between moves.
Store White-relative raw score, mate, depth, selective depth, reported nodes,
requested nodes, latency, context, move, and oracle identity. Cache each
`(tier, context, move)` independently and resumably.

## Compute curve

Allocate exactly the following nodes independently to every legal move:

- 2,500;
- 10,000;
- 40,000; and
- 160,000.

The four-times geometric spacing is frozen prospectively. Report both
nodes-per-move and implied total nodes per context. The 160,000-node tier is
audit-only and cannot validate or select itself.

## Measurements and ambiguity

For root and opponent-parent contexts separately, report every Experiment 017
stability measurement: top-move agreement, top-3/top-5 Jaccard, rank Spearman,
score and mover-regret differences, within-10/25/50/100-cp set Jaccard, and
10/25/50/100-cp label agreement.

For each lower tier, compare with both its next tier and the audit maximum.
Prospectively classify every threshold label comparison as:

- stable-important: positive at both tiers;
- stable-unimportant: negative at both tiers; or
- ambiguous: the tiers disagree.

Report the ambiguous rate and the mean fraction retained by the conservative
union. Do not silently relabel ambiguity as either truth or error. Also report
the count and reciprocal regret severity of changed top replies.

As allocation diagnostics only, compare independent 40,000-node-per-move
search with Experiment 017's shared 40,000-node-per-reply MultiPV tier, and the
160,000 independent audit with Experiment 017's deepest fixed-total tier. These
comparisons cannot waive the selection gate.

## Prospective gate and selection

A comparison passes only when both root and parent contexts satisfy all of:

- top-move agreement at least 85%;
- top-3 set Jaccard at least 80%;
- within-25-cp set Jaccard at least 75%;
- 25-, 50-, and 100-cp label agreement at least 90%; and
- median mover-oriented regret difference at most 25 cp.

A lower tier is eligible only if it passes against both its next tier and the
160,000-node audit endpoint. Select the eligible tier with the fewest nodes per
move, with lexical tie-breaking. The audit endpoint is never eligible.

If no lower tier passes, select no reference and keep model training blocked.
If one passes, it licenses only a separately preregistered development training
experiment. It remains subject to deeper, cross-oracle, exact-domain, self-play,
and adversarial validation.
