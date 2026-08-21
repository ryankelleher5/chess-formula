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
from .stability import _interval, position_categories


def grouped_bootstrap_indexes(
    game_ids: list[str] | np.ndarray, *, repeats: int, seed: int
) -> list[np.ndarray]:
    if repeats < 2:
        raise ValueError("bootstrap repeats must be at least 2")
    game_array = np.asarray(game_ids)
    unique_games = np.asarray(sorted(set(game_array.tolist())))
    if len(unique_games) < 2:
        raise ValueError("At least two games are required for grouped bootstrap")
    indexes_by_game = {
        game: np.flatnonzero(game_array == game) for game in unique_games.tolist()
    }
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(repeats):
        sampled_games = rng.choice(unique_games, size=len(unique_games), replace=True)
        samples.append(
            np.concatenate([indexes_by_game[game] for game in sampled_games.tolist()])
        )
    return samples


def _summarize_metric_runs(runs: list[dict]) -> dict:
    names = (
        "evaluation_mae_cp",
        "evaluation_rmse_cp",
        "evaluation_correlation",
        "sign_accuracy",
        "catastrophic_error_rate_500cp",
    )
    return {name: _interval([float(run[name]) for run in runs]) for name in names}


def _save_complexity_plot(artifact: Path, models: dict[str, dict]) -> None:
    labels = list(models)
    parameters = [models[label]["parameter_count"] for label in labels]
    maes = [models[label]["metrics"]["evaluation_mae_cp"] for label in labels]
    correlations = [models[label]["metrics"]["evaluation_correlation"] for label in labels]
    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].plot(parameters, maes, marker="o", color="#dc2626")
    axes[0].set(xlabel="Parameter count", ylabel="Confirmation MAE (cp)")
    axes[1].plot(parameters, correlations, marker="o", color="#2563eb")
    axes[1].set(xlabel="Parameter count", ylabel="Confirmation correlation")
    for axis in axes:
        axis.set_xticks(parameters, labels, rotation=15)
        axis.grid(alpha=0.25)
    figure.suptitle("Frozen February complexity frontier")
    figure.tight_layout()
    figure.savefig(artifact / "confirmation_frontier.png", dpi=150)
    plt.close(figure)


def _confirmation_report(result: dict) -> str:
    model_rows = []
    for label, model in result["models"].items():
        metrics = model["metrics"]
        intervals = model["bootstrap_intervals"]
        mae = intervals["evaluation_mae_cp"]
        correlation = intervals["evaluation_correlation"]
        model_rows.append(
            f"| {label} | {model['parameter_count']} | "
            f"{metrics['evaluation_mae_cp']:.2f} "
            f"[{mae['p2_5']:.2f}, {mae['p97_5']:.2f}] | "
            f"{metrics['evaluation_correlation']:.4f} "
            f"[{correlation['p2_5']:.4f}, {correlation['p97_5']:.4f}] | "
            f"{metrics['sign_accuracy']:.2%} | "
            f"{metrics['catastrophic_error_rate_500cp']:.2%} |"
        )
    category_rows = []
    for label, model in result["models"].items():
        for category, metrics in model["categories"].items():
            category_rows.append(
                f"| {label} | {category} | {result['category_counts'][category]} | "
                f"{metrics['evaluation_mae_cp']:.2f} | "
                f"{metrics['evaluation_correlation']:.4f} |"
            )
    locked = ", ".join(f"`{name}`" for name in result["locked_features"])
    locked_delta = result["paired_mae_deltas"]["locked-minus-material"]
    full_delta = result["paired_mae_deltas"]["full-minus-locked"]
    confirmation_before = result["confirmation_positions_before_exclusion"]
    return f"""# Frozen Transfer Confirmation: {result['experiment_id']}

## Question

Does the January-locked minimum subset transfer unchanged to an independent
February human-game sample?

## Prospective controls

- Locked features: {locked}
- Coefficients are trained only on the complete January corpus.
- February does not affect features, coefficients, ridge alpha, or stopping rules.
- Exact confirmation positions also found in January are excluded.
- Uncertainty comes from {result['bootstrap_repeats']} source-game bootstrap samples.

## Data

- Training games / positions: {result['training_games']} / {result['training_positions']}
- Confirmation games: {result['confirmation_games']}
- Confirmation positions before overlap exclusion: {confirmation_before}
- Exact cross-month overlaps excluded: {result['cross_month_positions_excluded']}
- Confirmation positions evaluated: {result['confirmation_positions']}
- Source: {result['confirmation_source']}
- Engine key: `{result['engine_key']}`
- Target clip: ±{result['target_clip_cp']} cp
- Git revision: {result['git_commit']}
- Runtime: {result['runtime_seconds']:.3f} seconds

## Confirmation performance

Brackets are 95% game-clustered bootstrap intervals.

| Formula | Params | MAE cp [95%] | Correlation [95%] | Sign accuracy | ≥500 cp |
|---|---:|---:|---:|---:|---:|
{chr(10).join(model_rows)}

Paired bootstrap MAE differences (negative favors the first named model):

- locked minus material: {locked_delta['mean']:+.2f} cp
  [{locked_delta['p2_5']:+.2f}, {locked_delta['p97_5']:+.2f}]
- full minus locked: {full_delta['mean']:+.2f} cp
  [{full_delta['p2_5']:+.2f}, {full_delta['p97_5']:+.2f}]

## Domain strata

| Formula | Stratum | Positions | MAE cp | Correlation |
|---|---|---:|---:|---:|
{chr(10).join(category_rows)}

## Guardrail

This is a one-shot test of Stockfish depth-8 evaluation transfer between two
small early-Lichess samples. It is not a measure of move choice or playing strength.
The February set remains confirmation data and must not be used to repair the lock.
"""


def _labeled_rows(connection, engine_key: str) -> list[tuple]:
    return connection.execute(
        "SELECT p.position_hash, p.fen, a.eval_cp, min(o.game_id) AS owner_game "
        "FROM positions p JOIN engine_analysis a USING(position_hash) "
        "JOIN position_occurrences o USING(position_hash) "
        "WHERE a.engine_key = ? "
        "GROUP BY p.position_hash, p.fen, a.eval_cp ORDER BY p.position_hash",
        [engine_key],
    ).fetchall()


def run_transfer_confirmation(
    training_database: str | Path,
    confirmation_database: str | Path,
    config: dict,
    *,
    results_dir: str | Path = "results",
    engine_key: str | None = None,
) -> tuple[dict, Path]:
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    seed = int(config["seed"])
    set_deterministic_seed(seed)
    training_connection = connect_database(training_database)
    confirmation_connection = connect_database(confirmation_database)
    training_key = resolve_engine_key(training_connection, engine_key)
    confirmation_key = resolve_engine_key(confirmation_connection, engine_key)
    if training_key != confirmation_key:
        raise ValueError("Training and confirmation engine configurations do not match")
    training_rows = _labeled_rows(training_connection, training_key)
    all_confirmation_rows = _labeled_rows(confirmation_connection, confirmation_key)
    if not training_rows or not all_confirmation_rows:
        raise RuntimeError("Both training and confirmation databases need labeled positions")
    training_hashes = {row[0] for row in training_rows}
    confirmation_rows = [row for row in all_confirmation_rows if row[0] not in training_hashes]
    if not confirmation_rows:
        raise RuntimeError("No confirmation positions remain after overlap exclusion")

    training_fens = [row[1] for row in training_rows]
    confirmation_fens = [row[1] for row in confirmation_rows]
    training_matrix, feature_names = feature_matrix(training_fens)
    confirmation_matrix, _ = feature_matrix(confirmation_fens, feature_names)
    clip = int(config["model"]["target_clip_cp"])
    training_target = np.clip(
        np.asarray([row[2] for row in training_rows], dtype=float), -clip, clip
    )
    confirmation_target = np.clip(
        np.asarray([row[2] for row in confirmation_rows], dtype=float), -clip, clip
    )
    confirmation_games = np.asarray([row[3] for row in confirmation_rows])
    settings = config["confirmation"]
    locked_features = list(settings["locked_features"])
    if locked_features != ["material", "space", "tempo"]:
        raise ValueError("Confirmation feature lock does not match transferable-subset-v1")
    feature_sets = {
        "material-only": ["material"],
        "locked-3": locked_features,
        "full-16": feature_names,
    }
    alpha = float(config["model"]["ridge_alpha"])
    predictions: dict[str, np.ndarray] = {}
    models = {}
    categories = position_categories(confirmation_fens, confirmation_matrix, feature_names)
    for label, names in feature_sets.items():
        indexes = [feature_names.index(name) for name in names]
        coefficients, intercept = fit_ridge(
            training_matrix[:, indexes], training_target, alpha
        )
        predicted = confirmation_matrix[:, indexes] @ coefficients + intercept
        predictions[label] = predicted
        category_metrics = {
            category: calculate_metrics(confirmation_target[mask], predicted[mask])
            for category, mask in categories.items()
            if int(mask.sum()) >= 2
        }
        models[label] = {
            "features": names,
            "parameter_count": len(names) + 1,
            "coefficients": coefficients.tolist(),
            "intercept": intercept,
            "metrics": calculate_metrics(confirmation_target, predicted),
            "categories": category_metrics,
        }

    bootstrap_indexes = grouped_bootstrap_indexes(
        confirmation_games,
        repeats=int(settings["bootstrap_repeats"]),
        seed=seed,
    )
    bootstrap_runs: dict[str, list[dict]] = {label: [] for label in models}
    locked_minus_material = []
    full_minus_locked = []
    for indexes in bootstrap_indexes:
        run_metrics = {}
        for label, predicted in predictions.items():
            metrics = calculate_metrics(confirmation_target[indexes], predicted[indexes])
            bootstrap_runs[label].append(metrics)
            run_metrics[label] = metrics
        locked_minus_material.append(
            run_metrics["locked-3"]["evaluation_mae_cp"]
            - run_metrics["material-only"]["evaluation_mae_cp"]
        )
        full_minus_locked.append(
            run_metrics["full-16"]["evaluation_mae_cp"]
            - run_metrics["locked-3"]["evaluation_mae_cp"]
        )
    for label in models:
        models[label]["bootstrap_intervals"] = _summarize_metric_runs(
            bootstrap_runs[label]
        )

    experiment_name = settings.get("experiment_name", "transfer-confirmation")
    experiment_id = _next_experiment_id(Path(results_dir), experiment_name)
    artifact = Path(results_dir) / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    runtime = time.perf_counter() - started
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "git_commit": _git_commit(),
        "engine_key": training_key,
        "training_games": len({row[3] for row in training_rows}),
        "training_positions": len(training_rows),
        "confirmation_games": len(set(confirmation_games.tolist())),
        "confirmation_positions_before_exclusion": len(all_confirmation_rows),
        "cross_month_positions_excluded": len(all_confirmation_rows) - len(confirmation_rows),
        "confirmation_positions": len(confirmation_rows),
        "confirmation_source": config["human_corpus"]["source_url"],
        "locked_features": locked_features,
        "target_clip_cp": clip,
        "bootstrap_repeats": len(bootstrap_indexes),
        "category_counts": {name: int(mask.sum()) for name, mask in categories.items()},
        "models": models,
        "paired_mae_deltas": {
            "locked-minus-material": _interval(locked_minus_material),
            "full-minus-locked": _interval(full_minus_locked),
        },
        "runtime_seconds": runtime,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    write_json(artifact / "config.json", config)
    write_json(artifact / "metrics.json", result)
    write_json(
        artifact / "models.json",
        {
            label: {
                "features": model["features"],
                "coefficients": model["coefficients"],
                "intercept": model["intercept"],
            }
            for label, model in models.items()
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
    (artifact / "report.md").write_text(_confirmation_report(result), encoding="utf-8")
    _save_complexity_plot(artifact, models)
    confirmation_connection.execute(
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
    confirmation_connection.execute(
        "INSERT OR REPLACE INTO benchmark_results VALUES (?, ?, ?, current_timestamp)",
        [experiment_id, config["benchmark_version"], json.dumps(result, sort_keys=True)],
    )
    training_connection.close()
    confirmation_connection.close()
    return result, artifact
