# Experiment 017 preregistration — ordinary branch-oracle convergence

## Status and scope

Freeze this protocol, configuration, implementation, and tests in Git before
making any new Experiment 017 oracle query. Reuse only the 24 root and 134
opponent-parent development contexts selected by SHA-256 before Experiment 016.
Do not inspect a branch-law selection or confirmation partition, change the
accepted Locked-3 formula or Forcing-3 policy, add move categories, or train a
selector in this experiment.

## Question

Do move ranks, regret-threshold sets, and scores approach a reproducible plateau
as Stockfish computation increases? Does normalizing computation by the number
of legal moves stabilize all-legal MultiPV labels more efficiently than giving
every context the same total-node budget?

This is an empirical oracle calibration, not a claim that finite Stockfish
search defines chess truth. A passing result licenses a development training
target only under the tested domain and budget range.

## Frozen sample and reuse

Use exactly the Experiment 016 stability sample:

- 24 ordinary root contexts;
- 134 opponent-parent contexts;
- 158 total contexts; and
- no selection or confirmation contexts.

Fail closed on the source-protocol bytes and checksum, source audits, selected
context-key digest, prior cache bytes and checksum, prior metadata checksum,
and prior oracle identity. Reuse the frozen 20,000-node and 80,000-node records
without recomputation. New cache writes must be resumable and keyed by tier,
context, engine identity, and the complete protocol.

## Frozen oracle and compute curves

Use Stockfish 18, one thread, 16 MB hash, all-legal MultiPV, a new-game boundary
per context, and White-relative scores. Clip scores only when deriving the
reported comparison metrics, at ±2,000 cp.

Compare two independently frozen cost rules:

1. fixed total nodes per context: 20,000; 80,000; 320,000; 1,280,000;
2. nodes per legal reply: 625; 2,500; 10,000; 40,000, with the requested total
   equal to the rate times the legal-move count.

The geometric four-times spacing is fixed prospectively. The deepest endpoints
have similar mean cost on the frozen sample but distribute computation
differently. Report requested minimum, median, mean, maximum, and total nodes
for every tier. Do not substitute elapsed time for the selection cost.

## Stability measurements

For root and opponent-parent contexts separately, report between tiers:

- top-move agreement;
- mean top-3 and top-5 set Jaccard agreement;
- mean rank Spearman correlation using deterministic lexical tie-breaking;
- mean and median common-move score difference;
- mean and median mover-oriented regret difference;
- mean within-10/25/50/100-cp set Jaccard agreement; and
- per-move 10/25/50/100-cp threshold-label agreement.

Compare every tier with its next level and family maximum. Separately compare
the two deepest cost-rule endpoints.

## Prospective stability gate

A comparison passes only when **both** root and parent contexts satisfy every
condition:

- top-move agreement at least 85%;
- top-3 set Jaccard at least 80%;
- within-25-cp set Jaccard at least 75%;
- 25-, 50-, and 100-cp per-move label agreement at least 90%; and
- median mover-oriented regret difference at most 25 cp.

A tier is eligible only if it passes against both its next level and its family
maximum. A family maximum is compared with itself for within-family eligibility.
No tier is eligible unless the two deepest cost-rule endpoints pass the same
cross-rule gate. Select the eligible tier having the lowest mean requested
nodes, with lexical tie-breaking.

The 10-cp label remains reported but is excluded from the gate because its
boundary is narrower than the project's 25-cp decision-preservation tolerance.
The gate is deliberately multi-criterion: abundant unimportant moves could
make raw classification accuracy look stable while decisive top replies still
change.

## Decision

If a tier is selected, model training is unblocked only for a separately
preregistered compact-selector experiment using that reference. If no tier is
selected, do not train on the Experiment 016 labels. Record which criteria fail
and design the next calibration or alternative-oracle test without changing
this result retrospectively.

Regardless of outcome, do not describe the selected Stockfish budget as
perfect truth. Later validation must still use deeper Stockfish, exact
tablebases, alternative oracles where practical, self-play, and adversarial
counterexample search.
