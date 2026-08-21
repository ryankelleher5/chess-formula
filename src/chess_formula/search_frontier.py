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
import numpy as np

from .config import set_deterministic_seed, write_json
from .frozen_policy import frozen_formula
from .march import forcing_moves
from .model import _git_commit, _next_experiment_id
from .oracle import _limit, configure_engine, normalize_score


@dataclass(frozen=True)
class FrontierChoice:
    move: str
    predicted_cp: float
    legal_moves_evaluated: int
    internal_children_expanded: int
    budget_exhausted_roots: int


def frontier_moves(board: chess.Board, selector: str) -> list[chess.Move]:
    forcing = forcing_moves(board)
    if selector == "forcing":
        return forcing
    if selector == "all-captures":
        if board.is_check():
            return forcing
        present = set(forcing)
        captures = sorted(
            (move for move in board.legal_moves if board.is_capture(move) and move not in present),
            key=lambda move: move.uci(),
        )
        return forcing + captures
    if selector == "all":
        present = set(forcing)
        quiet = sorted(
            (move for move in board.legal_moves if move not in present),
            key=lambda move: move.uci(),
        )
        return forcing + quiet
    raise ValueError(f"Unknown frontier selector: {selector}")


def scheduled_minimax(
    board: chess.Board,
    evaluator: Callable[[chess.Board], float],
    *,
    selector_schedule: list[str],
    maximum_expanded_children: int,
    terminal_cp: float,
) -> tuple[float, int, bool]:
    if not selector_schedule or maximum_expanded_children < 1:
        raise ValueError("A selector schedule and positive child budget are required")
    expanded = 0
    exhausted = False

    def terminal_score(position: chess.Board) -> float | None:
        outcome = position.outcome(claim_draw=False)
        if outcome is None:
            return None
        if outcome.winner is chess.WHITE:
            return terminal_cp
        if outcome.winner is chess.BLACK:
            return -terminal_cp
        return 0.0

    def search(position: chess.Board, level: int) -> float:
        nonlocal expanded, exhausted
        terminal = terminal_score(position)
        if terminal is not None:
            return terminal
        static = evaluator(position)
        if level == len(selector_schedule):
            return static
        selector = selector_schedule[level]
        moves = frontier_moves(position, selector)
        if not moves:
            return static
        stand_pat = selector != "all" and not position.is_check()
        best = static if stand_pat else (-np.inf if position.turn else np.inf)
        searched = False
        for move in moves:
            if expanded >= maximum_expanded_children:
                exhausted = True
                break
            position.push(move)
            expanded += 1
            value = search(position, level + 1)
            position.pop()
            searched = True
            best = max(best, value) if position.turn is chess.WHITE else min(best, value)
        return float(best if searched or stand_pat else static)

    return search(board.copy(stack=False), 0), expanded, exhausted


def choose_frontier_move(
    board: chess.Board,
    evaluator: Callable[[chess.Board], float],
    *,
    selector_schedule: list[str],
    maximum_expanded_children_per_root: int,
    terminal_cp: float,
) -> FrontierChoice:
    legal_moves = sorted(board.legal_moves, key=lambda move: move.uci())
    if not legal_moves:
        raise ValueError("Cannot choose a move from a terminal position")
    best_move = legal_moves[0]
    best_value = -np.inf if board.turn else np.inf
    expanded = 0
    exhausted_roots = 0
    for move in legal_moves:
        board.push(move)
        value, move_expanded, exhausted = scheduled_minimax(
            board,
            evaluator,
            selector_schedule=selector_schedule,
            maximum_expanded_children=maximum_expanded_children_per_root,
            terminal_cp=terminal_cp,
        )
        board.pop()
        expanded += move_expanded
        exhausted_roots += exhausted
        improves = value > best_value if board.turn else value < best_value
        if improves:
            best_move = move
            best_value = value
    return FrontierChoice(
        move=best_move.uci(),
        predicted_cp=float(best_value),
        legal_moves_evaluated=len(legal_moves),
        internal_children_expanded=expanded,
        budget_exhausted_roots=exhausted_roots,
    )


def _load_cache(path: Path) -> dict:
    if not path.exists():
        return {"engine_key": None, "entries": {}}
    cache = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cache.get("entries"), dict):
        raise RuntimeError("Search-frontier oracle cache is malformed")
    return cache


def label_frontier_choices(
    records: list[dict],
    choices: dict[str, list[FrontierChoice]],
    stockfish_path: str | Path,
    config: dict,
) -> tuple[dict[str, float], dict]:
    path = Path(stockfish_path)
    if not path.exists():
        raise FileNotFoundError(path)
    settings = config["search_frontier"]
    labeling = config["labeling"]
    cache_path = Path(settings["analysis_cache"])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = _load_cache(cache_path)
    record_by_hash = {record["position_hash"]: record for record in records}
    requested = {
        f"{record['position_hash']}:{choices[label][index].move}"
        for index, record in enumerate(records)
        for label in choices
    }
    scores: dict[str, float] = {}
    reused_best = 0
    reused_played = 0
    pending = []
    for key in sorted(requested):
        digest, move = key.split(":", 1)
        record = record_by_hash[digest]
        if move == record["best_move"]:
            scores[key] = float(record["best_cp"])
            reused_best += 1
        elif move == record["played_move"]:
            scores[key] = float(record["played_cp"])
            reused_played += 1
        elif key in cache["entries"]:
            scores[key] = float(cache["entries"][key]["eval_cp"])
        else:
            pending.append((key, record, move))

    engine = chess.engine.SimpleEngine.popen_uci(str(path))
    started = time.perf_counter()
    try:
        engine_key, engine_version, key_data = configure_engine(engine, path, labeling)
        if cache["engine_key"] not in {None, engine_key}:
            raise RuntimeError("Search-frontier cache engine configuration differs")
        cache.update(
            {
                "engine_key": engine_key,
                "engine_version": engine_version,
                "configuration": key_data,
            }
        )
        limit = _limit(labeling["limit_type"], float(labeling["limit_value"]))
        for index, (key, record, move_uci) in enumerate(pending):
            board = chess.Board(record["fen"])
            move = chess.Move.from_uci(move_uci)
            if move not in board.legal_moves:
                raise ValueError(
                    f"Frontier requested illegal move {move_uci} for {record['game_key']}"
                )
            info = engine.analyse(board, limit, root_moves=[move])
            if isinstance(info, list):
                info = info[0]
            eval_cp, mate = normalize_score(info["score"], int(labeling["mate_score_cp"]))
            cache["entries"][key] = {
                "eval_cp": eval_cp,
                "mate": mate,
                "pv": [pv_move.uci() for pv_move in info.get("pv", [])],
                "depth": info.get("depth"),
            }
            scores[key] = float(eval_cp)
            if (index + 1) % 25 == 0 or index + 1 == len(pending):
                write_json(cache_path, cache)
    finally:
        engine.quit()
    write_json(cache_path, cache)
    return scores, {
        "engine_key": cache["engine_key"],
        "engine_version": cache["engine_version"],
        "requested_unique_position_moves": len(requested),
        "root_best_reused": reused_best,
        "played_move_reused": reused_played,
        "cached_forced_moves": len(requested) - reused_best - reused_played - len(pending),
        "new_forced_moves": len(pending),
        "runtime_seconds": time.perf_counter() - started,
    }


def _regret_metrics(
    records: list[dict], choices: list[FrontierChoice], scores: dict[str, float], clip: float
) -> tuple[dict, np.ndarray]:
    regrets = []
    inversions = 0
    for record, choice in zip(records, choices, strict=True):
        chosen_cp = float(np.clip(scores[f"{record['position_hash']}:{choice.move}"], -clip, clip))
        best_cp = float(np.clip(record["best_cp"], -clip, clip))
        raw = best_cp - chosen_cp if record["candidate_color"] == "white" else chosen_cp - best_cp
        inversions += raw < 0
        regrets.append(max(0.0, raw))
    values = np.asarray(regrets, dtype=float)
    return {
        "mean_regret_cp": float(np.mean(values)),
        "median_regret_cp": float(np.median(values)),
        "p95_regret_cp": float(np.percentile(values, 95)),
        "maximum_regret_cp": float(np.max(values)),
        "top_1_agreement": float(
            np.mean(
                [
                    choice.move == record["best_move"]
                    for record, choice in zip(records, choices, strict=True)
                ]
            )
        ),
        "mistake_rate_100cp": float(np.mean(values >= 100)),
        "mistake_rate_150cp": float(np.mean(values >= 150)),
        "mistake_rate_300cp": float(np.mean(values >= 300)),
        "oracle_noise_inversion_rate": inversions / len(values),
    }, values


def grouped_delta_interval(deltas: np.ndarray, groups: list[str], repeats: int, seed: int) -> dict:
    labels = sorted(set(groups))
    indexes = {label: np.flatnonzero(np.asarray(groups) == label) for label in labels}
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(repeats):
        selected = rng.choice(labels, size=len(labels), replace=True)
        sample = np.concatenate([indexes[label] for label in selected])
        samples.append(float(np.mean(deltas[sample])))
    return {
        "mean": float(np.mean(deltas)),
        "p2_5": float(np.percentile(samples, 2.5)),
        "p97_5": float(np.percentile(samples, 97.5)),
    }


def select_frontier_candidate(models: dict, deltas: dict, decision: dict) -> dict:
    baseline = decision["baseline"]
    threshold = float(decision["minimum_relative_mean_regret_improvement"])
    baseline_regret = float(models[baseline]["metrics"]["mean_regret_cp"])
    eligible = []
    reasons = {}
    for label in models:
        if label == baseline:
            continue
        delta = deltas[label]
        relative = -float(delta["mean"]) / baseline_regret if baseline_regret else 0.0
        interval_passes = (
            not decision["require_group_bootstrap_interval_below_zero"] or float(delta["p97_5"]) < 0
        )
        passes = relative >= threshold and interval_passes
        reasons[label] = {
            "relative_mean_regret_improvement": relative,
            "interval_below_zero": interval_passes,
            "eligible": passes,
        }
        if passes:
            eligible.append(label)
    eligible.sort(
        key=lambda label: (
            models[label]["complexity"]["mean_total_states"],
            models[label]["metrics"]["mean_regret_cp"],
            label,
        )
    )
    selected = eligible[0] if eligible else baseline
    return {
        "selected_policy": selected,
        "baseline_retained": selected == baseline,
        "eligible_extensions": eligible,
        "candidate_audit": reasons,
        "maximum_advancing_candidates": int(decision["maximum_advancing_candidates"]),
    }


def _report(result: dict) -> str:
    rows = []
    for label, model in result["models"].items():
        metrics = model["metrics"]
        complexity = model["complexity"]
        rows.append(
            f"| {label} | {metrics['mean_regret_cp']:.2f} | {metrics['median_regret_cp']:.1f} | "
            f"{metrics['top_1_agreement']:.2%} | {metrics['mistake_rate_150cp']:.2%} | "
            f"{complexity['mean_total_states']:.1f} | "
            f"{complexity['latency_ms_per_position']:.1f} | "
            f"{complexity['budget_exhausted_positions']} |"
        )
    delta_rows = [
        f"| {label} | {summary['mean']:+.2f} | [{summary['p2_5']:+.2f}, {summary['p97_5']:+.2f}] |"
        for label, summary in result["paired_regret_deltas"].items()
    ]
    return f"""# Search-Resource Frontier: {result["experiment_id"]}

## Development-only guardrail

These {result["positions"]} turns come only from games lost to Stockfish-100n.
This result can select a candidate, but cannot confirm playing strength.

## Policies

| Policy | Mean regret | Median | Top-1 | ≥150 cp | Mean states | ms/position | Capped positions |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Paired 31-game bootstrap versus baseline

Negative regret differences favor the extension.

| Extension | Mean difference | 95% interval |
|---|---:|---:|
{chr(10).join(delta_rows)}

## Frozen decision

- Selected policy: **{result["decision"]["selected_policy"]}**
- Baseline retained: **{result["decision"]["baseline_retained"]}**
- Eligible extensions: {", ".join(result["decision"]["eligible_extensions"]) or "none"}
- Baseline replay agreement with recorded moves: {result["baseline_replay_agreement"]:.2%}
- New forced oracle calls: {result["oracle"]["new_forced_moves"]}
- Cached forced oracle calls: {result["oracle"]["cached_forced_moves"]}
- Git revision: {result["git_commit"]}
- Runtime: {result["runtime_seconds"]:.3f} seconds
"""


def run_search_frontier(
    stockfish_path: str | Path, config: dict, *, results_dir: str | Path = "results"
) -> tuple[dict, Path]:
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    seed = int(config["seed"])
    set_deterministic_seed(seed)
    settings = config["search_frontier"]
    records = json.loads(Path(settings["audit_records"]).read_text(encoding="utf-8"))
    if len(records) != int(settings["expected_positions"]):
        raise RuntimeError(
            f"Expected {settings['expected_positions']} audit positions, found {len(records)}"
        )
    if len({record["position_hash"] for record in records}) != len(records):
        raise RuntimeError("Search-frontier positions are not unique")
    formula = frozen_formula("searched-3")
    policies: dict[str, list[FrontierChoice]] = {}
    policy_seconds = {}
    for label, policy in settings["policies"].items():
        policy_started = time.perf_counter()
        policies[label] = [
            choose_frontier_move(
                chess.Board(record["fen"]),
                formula.evaluate,
                selector_schedule=list(policy["selector_schedule"]),
                maximum_expanded_children_per_root=int(
                    policy["maximum_expanded_children_per_root"]
                ),
                terminal_cp=float(settings["terminal_cp"]),
            )
            for record in records
        ]
        policy_seconds[label] = time.perf_counter() - policy_started
    baseline = settings["decision"]["baseline"]
    replay = float(
        np.mean(
            [
                choice.move == record["played_move"]
                for choice, record in zip(policies[baseline], records, strict=True)
            ]
        )
    )
    if replay != 1.0:
        raise RuntimeError(f"Frozen baseline replay agreement is {replay:.2%}, expected 100%")
    scores, oracle_audit = label_frontier_choices(records, policies, stockfish_path, config)
    clip = float(settings["score_clip_cp"])
    models = {}
    regrets = {}
    for label, choices in policies.items():
        metrics, regret = _regret_metrics(records, choices, scores, clip)
        regrets[label] = regret
        roots = np.asarray([choice.legal_moves_evaluated for choice in choices])
        expanded = np.asarray([choice.internal_children_expanded for choice in choices])
        exhausted = np.asarray([choice.budget_exhausted_roots for choice in choices])
        models[label] = {
            "selector_schedule": settings["policies"][label]["selector_schedule"],
            "maximum_expanded_children_per_root": settings["policies"][label][
                "maximum_expanded_children_per_root"
            ],
            "metrics": metrics,
            "complexity": {
                "mean_legal_roots": float(np.mean(roots)),
                "mean_internal_children": float(np.mean(expanded)),
                "mean_total_states": float(np.mean(roots + expanded)),
                "p95_total_states": float(np.percentile(roots + expanded, 95)),
                "maximum_total_states": int(np.max(roots + expanded)),
                "budget_exhausted_positions": int(np.sum(exhausted > 0)),
                "budget_exhausted_roots": int(np.sum(exhausted)),
                "runtime_seconds": policy_seconds[label],
                "latency_ms_per_position": policy_seconds[label] * 1000 / len(records),
            },
        }
    groups = [record["game_key"] for record in records]
    deltas = {
        label: grouped_delta_interval(
            regrets[label] - regrets[baseline],
            groups,
            int(settings["bootstrap_repeats"]),
            seed + index,
        )
        for index, label in enumerate(settings["policies"])
        if label != baseline
    }
    decision = select_frontier_candidate(models, deltas, settings["decision"])
    experiment_id = _next_experiment_id(
        Path(results_dir), settings.get("experiment_name", "search-frontier")
    )
    artifact = Path(results_dir) / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "git_commit": _git_commit(),
        "positions": len(records),
        "games": len(set(groups)),
        "formula_features": formula.feature_names,
        "formula_coefficients": formula.coefficients.tolist(),
        "formula_intercept": formula.intercept,
        "baseline_replay_agreement": replay,
        "models": models,
        "paired_regret_deltas": deltas,
        "decision": decision,
        "oracle": oracle_audit,
        "runtime_seconds": time.perf_counter() - started,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    write_json(artifact / "config.json", config)
    write_json(artifact / "metrics.json", result)
    write_json(
        artifact / "choices.json",
        {label: [asdict(choice) for choice in choices] for label, choices in policies.items()},
    )
    write_json(
        artifact / "environment.json",
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "python_chess": chess.__version__,
            "git_commit": result["git_commit"],
        },
    )
    (artifact / "report.md").write_text(_report(result), encoding="utf-8")
    return result, artifact
