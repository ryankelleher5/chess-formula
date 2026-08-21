# Contributing

Every change should serve a stated research question. Before adding machinery, write down the hypothesis, intervention, frozen measurement, and decision the result will inform.

1. Create a focused branch and keep generated data, binaries, checkpoints, caches, databases, and reports out of Git.
2. Add or update a versioned configuration and record the random seed, dataset/benchmark version, engine/model version, engine limits, runtime, and environment.
3. Preserve positive-as-White score orientation end to end.
4. Split positions by source game and audit duplicate positions before training.
5. Run `pytest` and the smallest relevant end-to-end experiment.
6. Append evidence to `RESEARCH.md`; never rewrite an unfavorable historical result.

Do not change a frozen benchmark in place. Create a new named version and explain why comparability was intentionally broken.

