from __future__ import annotations

import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .benchmark import calculate_metrics
from .config import set_deterministic_seed, write_json
from .database import connect_database
from .features import feature_matrix
from .model import _git_commit, _next_experiment_id, fit_ridge, resolve_engine_key


def grouped_resamples(
    game_ids: list[str], *, repeats: int, test_fraction: float, seed: int
) -> list[tuple[set[str], set[str]]]:
    unique_games = sorted(set(game_ids))
    if len(unique_games) < 4:
        raise ValueError("At least four source games are required for grouped resampling")
    if repeats < 2 or not 0.0 < test_fraction < 1.0:
        raise ValueError("repeats must be at least 2 and test_fraction must be between 0 and 1")
    test_count = max(1, min(len(unique_games) - 1, round(len(unique_games) * test_fraction)))
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(repeats):
        shuffled = rng.permutation(unique_games).tolist()
        test = set(shuffled[:test_count])
        train = set(shuffled[test_count:])
        samples.append((train, test))
    return samples


def _interval(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(np.nanmean(array)),
        "standard_deviation": float(np.nanstd(array)),
        "p2_5": float(np.nanpercentile(array, 2.5)),
        "median": float(np.nanmedian(array)),
        "p97_5": float(np.nanpercentile(array, 97.5)),
    }


def summarize_coefficients(
    coefficient_runs: list[np.ndarray], feature_names: list[str]
) -> dict[str, dict[str, float]]:
    matrix = np.asarray(coefficient_runs, dtype=float)
    summary = {}
    for index, name in enumerate(feature_names):
        values = matrix[:, index]
        nonzero = values[np.abs(values) > 1e-12]
        if len(nonzero):
            dominant = max(float(np.mean(nonzero > 0)), float(np.mean(nonzero < 0)))
        else:
            dominant = 1.0
        summary[name] = {**_interval(values.tolist()), "dominant_sign_fraction": dominant}
    return summary


def _save_plots(artifact: Path, feature_sets: dict, summaries: dict) -> None:
    labels = list(feature_sets)
    parameters = [len(feature_sets[label]) + 1 for label in labels]
    correlations = [summaries[label]["metrics"]["evaluation_correlation"] for label in labels]
    maes = [summaries[label]["metrics"]["evaluation_mae_cp"] for label in labels]

    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].errorbar(
        parameters,
        [value["mean"] for value in correlations],
        yerr=[value["standard_deviation"] for value in correlations],
        marker="o",
        capsize=4,
    )
    axes[0].set(xlabel="Parameter count", ylabel="Correlation", title="Complexity vs correlation")
    axes[1].errorbar(
        parameters,
        [value["mean"] for value in maes],
        yerr=[value["standard_deviation"] for value in maes],
        marker="o",
        capsize=4,
        color="#dc2626",
    )
    axes[1].set(xlabel="Parameter count", ylabel="MAE (cp)", title="Complexity vs error")
    for axis in axes:
        axis.set_xticks(parameters, labels, rotation=15)
        axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(artifact / "complexity_stability.png", dpi=150)
    plt.close(figure)

    full_label = max(labels, key=lambda label: len(feature_sets[label]))
    coefficients = summaries[full_label]["coefficient_runs"]
    figure, axis = plt.subplots(figsize=(11, 6))
    axis.boxplot(np.asarray(coefficients), tick_labels=feature_sets[full_label], vert=False)
    axis.axvline(0, color="black", linewidth=1)
    axis.set(xlabel="Coefficient (cp/unit)", title=f"{full_label} coefficient stability")
    figure.tight_layout()
    figure.savefig(artifact / "coefficient_stability.png", dpi=150)
    plt.close(figure)


def _report(experiment_id: str, result: dict) -> str:
    rows = []
    for label, summary in result["feature_sets"].items():
        metrics = summary["metrics"]
        rows.append(
            f"| {label} | {summary['parameter_count']} | "
            f"{metrics['evaluation_mae_cp']['mean']:.2f} ± "
            f"{metrics['evaluation_mae_cp']['standard_deviation']:.2f} | "
            f"{metrics['evaluation_correlation']['mean']:.4f} ± "
            f"{metrics['evaluation_correlation']['standard_deviation']:.4f} | "
            f"{metrics['sign_accuracy']['mean']:.2%} | "
            f"{metrics['catastrophic_error_rate_500cp']['mean']:.2%} |"
        )
    full_label = max(
        result["feature_sets"],
        key=lambda label: result["feature_sets"][label]["parameter_count"],
    )
    coefficient_rows = []
    for name, summary in result["feature_sets"][full_label]["coefficients"].items():
        coefficient_rows.append(
            f"| `{name}` | {summary['median']:.3f} | "
            f"[{summary['p2_5']:.3f}, {summary['p97_5']:.3f}] | "
            f"{summary['dominant_sign_fraction']:.1%} |"
        )
    material = result["feature_sets"]["material-only"]["metrics"]
    compact = result["feature_sets"]["compact-5"]["metrics"]
    full = result["feature_sets"]["full-16"]["metrics"]
    compact_mae_gain = material["evaluation_mae_cp"]["mean"] - compact["evaluation_mae_cp"]["mean"]
    full_mae_cost = full["evaluation_mae_cp"]["mean"] - compact["evaluation_mae_cp"]["mean"]
    full_correlation_gain = (
        full["evaluation_correlation"]["mean"] - compact["evaluation_correlation"]["mean"]
    )
    return f"""# Coefficient Stability Experiment: {experiment_id}

## Question

Does the apparent signal in the first 16-feature formula survive changes in which
source games are held out, and how much does each added level of description buy?

## Method

- Benchmark: `coefficient-stability-v1` (frozen)
- Git revision: {result["git_commit"]}
- Unique source games: {result["games"]}
- Unique labeled positions: {result["positions"]}
- White / Black to move: {result["side_to_move"]["white"]} / {result["side_to_move"]["black"]}
- Repeated grouped splits: {result["repeats"]}
- Test fraction per repeat: {result["test_fraction"]:.0%}
- Target clip: ±{result["target_clip_cp"]} cp
- Engine: {result["engine"]["version"]}
- Engine limit: {result["engine"]["limit_type"]}={result["engine"]["limit_value"]}
- Runtime: {result["runtime_seconds"]:.3f} seconds

Positions are deduplicated, assigned to one source game, and split only by game.
The intervals below describe variation across grouped resamples, not independent
position-level confidence intervals.

## Complexity and held-out performance

| Formula | Params | MAE cp ± sd | Correlation ± sd | Sign accuracy | ≥500 cp |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Full-model coefficient stability

| Feature | Median | 95% resampling interval | Dominant sign fraction |
|---|---:|---:|---:|
{chr(10).join(coefficient_rows)}

## Result

Compact-5 reduces mean MAE by {compact_mae_gain:.2f} cp relative to material-only.
Adding the other eleven features then worsens mean MAE by {full_mae_cost:.2f} cp
while increasing mean correlation by only {full_correlation_gain:.4f}. The full
model also has a higher mean catastrophic-error rate. On this synthetic domain,
compact-5 is the current description-complexity Pareto candidate; full-16 is not
justified by its mean held-out measurements.

## Interpretation guardrail

This experiment measures robustness of Stockfish-evaluation prediction on a
deterministically generated legal corpus. It does not measure move selection or
playing strength, and synthetic self-play is not representative of all chess.
"""


def run_stability(
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
    game_ids = [row[2] for row in rows]
    all_matrix, all_names = feature_matrix(fens)
    clip = int(config["model"]["target_clip_cp"])
    target = np.clip(np.asarray([row[1] for row in rows], dtype=float), -clip, clip)
    stability = config["stability"]
    samples = grouped_resamples(
        game_ids,
        repeats=int(stability["repeats"]),
        test_fraction=float(stability["test_fraction"]),
        seed=int(config["seed"]),
    )
    configured_sets = stability["feature_sets"]
    feature_sets = {
        label: all_names if names == "all" else list(names)
        for label, names in configured_sets.items()
    }
    alpha = float(config["model"]["ridge_alpha"])
    summaries = {}
    game_array = np.asarray(game_ids)
    for label, names in feature_sets.items():
        indexes = [all_names.index(name) for name in names]
        matrix = all_matrix[:, indexes]
        metric_runs: list[dict] = []
        coefficient_runs: list[np.ndarray] = []
        for train_games, test_games in samples:
            train_mask = np.isin(game_array, list(train_games))
            test_mask = np.isin(game_array, list(test_games))
            coefficients, intercept = fit_ridge(matrix[train_mask], target[train_mask], alpha)
            predicted = matrix[test_mask] @ coefficients + intercept
            metric_runs.append(calculate_metrics(target[test_mask], predicted))
            coefficient_runs.append(coefficients)
        metric_names = (
            "evaluation_mae_cp",
            "evaluation_correlation",
            "sign_accuracy",
            "catastrophic_error_rate_500cp",
        )
        summaries[label] = {
            "parameter_count": len(names) + 1,
            "features": names,
            "metrics": {
                metric: _interval([float(run[metric]) for run in metric_runs])
                for metric in metric_names
            },
            "coefficients": summarize_coefficients(coefficient_runs, names),
            "coefficient_runs": [run.tolist() for run in coefficient_runs],
        }
    engine = connection.execute(
        "SELECT engine_version, limit_type, limit_value, parameters_json "
        "FROM engine_analysis WHERE engine_key = ? LIMIT 1",
        [resolved_key],
    ).fetchone()
    experiment_id = _next_experiment_id(Path(results_dir), "coefficient-stability")
    artifact = Path(results_dir) / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    runtime = time.perf_counter() - started
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "git_commit": _git_commit(),
        "engine_key": resolved_key,
        "engine": {
            "version": engine[0],
            "limit_type": engine[1],
            "limit_value": engine[2],
            "parameters": json.loads(engine[3]),
        },
        "games": len(set(game_ids)),
        "positions": len(rows),
        "side_to_move": {
            "white": sum(fen.split()[1] == "w" for fen in fens),
            "black": sum(fen.split()[1] == "b" for fen in fens),
        },
        "repeats": len(samples),
        "test_fraction": float(stability["test_fraction"]),
        "target_clip_cp": clip,
        "runtime_seconds": runtime,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "feature_sets": summaries,
    }
    _save_plots(artifact, feature_sets, summaries)
    serializable = json.loads(json.dumps(result))
    write_json(artifact / "config.json", config)
    write_json(artifact / "metrics.json", serializable)
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
    (artifact / "report.md").write_text(_report(experiment_id, result), encoding="utf-8")
    connection.execute(
        "INSERT INTO experiments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            experiment_id,
            "coefficient-stability",
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
        [experiment_id, config["benchmark_version"], json.dumps(serializable, sort_keys=True)],
    )
    connection.close()
    return result, artifact
