# Experiment 019 preregistration — uncertainty-aware branch adjudication

## Status and scope

Freeze this protocol, implementation, configuration, source/cache identities,
conservative-union digests, tests, and roadmap entry in Git before making any
new Experiment 019 oracle query. Use all 158 frozen development contexts and
all 5,259 legal branches. Do not train a model or inspect any selection or
confirmation outcome.

## Question

Does the unchanged conservative union of independent 40,000- and 160,000-node
branch labels contain every important reply when judged by a new, substantially
deeper 640,000-node-per-move independent audit?

This remains finite Stockfish adjudication, not proof of chess truth. A pass
licenses only a separately preregistered development training experiment.

## Frozen conservative union

For every context, retain a legal move if its mover-oriented regret is at most
25 cp under either Experiment 018's independent 40,000-node tier or independent
160,000-node tier. Preserve the ±2,000 cp score clip and lexical tie-breaking.
Do not add or remove a move after observing 640,000-node outcomes.

The frozen union contains 555 branches: 57 across 24 root contexts and 498
across 134 opponent-parent contexts. Its complete branch-key SHA-256 is
`c52930deb1feec0a2825b488449482d2ca89d681bb452e518415fc2d29caff22`.
Fail closed on that digest, the separate root/parent digests, Experiment 018's
protocol/cache/metadata bytes and checksums, its oracle identity, and every
source identity.

## New audit

Analyze every one of the 5,259 legal moves at exactly 640,000 nodes in its own
Stockfish 18 constrained-root call, using one thread, 16 MB hash, and a new-game
boundary per branch. Use independently resumable caching for every
`(tier, context, move)`. Store the same raw score, mate, depth, selective depth,
nodes,
latency, context, move, and oracle identity as Experiment 018.

No difficult-context targeting is used: all 158 development contexts are
included, avoiding post-result sampling and providing stable controls
automatically.

## Measurements

Evaluate the frozen union against the 640,000-node audit, separately for roots
and opponent parents:

- exact audit top-reply recall;
- micro recall of every audit move within 25 cp of the audit best;
- fraction of contexts whose complete within-25-cp set is retained;
- fraction of contexts with at least one retained move within 25 cp;
- mean, median, and maximum pruning loss from the best retained move;
- counts of pruning losses over 25, 100, and 300 cp;
- micro and mean-context retained branch fraction; and
- structured identities for every false negative.

Report the unchanged 40k-only, 160k-only, intersection, and union selectors as
controls. The frozen intersection retains no move in four contexts; score those
control cases as zero-branch failures with a 4,000-cp capped loss. Do not fill
them with another move. Only the union is eligible to pass.

## Firm advancement gate

The union passes only if **both** root and opponent-parent contexts satisfy all
of the following:

- 100% 640k top-reply recall;
- 100% recall of all 640k within-25-cp moves;
- 100% of contexts retain at least one move within 25 cp;
- zero pruning losses over 100 cp;
- zero pruning losses over 300 cp;
- mean retained fraction at most 35% for roots and 20% for parents.

The first two conditions answer the literal “every important reply” question.
The 100/300-cp conditions remain explicit even though perfect top recall would
normally imply zero pruning loss. The branch-fraction limits prevent an
all-legal selector from passing trivially.

If any condition fails, do not license labels or train a selector. Preserve the
counterexamples for the next law-discovery iteration. If all pass, record that
the finite development gate passed; do not call the union perfect chess truth.
