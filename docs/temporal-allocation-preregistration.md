# Experiment 020 preregistration — temporal computation allocation

## Status and scope

Freeze this protocol, implementation, configuration, source/cache identities,
temporal-union digests, tests, metrics, and roadmap entry in Git before making
any new Experiment 020 oracle query. Use all 158 frozen development contexts
and all 5,259 legal branches. Do not train a model or inspect any selection or
confirmation outcome.

Experiment 019 remains failed under its original literal complete-recall gate.
Experiment 020 does not reinterpret or replace that result. It prospectively
tests a different target motivated by the distinction between retaining every
near-equivalent move and retaining enough information for a safe decision.

## Question

Does a branch's value trajectory across independent computation budgets
identify branches that must receive further computation?

The generic signal is early or intermittent promise, not the chess identity of
an observed failure. A branch receives further computation when it was within
25 cp of the best branch at **any** 10,000-, 40,000-, or 160,000-node
independent checkpoint.

## Post-hoc origin and prospective status

After Experiment 019, a diagnostic calculation found that adding the 10k
checkpoint to the prior 40k/160k union would recover a sufficiently good 640k
reply in all 134 opponent contexts, with maximum loss 14 cp. That calculation
uses already observed Experiment 019 outcomes and is not confirmation.

The candidate is now frozen independently of the new 2.56M outcomes. No
special case, move identity, piece category, position identity, or handcrafted
chess feature is permitted.

## Frozen temporal union

For every context, retain a legal move if its mover-oriented regret is at most
25 cp at any of Experiment 018's independent 10,000-, 40,000-, or
160,000-node tiers. Preserve the ±2,000 cp score clip and lexical tie-breaking.
Do not add or remove a move after observing 2.56M-node outcomes.

The union contains 594 branches: 60 across 24 root contexts and 534 across 134
opponent-parent contexts. At parents, pooled retention is
`534 / 4,580 = 11.6594%`; the equally weighted mean of the 134 context-level
fractions is 14.3865%. These are distinct estimands and must always be labeled.

The complete branch-key SHA-256 is
`d57751d6646c8f4bb797fc7e4d6c512222f35546ad1aeb743f5fac241f04c728`.
Fail closed on that digest, the separate root/parent digests, Experiment 018's
protocol/cache/metadata bytes and checksums, its oracle identity, and every
source identity.

## New independent audit

Analyze every one of the 5,259 legal moves at exactly 2,560,000 nodes in its
own Stockfish 18 constrained-root call, using one thread, 16 MB hash, and a
new-game boundary per branch. Use independently resumable caching for every
`(tier, context, move)`. Store the same raw score, mate, depth, selective depth,
nodes, latency, context, move, and oracle identity as Experiments 018–019.

All 158 contexts are included. A counterexample-only sample could test
persistence but could not support a population-level training license.

## Measurements

Evaluate 10k-only, 40k-only, 160k-only, the prior 40k/160k late union, and the
10k/40k/160k temporal union. Report separately for roots and opponent parents:

- fraction of contexts retaining at least one audit move within 25 cp;
- mean, median, and maximum pruning loss from the best retained move;
- counts of pruning losses over 25, 100, and 300 cp;
- pooled retained fraction (`total retained / total legal`);
- equally weighted mean context-level retained fraction;
- exact audit top-reply recall;
- micro recall of all audit moves within 25 cp; and
- complete within-25-cp-set recall.

Exact top-reply and complete near-best-set recall remain scientifically useful
diagnostics, but they are not advancement vetoes. The primary target is a
decision-sufficient set, not every interchangeable continuation.

## Firm advancement gate

The temporal union passes only if **both** root and opponent-parent contexts
satisfy all of the following:

- 100% of contexts retain at least one move within 25 cp;
- maximum pruning loss is no greater than 25 cp;
- zero pruning losses over 100 cp;
- zero pruning losses over 300 cp;
- both pooled and mean-context retained fractions are below 35% at roots; and
- both pooled and mean-context retained fractions are below 20% at parents.

The repeated loss thresholds are intentional: they make the catastrophic
omission contract explicit even though the 25-cp maximum implies them.

Only the temporal union is eligible. A pass licenses a separately
preregistered compact selector-discovery experiment. It does not make this
expensive oracle-derived set deployable, does not establish recursive tree
reduction, and does not establish final root-decision preservation.

This is the final deeper calibration on the current Stockfish-only path. If a
material late-emerging miss causes failure, stop escalating node budgets and
pivot toward exact-domain or alternative-oracle ground truth.
