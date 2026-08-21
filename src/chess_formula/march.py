from __future__ import annotations

import json
import platform
import time
from collections.abc import Callable
from dataclasses import dataclass
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
from .features import PIECE_VALUES, extract_features, feature_matrix
from .model import _git_commit, _next_experiment_id, fit_ridge, resolve_engine_key
from .stability import _interval, position_categories


@dataclass(frozen=True)
class StaticFormula:
    feature_names: list[str]
    coefficients: np.ndarray
    intercept: float

    def evaluate(self, board: chess.Board) -> float:
        features = extract_features(board)
        return float(
            self.intercept
            + sum(
                coefficient * features[name]
                for name, coefficient in zip(
                    self.feature_names, self.coefficients, strict=True
                )
            )
        )


def forcing_moves(board: chess.Board) -> list[chess.Move]:
    legal = list(board.legal_moves)
    if board.is_check():
        candidates = legal
    else:
        candidates = []
        for move in legal:
            captured = board.piece_at(move.to_square)
            if (
                board.gives_check(move)
                or move.promotion is not None
                or (captured is not None and captured.piece_type != chess.PAWN)
            ):
                candidates.append(move)

    def ordering(move: chess.Move) -> tuple[int, int, float, str]:
        captured = board.piece_at(move.to_square)
        captured_value = PIECE_VALUES[captured.piece_type] if captured is not None else 0.0
        return (
            -int(board.gives_check(move)),
            -int(move.promotion is not None),
            -captured_value,
            move.uci(),
        )

    return sorted(candidates, key=ordering)


def selective_minimax(
    board: chess.Board,
    evaluator: Callable[[chess.Board], float],
    *,
    depth_plies: int,
    maximum_expanded_children: int,
    terminal_cp: float,
) -> tuple[float, int]:
    if depth_plies < 1 or maximum_expanded_children < 1:
        raise ValueError("Search depth and expanded-child budget must be positive")
    expanded = 0

    def terminal_score(position: chess.Board) -> float | None:
        outcome = position.outcome(claim_draw=False)
        if outcome is None:
            return None
        if outcome.winner is chess.WHITE:
            return terminal_cp
        if outcome.winner is chess.BLACK:
            return -terminal_cp
        return 0.0

    def search(position: chess.Board, depth: int) -> float:
        nonlocal expanded
        terminal = terminal_score(position)
        if terminal is not None:
            return terminal
        static = evaluator(position)
        if depth == 0 or expanded >= maximum_expanded_children:
            return static
        moves = forcing_moves(position)
        if not moves:
            return static
        stand_pat = not position.is_check()
        best = static if stand_pat else (-np.inf if position.turn else np.inf)
        searched = False
        for move in moves:
            if expanded >= maximum_expanded_children:
                break
            position.push(move)
            expanded += 1
            value = search(position, depth - 1)
            position.pop()
            searched = True
            best = max(best, value) if position.turn is chess.WHITE else min(best, value)
        return float(best if searched or stand_pat else static)

    return search(board.copy(stack=False), depth_plies), expanded


def pool_development_rows(databases: list[str | Path], engine_key: str | None) -> tuple:
    grouped: dict[str, list[tuple[str, float]]] = {}
    resolved_key = None
    total_rows = 0
    for database in databases:
        connection = connect_database(database)
        key = resolve_engine_key(connection, engine_key)
        if resolved_key is None:
            resolved_key = key
        elif key != resolved_key:
            raise ValueError("Development engine configurations do not match")
        for digest, fen, score, _ in _labeled_rows(connection, key):
            grouped.setdefault(digest, []).append((fen, float(score)))
            total_rows += 1
        connection.close()
    rows = []
    differing_duplicates = 0
    maximum_duplicate_range = 0.0
    for digest, values in sorted(grouped.items()):
        fens = {fen for fen, _ in values}
        if len(fens) != 1:
            raise ValueError(f"Position hash collision for {digest}")
        scores = [score for _, score in values]
        score_range = max(scores) - min(scores)
        differing_duplicates += score_range > 0
        maximum_duplicate_range = max(maximum_duplicate_range, score_range)
        rows.append((digest, values[0][0], float(np.mean(scores))))
    return rows, resolved_key, {
        "input_rows": total_rows,
        "unique_positions": len(rows),
        "duplicate_occurrences": total_rows - len(rows),
        "differing_duplicate_targets": differing_duplicates,
        "maximum_duplicate_target_range_cp": maximum_duplicate_range,
        "duplicate_target_aggregation": "arithmetic mean",
    }


def _metric_intervals(runs: list[dict]) -> dict:
    names = (
        "evaluation_mae_cp",
        "evaluation_rmse_cp",
        "evaluation_correlation",
        "sign_accuracy",
        "catastrophic_error_rate_500cp",
    )
    return {name: _interval([float(run[name]) for run in runs]) for name in names}


def _save_plot(artifact: Path, models: dict) -> None:
    labels = list(models)
    x = np.arange(len(labels))
    overall = [models[label]["metrics"]["evaluation_mae_cp"] for label in labels]
    forcing = [
        models[label]["categories"]["forcing-proxy"]["evaluation_mae_cp"]
        for label in labels
    ]
    width = 0.38
    figure, axis = plt.subplots(figsize=(11, 5))
    axis.bar(x - width / 2, overall, width, label="overall")
    axis.bar(x + width / 2, forcing, width, label="forcing proxy")
    axis.set(
        ylabel="MAE (cp)",
        title="Untouched March compact-rule comparison",
        xticks=x,
        xticklabels=labels,
    )
    axis.tick_params(axis="x", rotation=18)
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(artifact / "march_comparison.png", dpi=150)
    plt.close(figure)


def _report(result: dict) -> str:
    rows = []
    for label, model in result["models"].items():
        metrics = model["metrics"]
        forcing = model["categories"]["forcing-proxy"]
        search = model.get("search")
        mean_expanded = search["mean_expanded_children"] if search else 0.0
        rows.append(
            f"| {label} | {model['parameter_count']} | "
            f"{metrics['evaluation_mae_cp']:.2f} | "
            f"{forcing['evaluation_mae_cp']:.2f} | "
            f"{metrics['evaluation_correlation']:.4f} | "
            f"{metrics['sign_accuracy']:.2%} | "
            f"{metrics['catastrophic_error_rate_500cp']:.2%} | "
            f"{mean_expanded:.1f} |"
        )
    delta_rows = []
    for label, summary in result["paired_mae_deltas"].items():
        delta_rows.append(
            f"| {label} | {summary['mean']:+.2f} | "
            f"[{summary['p2_5']:+.2f}, {summary['p97_5']:+.2f}] |"
        )
    decisions = result["decisions"]
    development = result["development"]
    development_counts = (
        f"{development['input_rows']} / {development['unique_positions']}"
    )
    duplicate_range = development["maximum_duplicate_target_range_cp"]
    return f"""# March Compact-Rule Validation: {result['experiment_id']}

## Question

Do the preregistered passed-pawn term or bounded forcing search improve the
compact evaluator on an untouched human-game month?

## Leakage controls

- Protocol Git revision: {result['git_commit']}
- March archive/sample was not accessed before the executable protocol commit.
- Static coefficients use only the deduplicated January/February union.
- Repeated development labels are averaged before fitting.
- Every March hash present in development data is excluded.
- Search uses compact formulas at leaves and never calls Stockfish.

## Data

- Development input / unique positions: {development_counts}
- Differing duplicate targets: {development['differing_duplicate_targets']}
- Maximum duplicate target range: {duplicate_range:.0f} cp
- March games: {result['confirmation_games']}
- March positions before overlap exclusion: {result['confirmation_positions_before_exclusion']}
- Cross-domain overlaps excluded: {result['cross_domain_positions_excluded']}
- March positions evaluated: {result['confirmation_positions']}
- Forcing-proxy positions: {result['category_counts']['forcing-proxy']}
- Bootstrap repeats: {result['bootstrap_repeats']}
- Runtime: {result['runtime_seconds']:.3f} seconds

## Frozen comparison

| Candidate | Params | Overall MAE | Forcing MAE | Correlation | Sign | ≥500 cp | Mean expanded |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Paired game-bootstrap decisions

Negative differences favor the first named candidate.

| Primary/secondary contrast | Mean MAE difference | 95% interval |
|---|---:|---:|
{chr(10).join(delta_rows)}

- Candidate A (`passed_pawns`) advances: **{decisions['passed_pawn_advances']}**
- Candidate B (bounded forcing search) advances: **{decisions['forcing_search_advances']}**

## Guardrail

This experiment predicts a shallow Stockfish evaluation; it does not measure move
agreement or playing strength. Search cost is part of the description/computation
frontier and must be reported alongside any accuracy gain.
"""


def run_march_validation(
    development_databases: list[str | Path],
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
    development_rows, development_key, development_audit = pool_development_rows(
        development_databases, engine_key
    )
    confirmation_connection = connect_database(confirmation_database)
    confirmation_key = resolve_engine_key(confirmation_connection, engine_key)
    if development_key != confirmation_key:
        raise ValueError("Development and confirmation engine configurations do not match")
    all_confirmation_rows = _labeled_rows(confirmation_connection, confirmation_key)
    development_hashes = {row[0] for row in development_rows}
    confirmation_rows = [
        row for row in all_confirmation_rows if row[0] not in development_hashes
    ]
    if not confirmation_rows:
        raise RuntimeError("No March positions remain after development-overlap exclusion")

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
    settings = config["march_validation"]
    alpha = float(config["model"]["ridge_alpha"])
    static_sets = {
        label: feature_names if names == "all" else list(names)
        for label, names in settings["static_candidates"].items()
    }
    static_formulas = {}
    predictions = {}
    for label, names in static_sets.items():
        indexes = [feature_names.index(name) for name in names]
        coefficients, intercept = fit_ridge(
            development_matrix[:, indexes], development_target, alpha
        )
        static_formulas[label] = StaticFormula(names, coefficients, intercept)
        predictions[label] = confirmation_matrix[:, indexes] @ coefficients + intercept

    search_settings = settings["forcing_search"]
    search_audits = {}
    for source_label, searched_label in (
        ("locked-3", "searched-3"),
        ("locked-4-passed", "searched-4-passed"),
    ):
        values = []
        expanded_counts = []
        search_started = time.perf_counter()
        formula = static_formulas[source_label]
        for fen in confirmation_fens:
            value, expanded = selective_minimax(
                chess.Board(fen),
                formula.evaluate,
                depth_plies=int(search_settings["depth_plies"]),
                maximum_expanded_children=int(
                    search_settings["maximum_expanded_children"]
                ),
                terminal_cp=float(search_settings["terminal_win_loss_cp"]),
            )
            values.append(value)
            expanded_counts.append(expanded)
        elapsed = time.perf_counter() - search_started
        predictions[searched_label] = np.asarray(values)
        search_audits[searched_label] = {
            "source_formula": source_label,
            "depth_plies": int(search_settings["depth_plies"]),
            "maximum_expanded_children": int(
                search_settings["maximum_expanded_children"]
            ),
            "mean_expanded_children": float(np.mean(expanded_counts)),
            "p95_expanded_children": float(np.percentile(expanded_counts, 95)),
            "maximum_observed_expanded_children": int(max(expanded_counts)),
            "positions_hitting_budget": int(
                np.sum(
                    np.asarray(expanded_counts)
                    >= int(search_settings["maximum_expanded_children"])
                )
            ),
            "runtime_seconds": elapsed,
            "latency_ms_per_position": elapsed * 1000 / len(confirmation_rows),
        }

    categories = position_categories(confirmation_fens, confirmation_matrix, feature_names)
    models = {}
    for label, predicted in predictions.items():
        source_label = search_audits.get(label, {}).get("source_formula", label)
        names = static_sets[source_label]
        models[label] = {
            "features": names,
            "parameter_count": len(names) + 1,
            "coefficients": static_formulas[source_label].coefficients.tolist(),
            "intercept": static_formulas[source_label].intercept,
            "metrics": calculate_metrics(target, predicted),
            "categories": {
                category: calculate_metrics(target[mask], predicted[mask])
                for category, mask in categories.items()
                if int(mask.sum()) >= 2
            },
        }
        if label in search_audits:
            models[label]["search"] = search_audits[label]

    bootstrap_indexes = grouped_bootstrap_indexes(
        game_ids,
        repeats=int(settings["bootstrap_repeats"]),
        seed=seed,
    )
    bootstrap_runs = {label: [] for label in models}
    passed_deltas = []
    forcing_deltas = []
    forcing_passed_deltas = []
    forcing_mask = categories["forcing-proxy"]
    for indexes in bootstrap_indexes:
        run_metrics = {}
        for label, predicted in predictions.items():
            metrics = calculate_metrics(target[indexes], predicted[indexes])
            bootstrap_runs[label].append(metrics)
            run_metrics[label] = metrics
        passed_deltas.append(
            run_metrics["locked-4-passed"]["evaluation_mae_cp"]
            - run_metrics["locked-3"]["evaluation_mae_cp"]
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
        forcing_passed_deltas.append(
            calculate_metrics(
                target[forcing_indexes], predictions["searched-4-passed"][forcing_indexes]
            )["evaluation_mae_cp"]
            - calculate_metrics(
                target[forcing_indexes], predictions["locked-4-passed"][forcing_indexes]
            )["evaluation_mae_cp"]
        )
    for label in models:
        models[label]["bootstrap_intervals"] = _metric_intervals(bootstrap_runs[label])

    paired = {
        "locked-4-passed minus locked-3 (overall)": _interval(passed_deltas),
        "searched-3 minus locked-3 (forcing)": _interval(forcing_deltas),
        "searched-4-passed minus locked-4-passed (forcing)": _interval(
            forcing_passed_deltas
        ),
    }
    decisions = {
        "passed_pawn_advances": bool(
            paired["locked-4-passed minus locked-3 (overall)"]["mean"] < 0
            and paired["locked-4-passed minus locked-3 (overall)"]["p97_5"] < 0
        ),
        "forcing_search_advances": bool(
            paired["searched-3 minus locked-3 (forcing)"]["mean"] < 0
            and paired["searched-3 minus locked-3 (forcing)"]["p97_5"] < 0
        ),
    }

    experiment_name = settings.get("experiment_name", "march-compact-rules")
    experiment_id = _next_experiment_id(Path(results_dir), experiment_name)
    artifact = Path(results_dir) / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    runtime = time.perf_counter() - started
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "git_commit": _git_commit(),
        "engine_key": confirmation_key,
        "development": development_audit,
        "confirmation_games": len(set(game_ids.tolist())),
        "confirmation_positions_before_exclusion": len(all_confirmation_rows),
        "cross_domain_positions_excluded": len(all_confirmation_rows)
        - len(confirmation_rows),
        "confirmation_positions": len(confirmation_rows),
        "category_counts": {name: int(mask.sum()) for name, mask in categories.items()},
        "target_clip_cp": clip,
        "bootstrap_repeats": len(bootstrap_indexes),
        "models": models,
        "paired_mae_deltas": paired,
        "decisions": decisions,
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
