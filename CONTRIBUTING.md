# Contributing

Every change should serve a stated research question. Before adding machinery, write down the hypothesis, intervention, frozen measurement, and decision the result will inform.

1. Create a focused branch and keep generated data, binaries, checkpoints, caches, databases, and reports out of Git.
2. Add or update a versioned configuration and record the random seed, dataset/benchmark version, engine/model version, engine limits, runtime, and environment.
3. Preserve positive-as-White score orientation end to end.
4. Split positions by source game and audit duplicate positions before training.
5. Run `pytest` and the smallest relevant end-to-end experiment.
6. Append evidence to `RESEARCH.md`; never rewrite an unfavorable historical result.

Do not change a frozen benchmark in place. Create a new named version and explain why comparability was intentionally broken.

Branch-law experiments must additionally freeze the branch-importance
definition, node/path context, retained-branch budget, oracle limits, and
counterfactual procedure before comparing selectors. Report the complete
retained-branch fraction versus decision-quality curve, `rho_95`, catastrophic
omissions, refutation recall, and selector-plus-search complexity. Keep ordinary
confirmation games and exact confirmation components untouched until the
candidate and advancement rule are committed.

Do not add conventional engine machinery solely for Elo. Every search mechanism
must isolate a stated question about evaluation, branch necessity, exact play,
or description complexity.
