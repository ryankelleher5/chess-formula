from __future__ import annotations

import hashlib
import json
import platform
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.engine
import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .config import write_json
from .human_corpus import sha256_file
from .model import _git_commit, _next_experiment_id
from .oracle import normalize_score
from .oracle_convergence import (
    _load_frozen_source,
    _passes_gate,
    compare_oracle_tiers,
)
from .ordinary_branch import _digest_lines, _load_oracle_cache, _mover_regret

SCHEMA_VERSION = "branch-separable-oracle-record-v1"


def _settings(config: dict) -> dict:
    if "branch_separable_oracle" not in config:
        raise ValueError("The active configuration has no branch_separable_oracle section")
    return config["branch_separable_oracle"]


def _load_source(settings: dict) -> tuple[dict, dict[str, dict]]:
    path = Path(settings["source_protocol_config"])
    if path.stat().st_size != int(settings["source_protocol_config_bytes"]):
        raise RuntimeError("Experiment 017 protocol byte count changed")
    if sha256_file(path) != settings["source_protocol_config_sha256"]:
        raise RuntimeError("Experiment 017 protocol checksum changed")
    prior_config = json.loads(path.read_text(encoding="utf-8"))
    _, source_audit, contexts = _load_frozen_source(prior_config["oracle_convergence"])
    branch_keys = []
    for context_key, context in sorted(contexts.items()):
        board = chess.Board(context["fen"])
        branch_keys.extend(f"{context_key}:{move.uci()}" for move in board.legal_moves)
    actual = {
        "contexts": len(contexts),
        "root_contexts": sum(key.startswith("root:") for key in contexts),
        "parent_contexts": sum(key.startswith("parent:") for key in contexts),
        "legal_branches": len(branch_keys),
        "branch_key_digest": _digest_lines(sorted(branch_keys)),
    }
    expected = {
        "contexts": int(settings["expected_contexts"]),
        "root_contexts": int(settings["expected_root_contexts"]),
        "parent_contexts": int(settings["expected_parent_contexts"]),
        "legal_branches": int(settings["expected_legal_branches"]),
        "branch_key_digest": settings["branch_key_digest"],
    }
    if actual != expected:
        raise RuntimeError(f"Branch-separable source audit changed: {actual}")
    return {**source_audit, **actual}, contexts


def audit_branch_separable_source(config: dict) -> dict:
    audit, _ = _load_source(_settings(config))
    return audit


def _oracle_identity(engine: chess.engine.SimpleEngine, settings: dict) -> tuple[str, dict]:
    oracle = settings["oracle"]
    engine_name = engine.id.get("name", "unknown")
    engine_author = engine.id.get("author", "unknown")
    if not engine_name.startswith(str(oracle["engine"])):
        raise RuntimeError(
            f"Frozen branch-separable oracle requires {oracle['engine']}, found {engine_name}"
        )
    parameters = {"Threads": int(oracle["threads"]), "Hash": int(oracle["hash_mb"])}
    configurable = {key: value for key, value in parameters.items() if key in engine.options}
    if configurable:
        engine.configure(configurable)
    if "UCI_ShowWDL" in engine.options:
        engine.configure({"UCI_ShowWDL": True})
    identity = {
        "engine": f"{engine_name} ({engine_author})",
        "parameters": parameters,
        "analysis": "one constrained root move per independent call",
        "mate_score_cp": int(oracle["mate_score_cp"]),
        "score_clip_cp": int(oracle["score_clip_cp"]),
        "new_game_per_branch": bool(oracle["new_game_per_branch"]),
        "nodes_per_move": settings["nodes_per_move"],
        "protocol_version": settings["protocol_version"],
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    return key, identity


def _analyse_forced_move(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    move: chess.Move,
    *,
    nodes: int,
    mate_score_cp: int,
    game_key: str,
) -> dict:
    started = time.perf_counter()
    info = engine.analyse(
        board,
        chess.engine.Limit(nodes=nodes),
        root_moves=[move],
        game=game_key,
    )
    if not isinstance(info, dict):
        raise RuntimeError(f"Constrained oracle returned multiple records for {game_key}")
    pv = info.get("pv", [])
    if not pv or pv[0] != move:
        raise RuntimeError(f"Constrained oracle PV does not begin with {move.uci()}")
    score, mate = normalize_score(info["score"], mate_score_cp)
    return {
        "eval_cp": score,
        "mate": mate,
        "depth": info.get("depth"),
        "seldepth": info.get("seldepth"),
        "reported_nodes": info.get("nodes"),
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }


def populate_branch_separable_cache(
    stockfish_path: str | Path,
    contexts: dict[str, dict],
    config: dict,
) -> tuple[dict[str, dict], dict]:
    settings = _settings(config)
    executable = Path(stockfish_path)
    if not executable.exists():
        raise FileNotFoundError(executable)
    cache_path = Path(settings["oracle_cache"])
    metadata_path = Path(settings["oracle_cache_metadata"])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    entries = _load_oracle_cache(cache_path)
    expected_keys = {
        f"per-move-{int(nodes)}:{context_key}:{move.uci()}"
        for nodes in settings["nodes_per_move"]
        for context_key, context in contexts.items()
        for move in chess.Board(context["fen"]).legal_moves
    }
    unexpected = set(entries) - expected_keys
    if unexpected:
        raise RuntimeError(f"Unexpected branch-separable cache keys: {sorted(unexpected)[:3]}")
    engine = chess.engine.SimpleEngine.popen_uci(str(executable))
    started = time.perf_counter()
    new_analyses = 0
    cached_analyses = 0
    try:
        oracle_key, identity = _oracle_identity(engine, settings)
        metadata = {
            "oracle_key": oracle_key,
            "identity": identity,
            "source_protocol_config_sha256": settings["source_protocol_config_sha256"],
            "branch_key_digest": settings["branch_key_digest"],
        }
        if metadata_path.exists():
            if json.loads(metadata_path.read_text(encoding="utf-8")) != metadata:
                raise RuntimeError("Branch-separable cache metadata differs")
        else:
            write_json(metadata_path, metadata)
        if any(row["oracle_key"] != oracle_key for row in entries.values()):
            raise RuntimeError("Branch-separable cache identity differs")
        with cache_path.open("a", encoding="utf-8") as output:
            for nodes_per_move in settings["nodes_per_move"]:
                tier_id = f"per-move-{int(nodes_per_move)}"
                for context_key, context in sorted(contexts.items()):
                    board = chess.Board(context["fen"])
                    legal_moves = sorted(board.legal_moves, key=lambda move: move.uci())
                    for move in legal_moves:
                        cache_key = f"{tier_id}:{context_key}:{move.uci()}"
                        if cache_key in entries:
                            cached_analyses += 1
                            continue
                        analysis = _analyse_forced_move(
                            engine,
                            board,
                            move,
                            nodes=int(nodes_per_move),
                            mate_score_cp=int(settings["oracle"]["mate_score_cp"]),
                            game_key=cache_key,
                        )
                        result = {
                            "schema_version": SCHEMA_VERSION,
                            "cache_key": cache_key,
                            "context_key": context_key,
                            "context_kind": context["kind"],
                            "source_root_hash": context["source_root_hash"],
                            "root_candidate_uci": context.get("root_candidate_uci"),
                            "fen": board.fen(),
                            "side_to_move": "white" if board.turn else "black",
                            "legal_moves": len(legal_moves),
                            "move_uci": move.uci(),
                            "tier_id": tier_id,
                            "nodes_per_move": int(nodes_per_move),
                            "requested_nodes": int(nodes_per_move),
                            "oracle_key": oracle_key,
                            "partition": "development",
                            **analysis,
                        }
                        output.write(json.dumps(result, sort_keys=True) + "\n")
                        output.flush()
                        entries[cache_key] = result
                        new_analyses += 1
    finally:
        engine.quit()
    if set(entries) != expected_keys:
        raise RuntimeError(
            f"Branch-separable cache is incomplete: {len(entries)} != {len(expected_keys)}"
        )
    return entries, {
        "oracle_key": next(iter(entries.values()))["oracle_key"],
        "analyses": len(entries),
        "new_analyses": new_analyses,
        "cached_analyses": cached_analyses,
        "runtime_seconds": time.perf_counter() - started,
    }


def aggregate_branch_records(entries: dict[str, dict]) -> dict[str, dict[str, dict]]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in entries.values():
        grouped[(row["tier_id"], row["context_key"])].append(row)
    tiers: dict[str, dict[str, dict]] = defaultdict(dict)
    for (tier_id, context_key), rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda row: row["move_uci"])
        legal_moves = int(rows[0]["legal_moves"])
        if len(rows) != legal_moves or len({row["move_uci"] for row in rows}) != legal_moves:
            raise RuntimeError(f"Incomplete constrained move set for {tier_id}:{context_key}")
        invariant = {
            (
                row["context_kind"],
                row["fen"],
                row["side_to_move"],
                row["nodes_per_move"],
            )
            for row in rows
        }
        if len(invariant) != 1:
            raise RuntimeError(f"Constrained context metadata changed for {tier_id}:{context_key}")
        first = rows[0]
        tiers[tier_id][context_key] = {
            "tier_id": tier_id,
            "context_key": context_key,
            "context_kind": first["context_kind"],
            "fen": first["fen"],
            "side_to_move": first["side_to_move"],
            "legal_moves": legal_moves,
            "nodes_per_move": int(first["nodes_per_move"]),
            "requested_nodes": int(first["nodes_per_move"]) * legal_moves,
            "elapsed_ms": sum(float(row["elapsed_ms"]) for row in rows),
            "moves": [
                {
                    "move_uci": row["move_uci"],
                    "eval_cp": row["eval_cp"],
                    "mate": row["mate"],
                    "depth": row["depth"],
                    "seldepth": row["seldepth"],
                    "nodes": row["reported_nodes"],
                }
                for row in rows
            ],
        }
    return dict(tiers)


def _load_shared_tiers(settings: dict) -> dict[str, dict[str, dict]]:
    path = Path(settings["prior_shared_cache"])
    metadata_path = Path(settings["prior_shared_cache_metadata"])
    if path.stat().st_size != int(settings["prior_shared_cache_bytes"]):
        raise RuntimeError("Experiment 017 cache byte count changed")
    if sha256_file(path) != settings["prior_shared_cache_sha256"]:
        raise RuntimeError("Experiment 017 cache checksum changed")
    if metadata_path.stat().st_size != int(settings["prior_shared_cache_metadata_bytes"]):
        raise RuntimeError("Experiment 017 cache metadata byte count changed")
    if sha256_file(metadata_path) != settings["prior_shared_cache_metadata_sha256"]:
        raise RuntimeError("Experiment 017 cache metadata checksum changed")
    entries = _load_oracle_cache(path)
    if {row["oracle_key"] for row in entries.values()} != {settings["prior_shared_key"]}:
        raise RuntimeError("Experiment 017 shared oracle identity changed")
    selected = set(settings["external_shared_tiers"])
    tiers: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in entries.values():
        if row["tier_id"] in selected:
            tiers[row["tier_id"]][row["context_key"]] = row
    incomplete = any(
        len(rows) != int(settings["expected_contexts"]) for rows in tiers.values()
    )
    if set(tiers) != selected or incomplete:
        raise RuntimeError("Experiment 017 external comparison tiers are incomplete")
    return dict(tiers)


def _scores_and_regrets(row: dict, clip: int) -> tuple[dict[str, float], dict[str, float]]:
    board = chess.Board(row["fen"])
    scores = {
        move["move_uci"]: float(np.clip(move["eval_cp"], -clip, clip))
        for move in row["moves"]
    }
    ranked = sorted(
        scores,
        key=lambda move: ((-scores[move]) if board.turn else scores[move], move),
    )
    best = scores[ranked[0]]
    regrets = {
        move: _mover_regret(best, value, board.turn) for move, value in scores.items()
    }
    return scores, regrets


def ambiguity_metrics(
    lower: dict[str, dict],
    audit: dict[str, dict],
    *,
    thresholds: list[int],
    score_clip_cp: int,
) -> dict:
    if set(lower) != set(audit):
        raise RuntimeError("Ambiguity tiers contain different context sets")
    result = {}
    for kind in ("root", "parent"):
        counts = {
            threshold: {"stable_important": 0, "stable_unimportant": 0, "ambiguous": 0}
            for threshold in thresholds
        }
        context_union_fractions = {threshold: [] for threshold in thresholds}
        top_disagreements = []
        for context_key in sorted(lower):
            left = lower[context_key]
            right = audit[context_key]
            if left["context_kind"] != kind:
                continue
            _, left_regrets = _scores_and_regrets(left, score_clip_cp)
            _, right_regrets = _scores_and_regrets(right, score_clip_cp)
            left_top = min(left_regrets, key=lambda move: (left_regrets[move], move))
            right_top = min(right_regrets, key=lambda move: (right_regrets[move], move))
            if left_top != right_top:
                top_disagreements.append(
                    max(right_regrets[left_top], left_regrets[right_top])
                )
            for threshold in thresholds:
                union = 0
                for move in left_regrets:
                    left_positive = left_regrets[move] <= threshold
                    right_positive = right_regrets[move] <= threshold
                    if left_positive and right_positive:
                        counts[threshold]["stable_important"] += 1
                    elif not left_positive and not right_positive:
                        counts[threshold]["stable_unimportant"] += 1
                    else:
                        counts[threshold]["ambiguous"] += 1
                    union += int(left_positive or right_positive)
                context_union_fractions[threshold].append(union / len(left_regrets))
        result[kind] = {
            "thresholds": {
                str(threshold): {
                    **values,
                    "ambiguous_rate": values["ambiguous"] / sum(values.values()),
                    "mean_conservative_important_fraction": float(
                        np.mean(context_union_fractions[threshold])
                    ),
                }
                for threshold, values in counts.items()
            },
            "top_reply_disagreements": len(top_disagreements),
            "median_larger_reciprocal_regret_cp": (
                float(np.median(top_disagreements)) if top_disagreements else 0.0
            ),
            "maximum_larger_reciprocal_regret_cp": max(top_disagreements, default=0.0),
            "mutually_within_threshold": {
                str(threshold): sum(value <= threshold for value in top_disagreements)
                for threshold in thresholds
            },
        }
    return result


def measure_branch_separable(
    tiers: dict[str, dict[str, dict]],
    shared_tiers: dict[str, dict[str, dict]],
    config: dict,
) -> dict:
    settings = _settings(config)
    thresholds = [int(value) for value in settings["regret_thresholds_cp"]]
    clip = int(settings["oracle"]["score_clip_cp"])
    level_ids = [f"per-move-{int(value)}" for value in settings["nodes_per_move"]]
    if set(tiers) != set(level_ids):
        raise RuntimeError("Branch-separable tier set changed")
    maximum = level_ids[-1]
    tier_summary = {}
    comparisons = {}
    ambiguity = {}
    eligibility = {}
    for index, tier_id in enumerate(level_ids):
        rows = tiers[tier_id]
        requested = [row["requested_nodes"] for row in rows.values()]
        tier_summary[tier_id] = {
            "nodes_per_move": int(settings["nodes_per_move"][index]),
            "contexts": len(rows),
            "branch_analyses": sum(row["legal_moves"] for row in rows.values()),
            "mean_requested_nodes_per_context": float(np.mean(requested)),
            "median_requested_nodes_per_context": float(np.median(requested)),
            "minimum_requested_nodes_per_context": min(requested),
            "maximum_requested_nodes_per_context": max(requested),
            "total_requested_nodes": sum(requested),
        }
        max_key = f"{tier_id}__vs__{maximum}"
        comparisons[max_key] = compare_oracle_tiers(
            rows, tiers[maximum], thresholds=thresholds, score_clip_cp=clip
        )
        ambiguity[max_key] = ambiguity_metrics(
            rows, tiers[maximum], thresholds=thresholds, score_clip_cp=clip
        )
        max_passed, max_failures = _passes_gate(
            comparisons[max_key], settings["stability_gate"]
        )
        eligibility[f"{tier_id}:audit_maximum"] = {
            "comparison": max_key,
            "passed": max_passed,
            "failures": max_failures,
        }
        if index + 1 < len(level_ids):
            next_id = level_ids[index + 1]
            next_key = f"{tier_id}__vs__{next_id}"
            comparisons[next_key] = compare_oracle_tiers(
                rows, tiers[next_id], thresholds=thresholds, score_clip_cp=clip
            )
            next_passed, next_failures = _passes_gate(
                comparisons[next_key], settings["stability_gate"]
            )
            eligibility[f"{tier_id}:next_level"] = {
                "comparison": next_key,
                "passed": next_passed,
                "failures": next_failures,
            }
    external = {}
    for comparison in settings["external_comparisons"]:
        left_id = comparison["independent_tier"]
        right_id = comparison["shared_tier"]
        key = f"{left_id}__vs__{right_id}"
        metrics = compare_oracle_tiers(
            tiers[left_id],
            shared_tiers[right_id],
            thresholds=thresholds,
            score_clip_cp=clip,
        )
        external[key] = {
            "label": comparison["label"],
            "matched_nominal_nodes_per_move": bool(
                comparison["matched_nominal_nodes_per_move"]
            ),
            "metrics": metrics,
            "ambiguity": ambiguity_metrics(
                tiers[left_id],
                shared_tiers[right_id],
                thresholds=thresholds,
                score_clip_cp=clip,
            ),
        }
    eligible = []
    for tier_id in level_ids[:-1]:
        if (
            eligibility[f"{tier_id}:audit_maximum"]["passed"]
            and eligibility[f"{tier_id}:next_level"]["passed"]
        ):
            eligible.append(tier_id)
    eligible.sort(key=lambda tier: (tier_summary[tier]["nodes_per_move"], tier))
    selected = eligible[0] if eligible else None
    return {
        "tiers": tier_summary,
        "comparisons": comparisons,
        "ambiguity": ambiguity,
        "external_allocation_comparisons": external,
        "eligibility": eligibility,
        "decision": {
            "stability_gate_passed": selected is not None,
            "selected_training_reference": selected,
            "eligible_tiers": eligible,
            "audit_only_tier": maximum,
            "model_training_unblocked": selected is not None,
        },
    }


def _save_plot(artifact: Path, result: dict, settings: dict) -> None:
    levels = [f"per-move-{int(value)}" for value in settings["nodes_per_move"]]
    maximum = levels[-1]
    x = [result["tiers"][tier]["nodes_per_move"] for tier in levels]
    top = [
        result["comparisons"][f"{tier}__vs__{maximum}"]["parent"][
            "top_move_agreement"
        ]
        for tier in levels
    ]
    near = [
        result["comparisons"][f"{tier}__vs__{maximum}"]["parent"][
            "mean_near_set_jaccard"
        ]["25"]
        for tier in levels
    ]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].plot(x, top, marker="o", color="#1f77b4")
    axes[1].plot(x, near, marker="o", color="#2ca02c")
    axes[0].axhline(
        float(settings["stability_gate"]["minimum_top_move_agreement"]),
        color="black",
        linestyle="--",
        linewidth=1,
    )
    axes[1].axhline(
        float(settings["stability_gate"]["minimum_near25_set_jaccard"]),
        color="black",
        linestyle="--",
        linewidth=1,
    )
    axes[0].set_title("Independent opponent top-reply stability")
    axes[1].set_title("Independent within-25-cp set stability")
    for axis in axes:
        axis.set_xscale("log")
        axis.set_ylim(0, 1.02)
        axis.set_xlabel("Nodes independently allocated to each legal move")
        axis.set_ylabel("Agreement with 160,000-node audit tier")
        axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(artifact / "branch_separable_convergence.png", dpi=160)
    plt.close(figure)


def _report(result: dict) -> str:
    decision = result["measurement"]["decision"]
    return f"""# Branch-separable oracle calibration

Experiment 018 gives every legal move an independent constrained-root Stockfish
search, preventing MultiPV from redistributing one shared context budget.

## Decision

- Stability gate passed: **{decision['stability_gate_passed']}**
- Selected training reference: `{decision['selected_training_reference']}`
- Audit-only tier: `{decision['audit_only_tier']}`
- Model training unblocked: **{decision['model_training_unblocked']}**

## Integrity

- Development contexts: {result['source_audit']['contexts']}
- Legal branches per tier: {result['source_audit']['legal_branches']}
- Oracle analyses: {result['oracle']['analyses']}
- New / cached analyses: {result['oracle']['new_analyses']} / {result['oracle']['cached_analyses']}
- Selection outcomes probed: 0
- Confirmation outcomes probed: 0
- Runtime: {result['runtime_seconds']:.2f} seconds
- Git revision: `{result['git_commit']}`

The highest compute tier is audit-only and cannot validate itself. A passing
finite-budget result is not a claim that Stockfish defines perfect chess truth.
"""


def run_branch_separable_oracle(
    stockfish_path: str | Path,
    config: dict,
    *,
    results_dir: str | Path | None = None,
) -> tuple[dict, Path]:
    settings = _settings(config)
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    source_audit, contexts = _load_source(settings)
    entries, oracle_audit = populate_branch_separable_cache(
        stockfish_path, contexts, config
    )
    tiers = aggregate_branch_records(entries)
    shared_tiers = _load_shared_tiers(settings)
    measurement = measure_branch_separable(tiers, shared_tiers, config)
    root = Path(results_dir or settings["results_directory"])
    experiment_id = _next_experiment_id(root, settings["experiment_name"])
    artifact = root / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    records_path = artifact / "branch_separable_records.ndjson"
    with records_path.open("w", encoding="utf-8") as output:
        for cache_key in sorted(entries):
            output.write(json.dumps(entries[cache_key], sort_keys=True) + "\n")
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "protocol_version": settings["protocol_version"],
        "git_commit": _git_commit(),
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "runtime_seconds": time.perf_counter() - started,
        "source_audit": source_audit,
        "oracle": oracle_audit,
        "measurement": measurement,
        "records": len(entries),
        "selection_outcomes_probed": 0,
        "confirmation_outcomes_probed": 0,
        "models_trained": 0,
    }
    write_json(artifact / "config.json", config)
    write_json(artifact / "metrics.json", result)
    write_json(
        artifact / "environment.json",
        {
            "python": platform.python_version(),
            "python_chess": chess.__version__,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "git_commit": result["git_commit"],
        },
    )
    write_json(
        artifact / "oracle_cache_metadata.json",
        json.loads(Path(settings["oracle_cache_metadata"]).read_text(encoding="utf-8")),
    )
    (artifact / "report.md").write_text(_report(result), encoding="utf-8")
    _save_plot(artifact, measurement, settings)
    return result, artifact
