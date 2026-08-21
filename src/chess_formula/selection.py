from __future__ import annotations

import json
import platform
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np

from .benchmark import calculate_metrics
from .config import set_deterministic_seed, write_json
from .database import connect_database
from .features import feature_matrix
from .model import _git_commit, _next_experiment_id, fit_ridge, resolve_engine_key
from .stability import _interval, grouped_resamples


def _mean_grouped_mae(
    matrix: np.ndarray,
    target: np.ndarray,
    game_ids: np.ndarray,
    indexes: list[int],
    splits: list[tuple[set[str], set[str]]],
    alpha: float,
) -> float:
    values = []
    selected = matrix[:, indexes]
    for train_games, validation_games in splits:
        train_mask = np.isin(game_ids, list(train_games))
        validation_mask = np.isin(game_ids, list(validation_games))
        coefficients, intercept = fit_ridge(selected[train_mask], target[train_mask], alpha)
        predicted = selected[validation_mask] @ coefficients + intercept
        values.append(float(np.mean(np.abs(target[validation_mask] - predicted))))
    return float(np.mean(values))


def forward_select_features(
    matrix: np.ndarray,
    target: np.ndarray,
    game_ids: list[str] | np.ndarray,
    feature_names: list[str],
    *,
    alpha: float,
    repeats: int,
    validation_fraction: float,
    retention_fraction: float,
    seed: int,
) -> dict:
    """Select the smallest greedy subset retaining a fraction of the full-model gain."""
    if "material" not in feature_names:
        raise ValueError("Feature selection requires the material feature")
    if not 0.0 <= retention_fraction <= 1.0:
        raise ValueError("retention_fraction must be between 0 and 1")
    game_array = np.asarray(game_ids)
    splits = grouped_resamples(
        game_array.tolist(),
        repeats=repeats,
        test_fraction=validation_fraction,
        seed=seed,
    )
    index_by_name = {name: index for index, name in enumerate(feature_names)}
    cache: dict[tuple[str, ...], float] = {}

    def score(names: list[str]) -> float:
        key = tuple(names)
        if key not in cache:
            cache[key] = _mean_grouped_mae(
                matrix,
                target,
                game_array,
                [index_by_name[name] for name in names],
                splits,
                alpha,
            )
        return cache[key]

    full_mae = score(feature_names)
    material_mae = score(["material"])
    gain = max(0.0, material_mae - full_mae)
    threshold = full_mae + (1.0 - retention_fraction) * gain
    selected = ["material"]
    path = [{"features": selected.copy(), "mean_validation_mae_cp": material_mae}]
    while len(selected) < len(feature_names) and score(selected) > threshold:
        candidates = []
        for name in feature_names:
            if name in selected:
                continue
            candidate = selected + [name]
            candidates.append((score(candidate), name))
        candidate_mae, candidate_name = min(candidates, key=lambda item: (item[0], item[1]))
        selected.append(candidate_name)
        path.append(
            {"features": selected.copy(), "mean_validation_mae_cp": candidate_mae}
        )
    return {
        "selected_features": selected,
        "selected_size": len(selected),
        "material_validation_mae_cp": material_mae,
        "full_validation_mae_cp": full_mae,
        "retained_gain_threshold_mae_cp": threshold,
        "path": path,
    }


def lock_consensus_subset(selections: list[list[str]], feature_names: list[str]) -> dict:
    if not selections:
        raise ValueError("At least one selection is required")
    sizes = np.asarray([len(selection) for selection in selections])
    locked_size = int(np.quantile(sizes, 0.5, method="higher"))
    counts = Counter(name for selection in selections for name in selection)
    ranks: dict[str, list[int]] = {name: [] for name in feature_names}
    for selection in selections:
        for rank, name in enumerate(selection):
            ranks[name].append(rank)

    def ordering(name: str) -> tuple[float, float, str]:
        mean_rank = float(np.mean(ranks[name])) if ranks[name] else float("inf")
        return (-counts[name], mean_rank, name)

    ordered = sorted(feature_names, key=ordering)
    if "material" in ordered:
        ordered.remove("material")
    locked = ["material", *ordered[: max(0, locked_size - 1)]]
    return {
        "locked_features": locked,
        "locked_size": locked_size,
        "size_distribution": dict(sorted(Counter(sizes.tolist()).items())),
        "selection_frequency": {
            name: counts[name] / len(selections) for name in feature_names
        },
        "mean_selected_rank": {
            name: (float(np.mean(ranks[name])) + 1.0 if ranks[name] else None)
            for name in feature_names
        },
    }


def _metric_summary(runs: list[dict]) -> dict:
    names = (
        "evaluation_mae_cp",
        "evaluation_correlation",
        "sign_accuracy",
        "catastrophic_error_rate_500cp",
    )
    return {name: _interval([float(run[name]) for run in runs]) for name in names}


def _selection_report(result: dict) -> str:
    performance_rows = []
    for label, summary in result["nested_performance"].items():
        metrics = summary["metrics"]
        performance_rows.append(
            f"| {label} | {summary['parameter_count']['median']:.0f} | "
            f"{metrics['evaluation_mae_cp']['mean']:.2f} ± "
            f"{metrics['evaluation_mae_cp']['standard_deviation']:.2f} | "
            f"{metrics['evaluation_correlation']['mean']:.4f} | "
            f"{metrics['sign_accuracy']['mean']:.2%} | "
            f"{metrics['catastrophic_error_rate_500cp']['mean']:.2%} |"
        )
    frequency_rows = []
    consensus = result["consensus_lock"]
    for name, frequency in sorted(
        consensus["selection_frequency"].items(), key=lambda item: (-item[1], item[0])
    ):
        rank = consensus["mean_selected_rank"][name]
        frequency_rows.append(
            f"| `{name}` | {frequency:.1%} | {rank:.2f} | "
            f"{'yes' if name in consensus['locked_features'] else 'no'} |"
            if rank is not None
            else f"| `{name}` | {frequency:.1%} | — | no |"
        )
    locked = ", ".join(f"`{name}`" for name in consensus["locked_features"])
    inner_summary = (
        f"{result['inner_repeats']} / {result['inner_validation_fraction']:.0%}"
    )
    return f"""# Nested Feature Selection: {result['experiment_id']}

## Question

What is the smallest handcrafted feature subset that retains 90% of the full
model's MAE gain over material on January human games?

## Leakage controls

- Outer test games never participate in their fold's feature selection.
- Greedy selection and its stopping threshold use only inner grouped splits.
- All splits are grouped by source game.
- The consensus subset is locked from January before opening the February confirmation set.

## Method

- Source games / positions: {result['games']} / {result['positions']}
- Outer repeats / test fraction: {result['outer_repeats']} / {result['outer_test_fraction']:.0%}
- Inner repeats / validation fraction: {inner_summary}
- Gain-retention target: {result['retention_fraction']:.0%}
- Target clip: ±{result['target_clip_cp']} cp
- Git revision: {result['git_commit']}
- Runtime: {result['runtime_seconds']:.3f} seconds

## Nested held-out performance

The selected row evaluates a freshly selected subset on each untouched outer fold.
Its parameter count therefore varies; the table reports its median.

| Formula | Median params | MAE cp ± sd | Correlation | Sign accuracy | ≥500 cp |
|---|---:|---:|---:|---:|---:|
{chr(10).join(performance_rows)}

## Selection stability and lock

The upper-median selected size is {consensus['locked_size']} features. Within that
budget, features are ordered by outer-training-fold selection frequency and then
mean selection rank. The resulting locked subset is: {locked}.

| Feature | Selection frequency | Mean selected rank | Locked |
|---|---:|---:|---:|
{chr(10).join(frequency_rows)}

This lock is a January-domain research decision. Its unbiased transfer performance
must be read from the separate February confirmation experiment.
"""


def run_nested_selection(
    database: str | Path,
    config: dict,
    *,
    results_dir: str | Path = "results",
    engine_key: str | None = None,
) -> tuple[dict, Path]:
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    set_deterministic_seed(int(config["seed"]))
    connection = connect_database(database)
    resolved_key = resolve_engine_key(connection, engine_key)
    rows = connection.execute(
        "SELECT p.fen, a.eval_cp, min(o.game_id) AS owner_game "
        "FROM positions p JOIN engine_analysis a USING(position_hash) "
        "JOIN position_occurrences o USING(position_hash) "
        "WHERE a.engine_key = ? GROUP BY p.position_hash, p.fen, a.eval_cp "
        "ORDER BY p.position_hash",
        [resolved_key],
    ).fetchall()
    if not rows:
        raise RuntimeError("No labeled positions are available")
    fens = [row[0] for row in rows]
    game_ids = np.asarray([row[2] for row in rows])
    matrix, feature_names = feature_matrix(fens)
    clip = int(config["model"]["target_clip_cp"])
    target = np.clip(np.asarray([row[1] for row in rows], dtype=float), -clip, clip)
    alpha = float(config["model"]["ridge_alpha"])
    settings = config["feature_selection"]
    outer_splits = grouped_resamples(
        game_ids.tolist(),
        repeats=int(settings["outer_repeats"]),
        test_fraction=float(settings["outer_test_fraction"]),
        seed=int(config["seed"]),
    )
    selected_runs: list[dict] = []
    metric_runs: dict[str, list[dict]] = {
        "material-only": [],
        "nested-selected": [],
        "full-16": [],
    }
    parameter_runs: dict[str, list[int]] = {label: [] for label in metric_runs}
    for outer_index, (train_games, test_games) in enumerate(outer_splits):
        train_mask = np.isin(game_ids, list(train_games))
        test_mask = np.isin(game_ids, list(test_games))
        selection = forward_select_features(
            matrix[train_mask],
            target[train_mask],
            game_ids[train_mask],
            feature_names,
            alpha=alpha,
            repeats=int(settings["inner_repeats"]),
            validation_fraction=float(settings["inner_validation_fraction"]),
            retention_fraction=float(settings["retention_fraction"]),
            seed=int(config["seed"]) + outer_index + 1,
        )
        selected_runs.append(selection)
        evaluated = {
            "material-only": ["material"],
            "nested-selected": selection["selected_features"],
            "full-16": feature_names,
        }
        for label, names in evaluated.items():
            indexes = [feature_names.index(name) for name in names]
            coefficients, intercept = fit_ridge(
                matrix[train_mask][:, indexes], target[train_mask], alpha
            )
            predicted = matrix[test_mask][:, indexes] @ coefficients + intercept
            metric_runs[label].append(calculate_metrics(target[test_mask], predicted))
            parameter_runs[label].append(len(names) + 1)
    consensus = lock_consensus_subset(
        [run["selected_features"] for run in selected_runs], feature_names
    )
    experiment_name = settings.get("experiment_name", "nested-feature-selection")
    experiment_id = _next_experiment_id(Path(results_dir), experiment_name)
    artifact = Path(results_dir) / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    runtime = time.perf_counter() - started
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "git_commit": _git_commit(),
        "engine_key": resolved_key,
        "games": len(set(game_ids.tolist())),
        "positions": len(rows),
        "outer_repeats": len(outer_splits),
        "outer_test_fraction": float(settings["outer_test_fraction"]),
        "inner_repeats": int(settings["inner_repeats"]),
        "inner_validation_fraction": float(settings["inner_validation_fraction"]),
        "retention_fraction": float(settings["retention_fraction"]),
        "target_clip_cp": clip,
        "runtime_seconds": runtime,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "nested_performance": {
            label: {
                "parameter_count": _interval(parameter_runs[label]),
                "metrics": _metric_summary(runs),
            }
            for label, runs in metric_runs.items()
        },
        "consensus_lock": consensus,
        "selection_runs": selected_runs,
    }
    write_json(artifact / "config.json", config)
    write_json(artifact / "metrics.json", result)
    write_json(
        artifact / "locked-subset.json",
        {
            "experiment_id": experiment_id,
            "git_commit": result["git_commit"],
            "selection_rule": "upper median size; frequency then mean-rank ordering",
            **consensus,
        },
    )
    write_json(
        artifact / "environment.json",
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "duckdb": duckdb.__version__,
            "git_commit": result["git_commit"],
        },
    )
    (artifact / "report.md").write_text(_selection_report(result), encoding="utf-8")
    connection.execute(
        "INSERT OR REPLACE INTO experiments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            experiment_id,
            experiment_name,
            json.dumps(config, sort_keys=True),
            result["git_commit"],
            started_at,
            datetime.now(UTC),
            runtime,
            str(artifact),
        ],
    )
    connection.execute(
        "INSERT OR REPLACE INTO benchmark_results VALUES (?, ?, ?, current_timestamp)",
        [experiment_id, config["benchmark_version"], json.dumps(result, sort_keys=True)],
    )
    connection.close()
    return result, artifact
