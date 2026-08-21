from __future__ import annotations

import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

import chess
import duckdb
import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .benchmark import calculate_metrics
from .config import set_deterministic_seed, write_json
from .confirmation import _labeled_rows, grouped_bootstrap_indexes
from .database import connect_database
from .features import feature_matrix
from .march import StaticFormula, _metric_intervals, pool_development_rows, selective_minimax
from .model import _git_commit, _next_experiment_id, fit_ridge, resolve_engine_key
from .stability import _interval, position_categories


def interval_excludes_zero_below(summary: dict[str, float]) -> bool:
    return bool(summary["mean"] < 0 and summary["p97_5"] < 0)


def prior_position_hashes(databases: list[str | Path]) -> set[str]:
    hashes: set[str] = set()
    for database in databases:
        connection = connect_database(database)
        hashes.update(row[0] for row in connection.execute("SELECT position_hash FROM positions"))
        connection.close()
    return hashes


def _engine_metadata(connection, engine_key: str) -> dict:
    row = connection.execute(
        "SELECT engine_version, limit_type, limit_value, multipv, parameters_json "
        "FROM engine_analysis WHERE engine_key = ? LIMIT 1",
        [engine_key],
    ).fetchone()
    if row is None:
        raise RuntimeError(f"No engine metadata for {engine_key}")
    return {
        "engine_version": row[0],
        "limit_type": row[1],
        "limit_value": row[2],
        "multipv": row[3],
        "parameters": json.loads(row[4]),
    }


def _save_plot(artifact: Path, models: dict) -> None:
    labels = list(models)
    overall = [models[label]["metrics"]["evaluation_mae_cp"] for label in labels]
    forcing = [
        models[label]["categories"]["forcing-proxy"]["evaluation_mae_cp"]
        for label in labels
    ]
    x = np.arange(len(labels))
    width = 0.38
    figure, axis = plt.subplots(figsize=(9, 5))
    axis.bar(x - width / 2, overall, width, label="overall")
    axis.bar(x + width / 2, forcing, width, label="forcing proxy")
    axis.set(
        ylabel="MAE against depth-12 Stockfish (cp)",
        title="April deeper-oracle robustness",
        xticks=x,
        xticklabels=labels,
    )
    axis.tick_params(axis="x", rotation=15)
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(artifact / "depth_robustness.png", dpi=150)
    plt.close(figure)


def _report(result: dict) -> str:
    rows = []
    for label, model in result["models"].items():
        metrics = model["metrics"]
        forcing = model["categories"]["forcing-proxy"]
        search = model.get("search")
        expanded = search["mean_expanded_children"] if search else 0.0
        rows.append(
            f"| {label} | {model['parameter_count']} | "
            f"{metrics['evaluation_mae_cp']:.2f} | "
            f"{forcing['evaluation_mae_cp']:.2f} | "
            f"{metrics['evaluation_correlation']:.4f} | "
            f"{metrics['sign_accuracy']:.2%} | "
            f"{metrics['catastrophic_error_rate_500cp']:.2%} | {expanded:.1f} |"
        )
    delta_rows = [
        f"| {label} | {summary['mean']:+.2f} | "
        f"[{summary['p2_5']:+.2f}, {summary['p97_5']:+.2f}] |"
        for label, summary in result["paired_mae_deltas"].items()
    ]
    development = result["development"]
    development_oracle = result["development_engine"]
    confirmation_oracle = result["confirmation_engine"]
    development_limit = (
        f"{development_oracle['limit_type']}={development_oracle['limit_value']}"
    )
    confirmation_limit = (
        f"{confirmation_oracle['limit_type']}={confirmation_oracle['limit_value']}"
    )
    return f"""# April Deeper-Oracle Robustness: {result['experiment_id']}

## Question

Does the frozen Searched Locked-3 advantage survive an untouched human-game
domain evaluated by a deeper Stockfish oracle?

## Frozen controls

- Protocol Git revision: {result['git_commit']}
- Development oracle: {development_limit}
- April oracle: {confirmation_limit}
- Coefficients use only January/February development positions.
- Search vocabulary, ordering, two-ply depth, stand-pat, and 128-child cap are unchanged.
- April hashes seen in January, February, or March are excluded.
- Search uses compact formula leaves and never calls Stockfish.

## Data

- Development unique positions: {development['unique_positions']}
- April games: {result['confirmation_games']}
- April positions before exclusion: {result['confirmation_positions_before_exclusion']}
- Prior-domain overlaps excluded: {result['prior_domain_positions_excluded']}
- April positions evaluated: {result['confirmation_positions']}
- Forcing-proxy positions: {result['category_counts']['forcing-proxy']}
- Bootstrap repeats: {result['bootstrap_repeats']}
- Runtime: {result['runtime_seconds']:.3f} seconds

## Deeper-oracle performance

| Candidate | Params | Overall MAE | Forcing MAE | Correlation | Sign | ≥500 cp | Mean expanded |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Paired game-bootstrap contrasts

Negative values favor the first named candidate.

| Contrast | Mean MAE difference | 95% interval |
|---|---:|---:|
{chr(10).join(delta_rows)}

- Search gain survives deeper oracle: **{result['decision']['search_gain_survives']}**

## Guardrail

This remains position-value prediction, not legal move selection or playing
strength. The depth-12 oracle is stronger than the development target but is not
game-theoretic truth.
"""


def run_depth_robustness(
    development_databases: list[str | Path],
    prior_databases: list[str | Path],
    confirmation_database: str | Path,
    config: dict,
    *,
    results_dir: str | Path = "results",
) -> tuple[dict, Path]:
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    seed = int(config["seed"])
    set_deterministic_seed(seed)
    settings = config["depth_robustness"]
    development_key = settings["development_engine_key"]
    development_rows, resolved_development_key, development_audit = pool_development_rows(
        development_databases, development_key
    )
    if resolved_development_key != development_key:
        raise ValueError("Resolved development engine key differs from frozen key")
    development_connection = connect_database(development_databases[0])
    development_engine = _engine_metadata(development_connection, development_key)
    development_connection.close()

    confirmation_connection = connect_database(confirmation_database)
    confirmation_key = resolve_engine_key(confirmation_connection, None)
    confirmation_engine = _engine_metadata(confirmation_connection, confirmation_key)
    if confirmation_engine["engine_version"] != development_engine["engine_version"]:
        raise ValueError("Development and confirmation engine versions differ")
    expected_depth = int(settings["confirmation_depth"])
    if (
        confirmation_engine["limit_type"] != "depth"
        or int(confirmation_engine["limit_value"]) != expected_depth
    ):
        raise ValueError("Confirmation engine does not match the frozen depth")

    all_confirmation_rows = _labeled_rows(confirmation_connection, confirmation_key)
    prior_hashes = prior_position_hashes(prior_databases)
    confirmation_rows = [row for row in all_confirmation_rows if row[0] not in prior_hashes]
    if not confirmation_rows:
        raise RuntimeError("No April positions remain after prior-domain exclusion")

    development_matrix, feature_names = feature_matrix([row[1] for row in development_rows])
    confirmation_fens = [row[1] for row in confirmation_rows]
    confirmation_matrix, _ = feature_matrix(confirmation_fens, feature_names)
    clip = int(config["model"]["target_clip_cp"])
    development_target = np.clip(
        np.asarray([row[2] for row in development_rows], dtype=float), -clip, clip
    )
    target = np.clip(
        np.asarray([row[2] for row in confirmation_rows], dtype=float), -clip, clip
    )
    game_ids = np.asarray([row[3] for row in confirmation_rows])
    alpha = float(config["model"]["ridge_alpha"])
    static_sets = {
        label: feature_names if names == "all" else list(names)
        for label, names in settings["static_candidates"].items()
    }
    formulas = {}
    predictions = {}
    for label, names in static_sets.items():
        indexes = [feature_names.index(name) for name in names]
        coefficients, intercept = fit_ridge(
            development_matrix[:, indexes], development_target, alpha
        )
        formulas[label] = StaticFormula(names, coefficients, intercept)
        predictions[label] = confirmation_matrix[:, indexes] @ coefficients + intercept

    search_settings = settings["forcing_search"]
    searched = []
    expanded_counts = []
    search_started = time.perf_counter()
    for fen in confirmation_fens:
        value, expanded = selective_minimax(
            chess.Board(fen),
            formulas["locked-3"].evaluate,
            depth_plies=int(search_settings["depth_plies"]),
            maximum_expanded_children=int(search_settings["maximum_expanded_children"]),
            terminal_cp=float(search_settings["terminal_win_loss_cp"]),
        )
        searched.append(value)
        expanded_counts.append(expanded)
    search_seconds = time.perf_counter() - search_started
    predictions["searched-3"] = np.asarray(searched)
    search_audit = {
        "source_formula": "locked-3",
        "depth_plies": int(search_settings["depth_plies"]),
        "maximum_expanded_children": int(search_settings["maximum_expanded_children"]),
        "mean_expanded_children": float(np.mean(expanded_counts)),
        "p95_expanded_children": float(np.percentile(expanded_counts, 95)),
        "maximum_observed_expanded_children": int(max(expanded_counts)),
        "positions_hitting_budget": int(
            np.sum(
                np.asarray(expanded_counts)
                >= int(search_settings["maximum_expanded_children"])
            )
        ),
        "runtime_seconds": search_seconds,
        "latency_ms_per_position": search_seconds * 1000 / len(confirmation_rows),
    }

    categories = position_categories(confirmation_fens, confirmation_matrix, feature_names)
    models = {}
    for label, predicted in predictions.items():
        source = "locked-3" if label == "searched-3" else label
        names = static_sets[source]
        models[label] = {
            "features": names,
            "parameter_count": len(names) + 1,
            "coefficients": formulas[source].coefficients.tolist(),
            "intercept": formulas[source].intercept,
            "metrics": calculate_metrics(target, predicted),
            "categories": {
                category: calculate_metrics(target[mask], predicted[mask])
                for category, mask in categories.items()
                if int(mask.sum()) >= 2
            },
        }
        if label == "searched-3":
            models[label]["search"] = search_audit

    bootstrap_indexes = grouped_bootstrap_indexes(
        game_ids, repeats=int(settings["bootstrap_repeats"]), seed=seed
    )
    bootstrap_runs = {label: [] for label in models}
    overall_deltas = []
    forcing_deltas = []
    full_deltas = []
    forcing_mask = categories["forcing-proxy"]
    for indexes in bootstrap_indexes:
        run_metrics = {}
        for label, predicted in predictions.items():
            metrics = calculate_metrics(target[indexes], predicted[indexes])
            bootstrap_runs[label].append(metrics)
            run_metrics[label] = metrics
        overall_deltas.append(
            run_metrics["searched-3"]["evaluation_mae_cp"]
            - run_metrics["locked-3"]["evaluation_mae_cp"]
        )
        full_deltas.append(
            run_metrics["searched-3"]["evaluation_mae_cp"]
            - run_metrics["full-16"]["evaluation_mae_cp"]
        )
        forcing_indexes = indexes[forcing_mask[indexes]]
        forcing_deltas.append(
            calculate_metrics(target[forcing_indexes], predictions["searched-3"][forcing_indexes])[
                "evaluation_mae_cp"
            ]
            - calculate_metrics(target[forcing_indexes], predictions["locked-3"][forcing_indexes])[
                "evaluation_mae_cp"
            ]
        )
    for label in models:
        models[label]["bootstrap_intervals"] = _metric_intervals(bootstrap_runs[label])

    paired = {
        "searched-3 minus locked-3 (forcing)": _interval(forcing_deltas),
        "searched-3 minus locked-3 (overall)": _interval(overall_deltas),
        "searched-3 minus full-16 (overall)": _interval(full_deltas),
    }
    decision = {
        "search_gain_survives": interval_excludes_zero_below(
            paired["searched-3 minus locked-3 (forcing)"]
        )
    }

    experiment_name = settings.get("experiment_name", "depth-robustness")
    experiment_id = _next_experiment_id(Path(results_dir), experiment_name)
    artifact = Path(results_dir) / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    runtime = time.perf_counter() - started
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "git_commit": _git_commit(),
        "development_engine_key": development_key,
        "confirmation_engine_key": confirmation_key,
        "development_engine": development_engine,
        "confirmation_engine": confirmation_engine,
        "development": development_audit,
        "confirmation_games": len(set(game_ids.tolist())),
        "confirmation_positions_before_exclusion": len(all_confirmation_rows),
        "prior_domain_positions_excluded": len(all_confirmation_rows)
        - len(confirmation_rows),
        "confirmation_positions": len(confirmation_rows),
        "category_counts": {name: int(mask.sum()) for name, mask in categories.items()},
        "target_clip_cp": clip,
        "bootstrap_repeats": len(bootstrap_indexes),
        "models": models,
        "paired_mae_deltas": paired,
        "decision": decision,
        "runtime_seconds": runtime,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    write_json(artifact / "config.json", config)
    write_json(artifact / "metrics.json", result)
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
    (artifact / "report.md").write_text(_report(result), encoding="utf-8")
    _save_plot(artifact, models)
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
    confirmation_connection.close()
    return result, artifact
