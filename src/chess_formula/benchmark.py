from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .config import write_json
from .database import connect_database
from .features import feature_matrix
from .model import LinearModel, _git_commit


def calculate_metrics(target: np.ndarray, predicted: np.ndarray) -> dict[str, float | int]:
    if target.size == 0:
        raise ValueError("Cannot benchmark an empty test set")
    error = predicted - target
    correlation = float(np.corrcoef(target, predicted)[0, 1]) if target.size > 1 else float("nan")
    sign_target = np.sign(target)
    sign_predicted = np.sign(predicted)
    return {
        "positions": int(target.size),
        "evaluation_mae_cp": float(np.mean(np.abs(error))),
        "evaluation_rmse_cp": float(np.sqrt(np.mean(error**2))),
        "evaluation_correlation": correlation,
        "sign_accuracy": float(np.mean(sign_target == sign_predicted)),
        "catastrophic_error_rate_500cp": float(np.mean(np.abs(error) >= 500.0)),
    }


def _save_plots(
    artifact: Path, target: np.ndarray, predicted: np.ndarray, phase: np.ndarray
) -> None:
    figure, axis = plt.subplots(figsize=(6, 5))
    axis.scatter(target, predicted, alpha=0.65, s=20)
    low, high = min(target.min(), predicted.min()), max(target.max(), predicted.max())
    axis.plot([low, high], [low, high], "--", color="black", linewidth=1)
    axis.set(
        xlabel="Stockfish evaluation (cp, clipped)",
        ylabel="Linear prediction (cp)",
        title="Held-out predictions",
    )
    figure.tight_layout()
    figure.savefig(artifact / "predicted_vs_stockfish.png", dpi=150)
    plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    error = predicted - target
    axes[0].hist(error, bins=min(20, max(5, len(error) // 2)), color="#3b82f6", alpha=0.8)
    axes[0].set(xlabel="Prediction error (cp)", ylabel="Count", title="Error distribution")
    axes[1].scatter(phase, np.abs(error), alpha=0.65, s=20, color="#dc2626")
    axes[1].set(
        xlabel="Game phase (1 ≈ opening)", ylabel="Absolute error (cp)", title="Error vs phase"
    )
    figure.tight_layout()
    figure.savefig(artifact / "error_analysis.png", dpi=150)
    plt.close(figure)


def _dataset_summary(connection, engine_key: str) -> dict:
    games = connection.execute("SELECT count(*) FROM games").fetchone()[0]
    occurrences = connection.execute("SELECT count(*) FROM position_occurrences").fetchone()[0]
    unique = connection.execute("SELECT count(*) FROM positions").fetchone()[0]
    split_rows = connection.execute(
        "SELECT split, count(*) FROM positions GROUP BY split ORDER BY split"
    ).fetchall()
    evaluation = connection.execute(
        "SELECT count(*), min(eval_cp), max(eval_cp), avg(eval_cp), stddev_pop(eval_cp), "
        "sum(CASE WHEN mate IS NOT NULL THEN 1 ELSE 0 END) "
        "FROM engine_analysis WHERE engine_key = ?",
        [engine_key],
    ).fetchone()
    engine = connection.execute(
        "SELECT engine_version, limit_type, limit_value, multipv, parameters_json "
        "FROM engine_analysis WHERE engine_key = ? LIMIT 1",
        [engine_key],
    ).fetchone()
    return {
        "games": games,
        "extracted_positions": occurrences,
        "unique_positions": unique,
        "split_sizes": dict(split_rows),
        "stockfish": {
            "labels": evaluation[0],
            "minimum_cp": evaluation[1],
            "maximum_cp": evaluation[2],
            "mean_cp": evaluation[3],
            "standard_deviation_cp": evaluation[4],
            "mate_scores": evaluation[5],
            "engine_version": engine[0] if engine else None,
            "limit_type": engine[1] if engine else None,
            "limit_value": engine[2] if engine else None,
            "multipv": engine[3] if engine else None,
            "parameters": json.loads(engine[4]) if engine else None,
        },
    }


def _report(model: LinearModel, dataset: dict, metrics: dict, runtime: float) -> str:
    split = dataset["split_sizes"]
    stockfish = dataset["stockfish"]
    coefficient_rows = "\n".join(
        f"| `{name}` | {coefficient:.6f} |"
        for name, coefficient in zip(model.feature_names, model.coefficients, strict=True)
    )
    formula = model.formula().rstrip()
    return f"""# Baseline Linear Experiment: {model.experiment_id}

## Hypothesis

A small, inspectable linear combination of human-readable position features can
preserve a measurable portion of shallow Stockfish judgment on unseen games.

## Reproducibility

- Benchmark: `baseline-v1` (frozen)
- Benchmark Git revision: {metrics["benchmark_git_commit"]}
- Evaluation convention: positive means advantage for White
- Training target and benchmark labels are clipped to ±{model.target_clip_cp} cp;
  raw oracle statistics remain recorded below
- Engine: {stockfish["engine_version"]}
- Limit: {stockfish["limit_type"]}={stockfish["limit_value"]}, MultiPV={stockfish["multipv"]}
- Parameters: {stockfish["parameters"]}
- Benchmark and report runtime: {runtime:.3f} seconds

## Dataset

- Games: {dataset["games"]}
- Extracted position occurrences: {dataset["extracted_positions"]}
- Unique positions: {dataset["unique_positions"]}
- Train: {split.get("train", 0)}
- Validation: {split.get("validation", 0)}
- Test: {split.get("test", 0)}
- Oracle labels: {stockfish["labels"]}
- Raw oracle cp minimum: {stockfish["minimum_cp"]}
- Raw oracle cp mean: {stockfish["mean_cp"]:.2f}
- Raw oracle cp maximum: {stockfish["maximum_cp"]}
- Raw oracle cp standard deviation: {stockfish["standard_deviation_cp"]:.2f}
- Mate evaluations: {stockfish["mate_scores"]}

## Held-out results

- Evaluation MAE: {metrics["evaluation_mae_cp"]:.2f} cp
- Evaluation RMSE: {metrics["evaluation_rmse_cp"]:.2f} cp
- Evaluation correlation: {metrics["evaluation_correlation"]:.4f}
- Sign accuracy: {metrics["sign_accuracy"]:.2%}
- Catastrophic error rate (≥500 cp): {metrics["catastrophic_error_rate_500cp"]:.2%}
- Inference latency: {metrics["inference_latency_us"]:.3f} µs/position (feature extraction excluded)
- Parameter count: {metrics["parameter_count"]}

## Features and learned coefficients

| Feature | Coefficient (cp/unit) |
|---|---:|
{coefficient_rows}

## Explicit formula

```text
{formula}
```

## Interpretation

This is a pipeline-validation experiment on a deliberately tiny sample, not evidence
of playing strength or a law of chess. Stockfish prediction, move prediction, and
objective play remain distinct objectives. The held-out sample is too small for
stable scientific conclusions.
"""


def benchmark_linear(
    database: str | Path,
    config: dict,
    *,
    model_path: str | Path = "models/baseline-linear.json",
    results_dir: str | Path = "results",
) -> tuple[dict, Path]:
    started = time.perf_counter()
    model = LinearModel.load(model_path)
    connection = connect_database(database)
    rows = connection.execute(
        "SELECT p.fen, a.eval_cp FROM positions p JOIN engine_analysis a USING(position_hash) "
        "WHERE p.split = 'test' AND a.engine_key = ? ORDER BY p.position_hash",
        [model.engine_key],
    ).fetchall()
    if not rows:
        raise RuntimeError("The held-out test split is empty; add more source games")
    matrix, _ = feature_matrix([row[0] for row in rows], model.feature_names)
    clip = model.target_clip_cp
    target = np.clip(np.asarray([row[1] for row in rows], dtype=float), -clip, clip)
    timing_repeats = max(100, int(10000 / len(rows)))
    timing_started = time.perf_counter()
    for _ in range(timing_repeats):
        predicted = model.predict(matrix)
    inference_seconds = time.perf_counter() - timing_started
    metrics = calculate_metrics(target, predicted)
    metrics.update(
        {
            "inference_latency_us": inference_seconds * 1e6 / (timing_repeats * len(rows)),
            "parameter_count": len(model.coefficients) + 1,
            "approximate_operations_per_evaluation": 2 * len(model.coefficients) + 1,
            "benchmark_version": config["benchmark_version"],
            "benchmark_git_commit": _git_commit(),
            "target_clip_cp": clip,
        }
    )
    artifact = Path(results_dir) / model.experiment_id
    artifact.mkdir(parents=True, exist_ok=True)
    _save_plots(artifact, target, predicted, matrix[:, model.feature_names.index("game_phase")])
    dataset = _dataset_summary(connection, model.engine_key)
    runtime = time.perf_counter() - started
    metrics["benchmark_runtime_seconds"] = runtime
    write_json(artifact / "metrics.json", metrics)
    write_json(artifact / "dataset.json", dataset)
    (artifact / "report.md").write_text(_report(model, dataset, metrics, runtime), encoding="utf-8")
    connection.execute(
        "INSERT OR REPLACE INTO benchmark_results VALUES (?, ?, ?, current_timestamp)",
        [model.experiment_id, config["benchmark_version"], json.dumps(metrics, sort_keys=True)],
    )
    connection.close()
    return metrics, artifact
