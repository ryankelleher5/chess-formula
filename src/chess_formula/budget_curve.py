from __future__ import annotations

import hashlib
import json
import platform
import time
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.engine
import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .config import set_deterministic_seed, write_json
from .frozen_policy import frozen_formula
from .ingest import position_hash
from .model import _git_commit, _next_experiment_id
from .oracle import _limit, configure_engine, normalize_score
from .search_frontier import FrontierChoice, choose_frontier_move, grouped_delta_interval
from .uci_match import load_opening_suite, play_uci_game, summarize_match


def extract_budget_curve_positions(games: list[dict], settings: dict, seed: int) -> list[dict]:
    if len(games) != int(settings["expected_games"]):
        raise ValueError(f"Expected {settings['expected_games']} completed games")
    selected = []
    per_game = int(settings["positions_per_game"])
    for game in games:
        color = chess.WHITE if game["candidate_color"] == "white" else chess.BLACK
        game_key = f"{game['opponent']}:{game['opening_id']}:{game['candidate_color']}"
        candidates = []
        board = chess.Board()
        for ply, move_uci in enumerate(game["moves_uci"]):
            if ply >= 8 and board.turn == color:
                digest = position_hash(board.fen())
                candidates.append(
                    {
                        "position_hash": digest,
                        "fen": board.fen(),
                        "candidate_color": game["candidate_color"],
                        "source_game_key": game_key,
                        "pair_key": f"{game['opponent']}:{game['opening_id']}",
                        "opening_id": game["opening_id"],
                        "opponent": game["opponent"],
                        "ply": ply,
                    }
                )
            move = chess.Move.from_uci(move_uci)
            if move not in board.legal_moves:
                raise ValueError(f"Illegal recorded move {move_uci} in {game_key}")
            board.push(move)
        if len(candidates) < per_game:
            raise RuntimeError(f"Game {game_key} has fewer than {per_game} candidate turns")
        candidates.sort(
            key=lambda row: hashlib.sha256(
                f"{seed}:{game_key}:{row['position_hash']}".encode()
            ).digest()
        )
        selected.extend(candidates[:per_game])
    unique = {}
    for row in sorted(selected, key=lambda item: (item["source_game_key"], item["ply"])):
        unique.setdefault(row["position_hash"], row)
    records = list(unique.values())
    if len(records) < int(settings["minimum_unique_positions"]):
        raise RuntimeError(f"Only {len(records)} unique development positions remain")
    return records


def _load_cache(path: Path) -> dict:
    if not path.exists():
        return {"engine_key": None, "entries": {}}
    cache = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cache.get("entries"), dict):
        raise RuntimeError("Fixed-budget oracle cache is malformed")
    return cache


def label_budget_curve_choices(
    records: list[dict],
    choices: dict[str, list[FrontierChoice]],
    stockfish_path: str | Path,
    config: dict,
) -> tuple[dict, dict]:
    path = Path(stockfish_path)
    if not path.exists():
        raise FileNotFoundError(path)
    settings = config["budget_curve"]
    labeling = config["labeling"]
    cache_path = Path(settings["analysis_cache"])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = _load_cache(cache_path)
    engine = chess.engine.SimpleEngine.popen_uci(str(path))
    started = time.perf_counter()
    new_root = 0
    new_forced = 0
    try:
        engine_key, engine_version, key_data = configure_engine(engine, path, labeling)
        if cache["engine_key"] not in {None, engine_key}:
            raise RuntimeError("Fixed-budget cache engine configuration differs")
        cache.update(
            {
                "engine_key": engine_key,
                "engine_version": engine_version,
                "configuration": key_data,
            }
        )
        limit = _limit(labeling["limit_type"], float(labeling["limit_value"]))
        writes = 0
        for index, record in enumerate(records):
            digest = record["position_hash"]
            root_key = f"{digest}:ROOT"
            board = chess.Board(record["fen"])
            if root_key not in cache["entries"]:
                info = engine.analyse(board, limit)
                score, mate = normalize_score(info["score"], int(labeling["mate_score_cp"]))
                cache["entries"][root_key] = {
                    "eval_cp": score,
                    "mate": mate,
                    "move": info["pv"][0].uci(),
                    "depth": info.get("depth"),
                }
                new_root += 1
                writes += 1
            best_move = cache["entries"][root_key]["move"]
            for label in choices:
                move_uci = choices[label][index].move
                key = f"{digest}:{move_uci}"
                if move_uci == best_move or key in cache["entries"]:
                    continue
                move = chess.Move.from_uci(move_uci)
                if move not in board.legal_moves:
                    raise ValueError(f"Policy requested illegal move {move_uci} for {digest}")
                info = engine.analyse(board, limit, root_moves=[move])
                score, mate = normalize_score(info["score"], int(labeling["mate_score_cp"]))
                cache["entries"][key] = {
                    "eval_cp": score,
                    "mate": mate,
                    "move": move_uci,
                    "depth": info.get("depth"),
                }
                new_forced += 1
                writes += 1
                if writes % 25 == 0:
                    write_json(cache_path, cache)
            if index + 1 == len(records):
                write_json(cache_path, cache)
    finally:
        engine.quit()
    write_json(cache_path, cache)
    root_total = len(records)
    requested_forced = {
        f"{record['position_hash']}:{choices[label][index].move}"
        for index, record in enumerate(records)
        for label in choices
        if choices[label][index].move != cache["entries"][f"{record['position_hash']}:ROOT"]["move"]
    }
    return cache["entries"], {
        "engine_key": cache["engine_key"],
        "engine_version": cache["engine_version"],
        "root_positions": root_total,
        "new_root_labels": new_root,
        "cached_root_labels": root_total - new_root,
        "requested_unique_forced_moves": len(requested_forced),
        "new_forced_labels": new_forced,
        "cached_forced_labels": len(requested_forced) - new_forced,
        "runtime_seconds": time.perf_counter() - started,
    }


def _policy_metrics(
    records: list[dict],
    choices: list[FrontierChoice],
    labels: dict,
    clip: float,
) -> tuple[dict, np.ndarray]:
    regret = []
    top_1 = []
    inversions = 0
    for record, choice in zip(records, choices, strict=True):
        digest = record["position_hash"]
        root = labels[f"{digest}:ROOT"]
        best_cp = float(np.clip(root["eval_cp"], -clip, clip))
        if choice.move == root["move"]:
            chosen_cp = best_cp
        else:
            chosen_cp = float(np.clip(labels[f"{digest}:{choice.move}"]["eval_cp"], -clip, clip))
        raw = best_cp - chosen_cp if record["candidate_color"] == "white" else chosen_cp - best_cp
        inversions += raw < 0
        regret.append(max(0.0, raw))
        top_1.append(choice.move == root["move"])
    values = np.asarray(regret, dtype=float)
    return {
        "mean_regret_cp": float(np.mean(values)),
        "median_regret_cp": float(np.median(values)),
        "p95_regret_cp": float(np.percentile(values, 95)),
        "maximum_regret_cp": float(np.max(values)),
        "top_1_agreement": float(np.mean(top_1)),
        "mistake_rate_100cp": float(np.mean(values >= 100)),
        "mistake_rate_300cp": float(np.mean(values >= 300)),
        "oracle_noise_inversion_rate": inversions / len(values),
    }, values


def select_budget_candidate(
    models: dict,
    regret_deltas: dict,
    game_matches: dict,
    settings: dict,
) -> dict:
    anchor = settings["anchor"]
    low = settings["low_budget_reference"]
    decision = settings["decision"]
    anchor_regret = float(models[anchor]["metrics"]["mean_regret_cp"])
    low_regret = float(models[low]["metrics"]["mean_regret_cp"])
    total_gain = low_regret - anchor_regret
    if total_gain <= 0:
        raise RuntimeError("Confirmed anchor does not improve over the low-budget reference")
    audits = {}
    eligible = []
    anchor_states = float(models[anchor]["complexity"]["mean_total_states"])
    for label, model in models.items():
        if label == anchor:
            continue
        regret = float(model["metrics"]["mean_regret_cp"])
        retention = (low_regret - regret) / total_gain
        cheaper = float(model["complexity"]["mean_total_states"]) < anchor_states
        delta = regret_deltas[label]
        match = game_matches[label]
        score = float(match["score_rate"])
        score_lower = float(match["score_rate_bootstrap"]["p2_5"])
        protocol = not (
            match["candidate_illegal_moves"]
            or match["candidate_timeouts"]
            or match["candidate_engine_errors"]
            or match["opponent_forfeits"]
        )
        passes = (
            cheaper
            and retention >= float(decision["minimum_regret_gain_retention"])
            and float(delta["mean"]) <= float(decision["maximum_mean_regret_increase_cp"])
            and float(delta["p97_5"])
            <= float(decision["maximum_bootstrap_upper_regret_increase_cp"])
            and score >= float(decision["minimum_head_to_head_score"])
            and score_lower >= float(decision["minimum_head_to_head_lower_bound"])
            and protocol
        )
        audits[label] = {
            "cheaper_than_anchor": cheaper,
            "regret_gain_retention": retention,
            "mean_regret_increase_cp": float(delta["mean"]),
            "bootstrap_upper_regret_increase_cp": float(delta["p97_5"]),
            "head_to_head_score": score,
            "head_to_head_lower_bound": score_lower,
            "protocol_clean": protocol,
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
    selected = eligible[0] if eligible else anchor
    return {
        "selected_policy": selected,
        "anchor_retained": selected == anchor,
        "eligible_cheaper_policies": eligible,
        "policy_audit": audits,
        "maximum_advancing_candidates": int(decision["maximum_advancing_candidates"]),
    }


def _save_plot(artifact: Path, models: dict, game_matches: dict, anchor: str) -> None:
    labels = list(models)
    states = [models[label]["complexity"]["mean_total_states"] for label in labels]
    regret = [models[label]["metrics"]["mean_regret_cp"] for label in labels]
    scores = [0.5 if label == anchor else game_matches[label]["score_rate"] for label in labels]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].plot(states, regret, "o-")
    axes[0].set(xscale="log", xlabel="Mean decision states", ylabel="Mean regret (cp)")
    axes[1].plot(states, scores, "o-")
    axes[1].axhline(0.5, color="gray", linestyle="--", linewidth=1)
    axes[1].set(xscale="log", xlabel="Mean decision states", ylabel="Score vs Forcing-3")
    for axis, y_values in zip(axes, (regret, scores), strict=True):
        for x_value, y_value, label in zip(states, y_values, labels, strict=True):
            axis.annotate(
                label, (x_value, y_value), xytext=(4, 4), textcoords="offset points", fontsize=8
            )
        axis.grid(alpha=0.25)
    figure.suptitle("Development fixed-budget search curve")
    figure.tight_layout()
    figure.savefig(artifact / "budget_curve.png", dpi=150)
    plt.close(figure)


def _report(result: dict) -> str:
    rows = []
    for label, model in result["models"].items():
        metrics = model["metrics"]
        complexity = model["complexity"]
        match = result["game_matches"].get(label)
        score = "anchor" if match is None else f"{match['score_rate']:.1%}"
        rows.append(
            f"| {label} | {complexity['mean_total_states']:.1f} | "
            f"{metrics['mean_regret_cp']:.2f} | {metrics['top_1_agreement']:.2%} | "
            f"{complexity['budget_exhausted_positions']} | {score} |"
        )
    return f"""# Fixed-Budget Search Curve: {result["experiment_id"]}

## Development-only guardrail

All positions and openings come from the completed Forcing-3 confirmation.
This experiment may select a candidate but cannot confirm it.

## Curve

| Policy | Mean states | Mean regret | Top-1 | Capped positions | Score vs anchor |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Frozen decision

- Selected policy: **{result["decision"]["selected_policy"]}**
- Anchor retained: **{result["decision"]["anchor_retained"]}**
- Eligible cheaper policies: {", ".join(result["decision"]["eligible_cheaper_policies"]) or "none"}
- New root labels: {result["oracle"]["new_root_labels"]}
- New forced labels: {result["oracle"]["new_forced_labels"]}
- Runtime: {result["runtime_seconds"]:.2f} seconds
- Git revision: {result["git_commit"]}

Any selected policy requires a new opening suite before a strength claim.
"""


def run_fixed_budget_curve(
    stockfish_path: str | Path,
    config: dict,
    *,
    results_dir: str | Path = "results",
) -> tuple[dict, Path]:
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    seed = int(config["seed"])
    set_deterministic_seed(seed)
    settings = config["budget_curve"]
    games = json.loads(Path(settings["development_games"]).read_text(encoding="utf-8"))
    records = extract_budget_curve_positions(games, settings, seed)
    formula = frozen_formula("forcing-3")
    policies = {}
    policy_seconds = {}
    for label, policy in settings["policies"].items():
        policy_started = time.perf_counter()
        policies[label] = [
            choose_frontier_move(
                chess.Board(record["fen"]),
                formula.evaluate,
                selector_schedule=["forcing"] * int(policy["depth_plies"]),
                maximum_expanded_children_per_root=int(
                    policy["maximum_expanded_children_per_root"]
                ),
                terminal_cp=float(settings["terminal_cp"]),
            )
            for record in records
        ]
        policy_seconds[label] = time.perf_counter() - policy_started
    labels, oracle_audit = label_budget_curve_choices(records, policies, stockfish_path, config)
    models = {}
    regrets = {}
    for label, choices in policies.items():
        metrics, regret = _policy_metrics(
            records, choices, labels, float(settings["score_clip_cp"])
        )
        regrets[label] = regret
        roots = np.asarray([choice.legal_moves_evaluated for choice in choices])
        expanded = np.asarray([choice.internal_children_expanded for choice in choices])
        exhausted = np.asarray([choice.budget_exhausted_roots for choice in choices])
        complexity = {
            "mean_total_states": float(np.mean(roots + expanded)),
            "median_total_states": float(np.median(roots + expanded)),
            "p95_total_states": float(np.percentile(roots + expanded, 95)),
            "maximum_total_states": int(np.max(roots + expanded)),
            "budget_exhausted_positions": int(np.sum(exhausted > 0)),
            "budget_exhausted_roots": int(np.sum(exhausted)),
            "runtime_seconds": policy_seconds[label],
            "latency_ms_per_position": policy_seconds[label] * 1000 / len(records),
        }
        lower, upper = settings["calibration_state_ranges"][label]
        if not float(lower) <= complexity["mean_total_states"] <= float(upper):
            raise RuntimeError(f"Policy {label} falls outside its frozen state range")
        models[label] = {
            "depth_plies": settings["policies"][label]["depth_plies"],
            "maximum_expanded_children_per_root": settings["policies"][label][
                "maximum_expanded_children_per_root"
            ],
            "metrics": metrics,
            "complexity": complexity,
        }
    anchor = settings["anchor"]
    groups = [record["pair_key"] for record in records]
    regret_deltas = {
        label: grouped_delta_interval(
            regrets[label] - regrets[anchor],
            groups,
            int(settings["bootstrap_repeats"]),
            seed + index,
        )
        for index, label in enumerate(settings["policies"])
        if label != anchor
    }
    openings = load_opening_suite(settings["opening_suite"])
    if len(openings) != int(settings["expected_openings"]):
        raise RuntimeError("Fixed-budget opening count differs from the frozen protocol")
    game_matches = {}
    all_games = []
    pgns = []
    opponent = {"name": "forcing-3-anchor", "type": "policy", "policy": anchor}
    for policy_index, label in enumerate(settings["policies"]):
        if label == anchor:
            continue
        policy_settings = {**settings, "candidate": label}
        match_games = []
        for opening in openings:
            for candidate_color in (chess.WHITE, chess.BLACK):
                record, pgn = play_uci_game(
                    opening,
                    opponent,
                    candidate_color,
                    stockfish_path,
                    policy_settings,
                )
                match_games.append(record)
                all_games.append({**record, "curve_policy": label})
                pgns.append(pgn)
        game_matches[label] = summarize_match(
            match_games,
            repeats=int(settings["game_bootstrap_repeats"]),
            seed=seed + 100 + policy_index,
        )
    decision = select_budget_candidate(models, regret_deltas, game_matches, settings)
    experiment_id = _next_experiment_id(Path(results_dir), settings["experiment_name"])
    artifact = Path(results_dir) / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "git_commit": _git_commit(),
        "development_games": len(games),
        "development_positions": len(records),
        "position_pair_groups": len(set(groups)),
        "formula_features": formula.feature_names,
        "formula_coefficients": formula.coefficients.tolist(),
        "formula_intercept": formula.intercept,
        "models": models,
        "regret_deltas_vs_anchor": regret_deltas,
        "game_matches": game_matches,
        "decision": decision,
        "oracle": oracle_audit,
        "game_faults": dict(
            Counter(game["failure_kind"] for game in all_games if game["failure_kind"] is not None)
        ),
        "runtime_seconds": time.perf_counter() - started,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    write_json(artifact / "config.json", config)
    write_json(artifact / "metrics.json", result)
    write_json(artifact / "positions.json", records)
    write_json(
        artifact / "choices.json",
        {label: [asdict(choice) for choice in choices] for label, choices in policies.items()},
    )
    write_json(artifact / "games.json", all_games)
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
    (artifact / "games.pgn").write_text("\n\n".join(pgns) + "\n", encoding="utf-8")
    (artifact / "report.md").write_text(_report(result), encoding="utf-8")
    _save_plot(artifact, models, game_matches, anchor)
    return result, artifact
