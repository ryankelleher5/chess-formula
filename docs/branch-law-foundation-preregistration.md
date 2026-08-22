# Experiment 015 preregistration — Branch-Law measurement foundation

## Status and non-interference

This protocol is frozen before probing Syzygy outcomes or fitting any branch
selector. Experiments 001–014, all prior datasets and conclusions, the accepted
Locked-3 formula, and the accepted Forcing-3 policy remain unchanged.

Experiment 015 establishes measurement infrastructure and development baselines.
It cannot promote a learned selector and cannot produce a new playing-strength
claim. Selection and confirmation outcomes remain locked.

## Question

Can exact branch necessity and branch-retention curves be measured reproducibly
without conflating pruning loss with errors already made by a compact evaluator
or finite search horizon?

The first output is a measurement baseline, not a discovered law.

## Exact domains

Enumerate every legal fixed-material KQvK, KRvK, and KPvK state with the extra
piece normalized to White, both sides to move, no castling or en-passant rights,
and halfmove clock zero. Pawns occupy only ranks two through seven. Retain legal
terminal states in the census and exclude them from branch curves.

Canonicalize KQvK and KRvK over the eight dihedral board symmetries. Pawn
direction makes only identity and file reflection valid for normalized KPK.
Side to move is never removed by canonicalization. Assign complete canonical
classes by SHA-256 of seed and canonical key to 60% development, 20% selection,
and 20% confirmation.

The complete census is audited, but this experiment labels only a deterministic
5,000-position development sample per domain. Sample by SHA-256 rank after
canonicalization and terminal exclusion. Do not inspect selection or
confirmation WDL, DTZ, or branch outcomes.

The outcome-free implementation audit fixes the expected census before probing:

| Domain | Raw legal | Canonical | Canonical terminal | Development / selection / confirmation |
|---|---:|---:|---:|---:|
| KQvK | 368,452 | 46,137 | 155 | 27,473 / 9,264 / 9,400 |
| KRvK | 399,112 | 50,015 | 36 | 29,889 / 10,148 / 9,978 |
| KPvK | 331,352 | 165,676 | 11 | 99,589 / 33,093 / 32,994 |

The config freezes the SHA-256 digest of each 5,000-state development sample.
The audit reports `outcomes_probed: 0`.

## Exact truth and provenance

Use local Syzygy WDL50 and DTZ50 tables through `python-chess`. Required KQvK,
KRvK, and KPvK files plus KBvK/KNvK promotion subtables are downloaded from the
Lichess tablebase mirror and must
match the frozen byte counts and SHA-256 hashes in
[`configs/branch-law-foundation.json`](../configs/branch-law-foundation.json).
The [Syzygy generator](https://github.com/syzygy1/tb) documents the formats,
embedded checks, and redistribution status; the
[python-chess documentation](https://python-chess.readthedocs.io/en/stable/syzygy.html)
defines WDL/DTZ probing behavior and warns that files must match known hashes.

Fail closed for a missing file, unexpected byte count, checksum mismatch,
missing subtable, invalid position, or inconsistent one-ply recurrence.

## Exact labels

For every sampled nonterminal development state, store root WDL and DTZ. Probe
every legal successor and orient successor WDL to the root mover. Store the
WDL-optimal set and the DTZ-optimal subset using Syzygy's one-ply DTZ recurrence.
DTZ is a secondary progress label; WDL preservation is primary.

This exact root experiment measures whether a retained set contains at least one
WDL-perfect move. Context-aware ordinary records additionally reserve root
candidate, path, node role, remaining depth, and budget fields so later
refutation labels are not forced into a context-free `(position, move)` target.

## Baseline orderings and budgets

Every baseline returns a complete deterministic legal-move ordering. Compare
nested top 1, 2, 3, 4, 5, 8, 16, and all-legal retained sets:

1. random SHA-256 ordering over 20 deterministic repeat seeds;
2. current forcing-category priority, then lexical fill;
3. check, all-capture, promotion, and evasion priority, then lexical fill;
4. mover-oriented Locked-3 successor evaluation, then lexical ties;
5. oracle WDL then DTZ as a nondeployable upper reference; and
6. all legal moves as the endpoint.

Category baselines are filled lexically to the requested budget. This measures
the information in their priority ordering at equal branch counts; natural
variable-size category recall is reported separately.

## Measurements

For each domain, baseline, and budget report:

- mean legal and retained moves and retained fraction;
- WDL-perfect decision preservation;
- recall of all WDL-optimal moves and retention of at least one;
- DTZ-optimal retention within WDL-optimal moves;
- natural forcing/capture set size and exact recall;
- wall time and selector operations where defined.

Report `rho_95_wdl`, the smallest tested retained fraction with at least 95% WDL
preservation at that and every larger nested budget. Report `rho_perfect` only
when every sampled state is preserved; all-legal must equal 1.0. Neither exact
development number is a confirmation result.

The later ordinary-position north-star remains `rho_95` based on at most 25 cp
pruning-induced loss relative to the same all-legal frozen search. Absolute
oracle regret is reported separately.

## Integrity gates

- every emitted board is valid and has exactly the configured material;
- all symmetry-equivalent boards share canonical key and partition;
- no canonical key occurs in more than one partition;
- only development states appear in labeled records;
- all legal moves receive exactly one exact label;
- at least one WDL-optimal move exists for every nonterminal state;
- oracle ordering at budget one preserves WDL on every labeled state;
- all-legal preserves WDL on every labeled state for every baseline;
- cached tablebase files reproduce the same provenance on rerun; and
- generated JSON/NDJSON records conform to the versioned field contracts.

## What remains locked

Do not train logistic regression, trees, neural models, or symbolic selectors in
Experiment 015. Do not recursively apply a selector. Do not inspect selection or
confirmation exact outcomes. Do not use prior confirmation games as a new
ordinary confirmation set. A later protocol must freeze the ordinary development
source, counterfactual refutation procedure, candidate class, description cap,
and untouched confirmation domain before predictive comparison.
