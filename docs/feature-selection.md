# Nested feature selection

`nested-feature-selection-v1` searches for a minimum human-domain feature subset
without allowing a held-out game's positions to influence the subset evaluated on
that game.

## Selection rule

Each of 30 outer resamples holds out 25% of complete January games. Within the
remaining games, greedy forward selection begins with `material`. Eight inner
game-grouped resamples score each possible next feature by mean validation MAE.
Selection stops at the smallest path subset whose inner MAE retains 90% of the
full-16 model's gain over material-only.

The confirmation lock uses the upper-median selected feature count across outer
runs. Features fill that budget in descending selection frequency, breaking ties
by mean selection rank and then feature name. This rule was specified before the
February corpus was labeled or evaluated.

## January result and frozen lock

The nested procedure selected 2, 3, 4, or 6 features across outer folds, with an
upper median of 3. The locked feature set is:

```text
material + space + tempo
```

Including the intercept, this is a four-parameter linear evaluator. The selected
procedure achieved 150.76 cp outer-fold MAE, versus 154.00 for material-only and
141.25 for full-16. It recovered only 3.23 cp of the 12.75 cp full-model gain on
outer folds, despite the inner 90% stopping target. This is evidence that the
selection decision is unstable at the present sample size, not evidence that the
three-feature formula is sufficient.

The subset remained frozen for the independent February test. It subsequently
captured 85.2% of full-16's February MAE gain over material; the complete one-shot
result is in [transfer-confirmation.md](transfer-confirmation.md). February remains
confirmation data and is not used to repair the lock.

## Reproduction

```bash
chess-formula --config configs/feature-selection.json select-features
```

The complete paths, per-fold selections, metrics, and locked-subset manifest are
written beneath `results/YYYY-MM-DD_nested_feature_selection_NNN/`.
