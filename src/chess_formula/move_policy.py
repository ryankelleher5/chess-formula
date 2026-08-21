from __future__ import annotations

import json
import platform
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.engine
import duckdb
import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .config import set_deterministic_seed, write_json
from .confirmation import grouped_bootstrap_indexes
from .database import connect_database
from .features import feature_matrix
from .march import StaticFormula, pool_development_rows, selective_minimax
from .model import _git_commit, _next_experiment_id, fit_ridge, resolve_engine_key
from .oracle import _limit, configure_engine, normalize_score
from .robustness import _engine_metadata, interval_excludes_zero_below, prior_position_hashes
from .stability import _interval, position_categories


@dataclass(frozen=True)
class PolicyChoice:
    move: str
    predicted_cp: float
    legal_moves_evaluated: int
    forcing_children_expanded: int


def _terminal_score(board: chess.Board, terminal_cp: float) -> float | None:
    outcome = board.outcome(claim_draw=False)
    if outcome is None:
        return None
    if outcome.winner is chess.WHITE:
        return terminal_cp
    if outcome.winner is chess.BLACK:
        return -terminal_cp
    return 0.0


def choose_legal_move(
    board: chess.Board,
    evaluator: Callable[[chess.Board], float],
    *,
    terminal_cp: float,
    search_depth_plies: int | None = None,
    maximum_expanded_children: int | None = None,
) -> PolicyChoice:
    """Choose a legal root move by deterministic White-max/Black-min evaluation."""
    legal_moves = sorted(board.legal_moves, key=lambda move: move.uci())
    if not legal_moves:
        raise ValueError("Cannot choose a move from a terminal position")
    searched = search_depth_plies is not None
    if searched and maximum_expanded_children is None:
        raise ValueError("Searched policies require an expanded-child budget")
    if not searched and maximum_expanded_children is not None:
        raise ValueError("Static policies cannot specify an expanded-child budget")

    best_move = legal_moves[0]
    best_value = -np.inf if board.turn is chess.WHITE else np.inf
    expanded = 0
    for move in legal_moves:
        board.push(move)
        terminal = _terminal_score(board, terminal_cp)
        if terminal is not None:
            value = terminal
            move_expanded = 0
        elif searched:
            value, move_expanded = selective_minimax(
                board,
                evaluator,
                depth_plies=int(search_depth_plies),
                maximum_expanded_children=int(maximum_expanded_children),
                terminal_cp=terminal_cp,
            )
        else:
            value = evaluator(board)
            move_expanded = 0
        board.pop()
        expanded += move_expanded
        improves = value > best_value if board.turn is chess.WHITE else value < best_value
        if improves:
            best_move = move
            best_value = value
    return PolicyChoice(
        move=best_move.uci(),
        predicted_cp=float(best_value),
        legal_moves_evaluated=len(legal_moves),
        forcing_children_expanded=expanded,
    )


def move_quality_metrics(
    *,
    turns: np.ndarray,
    chosen_moves: list[str],
    chosen_scores: np.ndarray,
    best_moves: list[str],
    best_scores: np.ndarray,
    top_moves: list[list[str]],
    top_k: int,
) -> tuple[dict[str, float], np.ndarray]:
    if not (
        len(turns)
        == len(chosen_moves)
        == len(chosen_scores)
        == len(best_moves)
        == len(best_scores)
        == len(top_moves)
    ):
        raise ValueError("Move-quality inputs must have equal lengths")
    if len(turns) == 0:
        raise ValueError("Move-quality metrics require at least one position")
    white_to_move = turns == chess.WHITE
    raw_regret = np.where(
        white_to_move,
        best_scores - chosen_scores,
        chosen_scores - best_scores,
    )
    regret = np.maximum(raw_regret, 0.0)
    top_1 = np.asarray(
        [chosen == best for chosen, best in zip(chosen_moves, best_moves, strict=True)]
    )
    top_k_hits = np.asarray(
        [
            chosen in candidates[:top_k]
            for chosen, candidates in zip(chosen_moves, top_moves, strict=True)
        ]
    )
    metrics = {
        "mean_regret_cp": float(np.mean(regret)),
        "median_regret_cp": float(np.median(regret)),
        "p95_regret_cp": float(np.percentile(regret, 95)),
        "maximum_regret_cp": float(np.max(regret)),
        "top_1_agreement": float(np.mean(top_1)),
        f"top_{top_k}_agreement": float(np.mean(top_k_hits)),
        "within_10cp_rate": float(np.mean(regret <= 10)),
        "mistake_rate_50cp": float(np.mean(regret >= 50)),
        "mistake_rate_100cp": float(np.mean(regret >= 100)),
        "mistake_rate_300cp": float(np.mean(regret >= 300)),
        "oracle_noise_inversion_rate": float(np.mean(raw_regret < 0)),
    }
    return metrics, regret


def _metric_intervals(runs: list[dict[str, float]], top_k: int) -> dict[str, dict]:
    names = (
        "mean_regret_cp",
        "top_1_agreement",
        f"top_{top_k}_agreement",
        "within_10cp_rate",
        "mistake_rate_50cp",
        "mistake_rate_100cp",
        "mistake_rate_300cp",
    )
    return {name: _interval([run[name] for run in runs]) for name in names}


def label_forced_policy_moves(
    stockfish_path: str | Path,
    database: str | Path,
    config: dict,
    engine_key: str,
    requests: dict[str, set[str]],
) -> dict:
    path = Path(stockfish_path)
    if not path.exists():
        raise FileNotFoundError(path)
    labeling = config["labeling"]
    connection = connect_database(database)
    best_rows = connection.execute(
        "SELECT position_hash, best_move FROM engine_analysis WHERE engine_key = ?",
        [engine_key],
    ).fetchall()
    best_moves = dict(best_rows)
    pending = []
    reused_best = 0
    cached = 0
    for digest in sorted(requests):
        if digest not in best_moves:
            connection.close()
            raise RuntimeError(f"Missing root oracle analysis for {digest}")
        for move in sorted(requests[digest]):
            if move == best_moves[digest]:
                reused_best += 1
                continue
            exists = connection.execute(
                "SELECT 1 FROM move_analysis WHERE position_hash = ? "
                "AND engine_key = ? AND move = ?",
                [digest, engine_key, move],
            ).fetchone()
            if exists:
                cached += 1
            else:
                pending.append((digest, move))

    engine = chess.engine.SimpleEngine.popen_uci(str(path))
    started = time.perf_counter()
    try:
        resolved_key, engine_version, _ = configure_engine(engine, path, labeling)
        if resolved_key != engine_key:
            raise ValueError("Forced-move engine configuration differs from root oracle")
        for digest, move_uci in pending:
            fen_row = connection.execute(
                "SELECT fen FROM positions WHERE position_hash = ?", [digest]
            ).fetchone()
            if fen_row is None:
                raise RuntimeError(f"Missing position for {digest}")
            board = chess.Board(fen_row[0])
            move = chess.Move.from_uci(move_uci)
            if move not in board.legal_moves:
                raise ValueError(f"Policy requested illegal move {move_uci} for {digest}")
            analysis_started = time.perf_counter()
            info = engine.analyse(
                board,
                _limit(labeling["limit_type"], float(labeling["limit_value"])),
                root_moves=[move],
            )
            elapsed_ms = (time.perf_counter() - analysis_started) * 1000
            if isinstance(info, list):
                info = info[0]
            eval_cp, mate = normalize_score(info["score"], int(labeling["mate_score_cp"]))
            connection.execute(
                "INSERT INTO move_analysis VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)",
                [
                    digest,
                    engine_key,
                    move_uci,
                    eval_cp,
                    mate,
                    info.get("depth"),
                    info.get("seldepth"),
                    info.get("nodes"),
                    elapsed_ms,
                ],
            )
    finally:
        engine.quit()
        connection.close()
    return {
        "engine_key": engine_key,
        "engine_version": engine_version,
        "requested_unique_moves": sum(len(moves) for moves in requests.values()),
        "root_best_moves_reused": reused_best,
        "cached_forced_moves": cached,
        "new_forced_moves": len(pending),
        "runtime_seconds": time.perf_counter() - started,
    }


def _position_rows(connection) -> list[tuple[str, str, str]]:
    return connection.execute(
        "SELECT p.position_hash, p.fen, min(o.game_id) AS owner_game "
        "FROM positions p JOIN position_occurrences o USING(position_hash) "
        "GROUP BY p.position_hash, p.fen ORDER BY p.position_hash"
    ).fetchall()


def _root_oracle_rows(connection, engine_key: str) -> dict[str, tuple]:
    rows = connection.execute(
        "SELECT position_hash, eval_cp, best_move, top_moves_json "
        "FROM engine_analysis WHERE engine_key = ?",
        [engine_key],
    ).fetchall()
    return {row[0]: row[1:] for row in rows}


def _forced_scores(
    connection, engine_key: str, digests: list[str], choices: list[PolicyChoice], roots: dict
) -> np.ndarray:
    scores = []
    for digest, choice in zip(digests, choices, strict=True):
        root_eval, best_move, _ = roots[digest]
        if choice.move == best_move:
            scores.append(float(root_eval))
            continue
        row = connection.execute(
            "SELECT eval_cp FROM move_analysis WHERE position_hash = ? "
            "AND engine_key = ? AND move = ?",
            [digest, engine_key, choice.move],
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Missing forced oracle score for {digest} {choice.move}")
        scores.append(float(row[0]))
    return np.asarray(scores)


def _save_plot(artifact: Path, models: dict, top_k: int) -> None:
    labels = list(models)
    regret = [models[label]["metrics"]["mean_regret_cp"] for label in labels]
    top_1 = [models[label]["metrics"]["top_1_agreement"] for label in labels]
    top_n = [models[label]["metrics"][f"top_{top_k}_agreement"] for label in labels]
    x = np.arange(len(labels))
    figure, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    axes[0].bar(x, regret, color="#dc2626")
    axes[0].set(ylabel="Mean regret (cp)", xticks=x, xticklabels=labels)
    width = 0.36
    axes[1].bar(x - width / 2, top_1, width, label="top-1")
    axes[1].bar(x + width / 2, top_n, width, label=f"top-{top_k}")
    axes[1].set(ylabel="Agreement", xticks=x, xticklabels=labels, ylim=(0, 1))
    axes[1].legend()
    for axis in axes:
        axis.tick_params(axis="x", rotation=15)
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle("Untouched May legal move-policy comparison")
    figure.tight_layout()
    figure.savefig(artifact / "move_policy.png", dpi=150)
    plt.close(figure)


def _report(result: dict) -> str:
    top_k = result["top_k"]
    rows = []
    for label, model in result["models"].items():
        metrics = model["metrics"]
        complexity = model["complexity"]
        rows.append(
            f"| {label} | {metrics['mean_regret_cp']:.2f} | "
            f"{metrics['median_regret_cp']:.2f} | {metrics['p95_regret_cp']:.2f} | "
            f"{metrics['top_1_agreement']:.2%} | "
            f"{metrics[f'top_{top_k}_agreement']:.2%} | "
            f"{metrics['mistake_rate_100cp']:.2%} | "
            f"{metrics['mistake_rate_300cp']:.2%} | "
            f"{complexity['mean_forcing_children_expanded']:.1f} |"
        )
    delta_rows = [
        f"| {label} | {summary['mean']:+.2f} | "
        f"[{summary['p2_5']:+.2f}, {summary['p97_5']:+.2f}] |"
        for label, summary in result["paired_regret_deltas"].items()
    ]
    engine = result["confirmation_engine"]
    oracle_summary = (
        f"Oracle: Stockfish depth {engine['limit_value']}, "
        f"MultiPV {engine['multipv']}."
    )
    regret_summary = (
        "Regret uses root-move-constrained analysis and clips both oracle scores "
        f"to ±{result['target_clip_cp']} cp."
    )
    forced = result["forced_labeling"]
    forced_summary = (
        f"New / cached forced oracle calls: {forced['new_forced_moves']} / "
        f"{forced['cached_forced_moves']}"
    )
    table_header = (
        f"| Policy | Mean regret | Median | p95 | Top-1 | Top-{top_k} | "
        "≥100 cp | ≥300 cp | Mean forcing expansions |"
    )
    return f"""# May Legal Move-Policy Validation: {result['experiment_id']}

## Question

Does wrapping the frozen compact evaluator in deterministic legal root-move
enumeration produce lower Stockfish regret than static compact move selection?

## Frozen controls

- Protocol Git revision: {result['git_commit']}
- Coefficients use only January/February depth-8 development positions.
- Every May hash observed in January through April is excluded.
- Every policy enumerates all legal root moves with UCI-lexical tie-breaking.
- Searched Locked-3 applies the unchanged two-ply/128-child forcing search after each root move.
- {oracle_summary}
- {regret_summary}

## Data

- Development unique positions: {result['development']['unique_positions']}
- May games: {result['confirmation_games']}
- May positions before exclusion: {result['confirmation_positions_before_exclusion']}
- Prior-domain overlaps excluded: {result['prior_domain_positions_excluded']}
- May positions evaluated: {result['confirmation_positions']}
- Bootstrap repeats: {result['bootstrap_repeats']}
- {forced_summary}
- Runtime excluding initial root labeling: {result['runtime_seconds']:.3f} seconds

## Move quality

{table_header}
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Paired game-bootstrap contrasts

Negative values favor the first named policy.

| Contrast | Mean regret difference | 95% interval |
|---|---:|---:|
{chr(10).join(delta_rows)}

- Legal coverage: **{result['legal_coverage']:.2%}**
- Searched policy advances: **{result['decision']['searched_policy_advances']}**

## Guardrail

Move agreement and centipawn regret are stronger tests than value prediction,
but they are not playing strength. Root enumeration and all selective expansions
count toward computation and description complexity.
"""


def run_move_policy_validation(
    development_databases: list[str | Path],
    prior_databases: list[str | Path],
    confirmation_database: str | Path,
    stockfish_path: str | Path,
    config: dict,
    *,
    results_dir: str | Path = "results",
) -> tuple[dict, Path]:
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    seed = int(config["seed"])
    set_deterministic_seed(seed)
    settings = config["move_policy"]
    development_key = settings["development_engine_key"]
    development_rows, resolved_key, development_audit = pool_development_rows(
        development_databases, development_key
    )
    if resolved_key != development_key:
        raise ValueError("Resolved development engine key differs from frozen key")
    development_connection = connect_database(development_databases[0])
    development_engine = _engine_metadata(development_connection, development_key)
    development_connection.close()

    confirmation_connection = connect_database(confirmation_database)
    all_positions = _position_rows(confirmation_connection)
    prior_hashes = prior_position_hashes(prior_databases)
    confirmation_rows = [row for row in all_positions if row[0] not in prior_hashes]
    if not confirmation_rows:
        confirmation_connection.close()
        raise RuntimeError("No May positions remain after prior-domain exclusion")

    development_matrix, feature_names = feature_matrix([row[1] for row in development_rows])
    clip = int(config["model"]["target_clip_cp"])
    development_target = np.clip(
        np.asarray([row[2] for row in development_rows], dtype=float), -clip, clip
    )
    alpha = float(config["model"]["ridge_alpha"])
    feature_sets = {
        label: feature_names if names == "all" else list(names)
        for label, names in settings["static_candidates"].items()
    }
    if set(feature_sets) != {"locked-3", "full-16"} or feature_sets["locked-3"] != [
        "material",
        "space",
        "tempo",
    ]:
        confirmation_connection.close()
        raise ValueError("Static candidates do not match may-move-policy-v1")
    if int(settings["regret"]["score_clip_cp"]) != clip:
        confirmation_connection.close()
        raise ValueError("Regret clip differs from the frozen model target clip")
    formulas = {}
    for label, names in feature_sets.items():
        indexes = [feature_names.index(name) for name in names]
        coefficients, intercept = fit_ridge(
            development_matrix[:, indexes], development_target, alpha
        )
        formulas[label] = StaticFormula(names, coefficients, intercept)

    search = settings["forcing_search"]
    if search.get("budget_scope") != "per legal root candidate":
        confirmation_connection.close()
        raise ValueError("Forcing-search budget scope does not match the frozen protocol")
    policies = {}
    policy_seconds = {}
    for label, formula_label, searched in (
        ("locked-3", "locked-3", False),
        ("full-16", "full-16", False),
        ("searched-3", "locked-3", True),
    ):
        policy_started = time.perf_counter()
        policies[label] = [
            choose_legal_move(
                chess.Board(fen),
                formulas[formula_label].evaluate,
                terminal_cp=float(search["terminal_win_loss_cp"]),
                search_depth_plies=int(search["depth_plies"]) if searched else None,
                maximum_expanded_children=(
                    int(search["maximum_expanded_children"]) if searched else None
                ),
            )
            for _, fen, _ in confirmation_rows
        ]
        policy_seconds[label] = time.perf_counter() - policy_started

    confirmation_key = resolve_engine_key(confirmation_connection, None)
    confirmation_engine = _engine_metadata(confirmation_connection, confirmation_key)
    expected_depth = int(settings["confirmation_depth"])
    top_k = int(settings["top_k"])
    if confirmation_engine["engine_version"] != development_engine["engine_version"]:
        confirmation_connection.close()
        raise ValueError("Development and confirmation engine versions differ")
    if (
        confirmation_engine["limit_type"] != "depth"
        or int(confirmation_engine["limit_value"]) != expected_depth
        or int(confirmation_engine["multipv"]) != top_k
        or confirmation_engine["parameters"]
        != {
            "Hash": int(config["labeling"]["hash_mb"]),
            "Threads": int(config["labeling"]["threads"]),
        }
    ):
        confirmation_connection.close()
        raise ValueError("Confirmation engine does not match frozen depth/MultiPV")
    roots = _root_oracle_rows(confirmation_connection, confirmation_key)
    digests = [row[0] for row in confirmation_rows]
    missing = [digest for digest in digests if digest not in roots]
    if missing:
        confirmation_connection.close()
        raise RuntimeError(f"Missing root oracle labels for {len(missing)} May positions")
    confirmation_connection.close()

    requests = {
        digest: {policies[label][index].move for label in policies}
        for index, digest in enumerate(digests)
    }
    forced_audit = label_forced_policy_moves(
        stockfish_path, confirmation_database, config, confirmation_key, requests
    )
    confirmation_connection = connect_database(confirmation_database)
    roots = _root_oracle_rows(confirmation_connection, confirmation_key)
    turns = np.asarray([chess.Board(row[1]).turn for row in confirmation_rows])
    game_ids = np.asarray([row[2] for row in confirmation_rows])
    best_moves = [roots[digest][1] for digest in digests]
    best_scores = np.clip(
        np.asarray([roots[digest][0] for digest in digests], dtype=float), -clip, clip
    )
    top_moves = [
        [item["move"] for item in json.loads(roots[digest][2]) if item["move"]]
        for digest in digests
    ]
    categories_matrix, category_names = feature_matrix([row[1] for row in confirmation_rows])
    categories = position_categories(
        [row[1] for row in confirmation_rows], categories_matrix, category_names
    )

    models = {}
    regrets = {}
    oracle_choice_scores = {}
    position_records = []
    for label, choices in policies.items():
        chosen_scores = np.clip(
            _forced_scores(confirmation_connection, confirmation_key, digests, choices),
            -clip,
            clip,
        )
        oracle_choice_scores[label] = chosen_scores
        metrics, model_regret = move_quality_metrics(
            turns=turns,
            chosen_moves=[choice.move for choice in choices],
            chosen_scores=chosen_scores,
            best_moves=best_moves,
            best_scores=best_scores,
            top_moves=top_moves,
            top_k=top_k,
        )
        regrets[label] = model_regret
        category_metrics = {}
        for category, mask in categories.items():
            if int(mask.sum()) >= 2:
                category_metrics[category] = {
                    "positions": int(mask.sum()),
                    "mean_regret_cp": float(np.mean(model_regret[mask])),
                    "top_1_agreement": float(
                        np.mean(
                            [
                                choices[index].move == best_moves[index]
                                for index in np.flatnonzero(mask)
                            ]
                        )
                    ),
                }
        legal_counts = np.asarray([choice.legal_moves_evaluated for choice in choices])
        expanded = np.asarray([choice.forcing_children_expanded for choice in choices])
        models[label] = {
            "features": feature_sets["locked-3" if label == "searched-3" else label],
            "parameter_count": len(
                feature_sets["locked-3" if label == "searched-3" else label]
            )
            + 1,
            "coefficients": formulas[
                "locked-3" if label == "searched-3" else label
            ].coefficients.tolist(),
            "intercept": formulas[
                "locked-3" if label == "searched-3" else label
            ].intercept,
            "metrics": metrics,
            "categories": category_metrics,
            "complexity": {
                "mean_legal_root_moves": float(np.mean(legal_counts)),
                "mean_forcing_children_expanded": float(np.mean(expanded)),
                "p95_forcing_children_expanded": float(np.percentile(expanded, 95)),
                "maximum_forcing_children_expanded": int(np.max(expanded)),
                "runtime_seconds": policy_seconds[label],
                "latency_ms_per_position": policy_seconds[label] * 1000 / len(choices),
            },
        }
        for index, choice in enumerate(choices):
            position_records.append(
                {
                    "position_hash": digests[index],
                    "game_id": str(game_ids[index]),
                    "policy": label,
                    **asdict(choice),
                    "stockfish_best_move": best_moves[index],
                    "stockfish_move_cp": float(chosen_scores[index]),
                    "regret_cp": float(model_regret[index]),
                }
            )

    bootstrap_indexes = grouped_bootstrap_indexes(
        game_ids, repeats=int(settings["bootstrap_repeats"]), seed=seed
    )
    bootstrap_runs = {label: [] for label in policies}
    locked_deltas = []
    full_deltas = []
    for indexes in bootstrap_indexes:
        for label in policies:
            selected_choices = [policies[label][index].move for index in indexes]
            selected_best = [best_moves[index] for index in indexes]
            selected_top = [top_moves[index] for index in indexes]
            selected_metrics, _ = move_quality_metrics(
                turns=turns[indexes],
                chosen_moves=selected_choices,
                chosen_scores=oracle_choice_scores[label][indexes],
                best_moves=selected_best,
                best_scores=best_scores[indexes],
                top_moves=selected_top,
                top_k=top_k,
            )
            bootstrap_runs[label].append(selected_metrics)
        locked_deltas.append(
            float(np.mean(regrets["searched-3"][indexes]))
            - float(np.mean(regrets["locked-3"][indexes]))
        )
        full_deltas.append(
            float(np.mean(regrets["searched-3"][indexes]))
            - float(np.mean(regrets["full-16"][indexes]))
        )
    for label in models:
        models[label]["bootstrap_intervals"] = _metric_intervals(
            bootstrap_runs[label], top_k
        )

    paired = {
        "searched-3 minus locked-3": _interval(locked_deltas),
        "searched-3 minus full-16": _interval(full_deltas),
    }
    legal_coverage = float(
        np.mean(
            [
                chess.Move.from_uci(choice.move) in chess.Board(fen).legal_moves
                for choices in policies.values()
                for choice, (_, fen, _) in zip(choices, confirmation_rows, strict=True)
            ]
        )
    )
    decision = {
        "searched_policy_advances": bool(
            legal_coverage == 1.0
            and interval_excludes_zero_below(paired["searched-3 minus locked-3"])
        )
    }

    experiment_name = settings.get("experiment_name", "may-move-policy")
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
        "confirmation_positions_before_exclusion": len(all_positions),
        "prior_domain_positions_excluded": len(all_positions) - len(confirmation_rows),
        "confirmation_positions": len(confirmation_rows),
        "category_counts": {name: int(mask.sum()) for name, mask in categories.items()},
        "target_clip_cp": clip,
        "top_k": top_k,
        "bootstrap_repeats": len(bootstrap_indexes),
        "models": models,
        "paired_regret_deltas": paired,
        "legal_coverage": legal_coverage,
        "forced_labeling": forced_audit,
        "decision": decision,
        "runtime_seconds": runtime,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    write_json(artifact / "config.json", config)
    write_json(artifact / "metrics.json", result)
    write_json(artifact / "choices.json", position_records)
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
    _save_plot(artifact, models, top_k)
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
