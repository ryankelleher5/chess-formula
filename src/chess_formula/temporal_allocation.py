from __future__ import annotations

import hashlib
import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.engine
import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .branch_separable_oracle import (
    SCHEMA_VERSION,
    _analyse_forced_move,
    _load_source,
    _scores_and_regrets,
    aggregate_branch_records,
)
from .config import write_json
from .human_corpus import sha256_file
from .model import _git_commit, _next_experiment_id
from .ordinary_branch import _load_oracle_cache
from .uncertainty_adjudication import _selector_digest, evaluate_selector


def _settings(config: dict) -> dict:
    if "temporal_allocation_adjudication" not in config:
        raise ValueError(
            "The active configuration has no temporal_allocation_adjudication section"
        )
    return config["temporal_allocation_adjudication"]


def derive_temporal_selectors(
    tiers: dict[str, dict[str, dict]],
    *,
    checkpoint_nodes: list[int],
    threshold_cp: int,
    score_clip_cp: int,
) -> dict[str, dict[str, set[str]]]:
    checkpoint_names = [f"{nodes // 1000}k" for nodes in checkpoint_nodes]
    checkpoint_tiers = [tiers[f"per-move-{nodes}"] for nodes in checkpoint_nodes]
    context_keys = set(checkpoint_tiers[0])
    if any(set(tier) != context_keys for tier in checkpoint_tiers[1:]):
        raise RuntimeError("Temporal checkpoint tiers contain different contexts")
    selectors = {name: {} for name in checkpoint_names}
    selectors["late_union"] = {}
    selectors["temporal_union"] = {}
    for context_key in sorted(context_keys):
        checkpoint_sets = []
        for name, tier in zip(checkpoint_names, checkpoint_tiers, strict=True):
            _, regrets = _scores_and_regrets(tier[context_key], score_clip_cp)
            near = {move for move, regret in regrets.items() if regret <= threshold_cp}
            selectors[name][context_key] = near
            checkpoint_sets.append(near)
        selectors["late_union"][context_key] = (
            checkpoint_sets[-2] | checkpoint_sets[-1]
        )
        selectors["temporal_union"][context_key] = set().union(*checkpoint_sets)
    return selectors


def _selector_identity(
    selector: dict[str, set[str]], contexts: dict[str, dict]
) -> dict:
    kinds = {key: context["kind"] for key, context in contexts.items()}
    legal_counts = {
        key: chess.Board(context["fen"]).legal_moves.count()
        for key, context in contexts.items()
    }
    result = {
        "retained_branches": sum(len(moves) for moves in selector.values()),
        "branch_key_digest": _selector_digest(selector, sorted(selector)),
    }
    for kind in ("root", "parent"):
        keys = sorted(key for key in selector if kinds[key] == kind)
        legal = sum(legal_counts[key] for key in keys)
        retained = sum(len(selector[key]) for key in keys)
        result[f"{kind}_legal_branches"] = legal
        result[f"{kind}_retained_branches"] = retained
        result[f"{kind}_micro_retained_fraction"] = retained / legal
        result[f"{kind}_mean_context_retained_fraction"] = float(
            np.mean([len(selector[key]) / legal_counts[key] for key in keys])
        )
        result[f"{kind}_branch_key_digest"] = _selector_digest(selector, keys)
    return result


def _load_source_and_selectors(
    settings: dict,
) -> tuple[dict, dict[str, dict], dict[str, dict[str, set[str]]]]:
    protocol_path = Path(settings["source_protocol_config"])
    if protocol_path.stat().st_size != int(settings["source_protocol_config_bytes"]):
        raise RuntimeError("Experiment 018 protocol byte count changed")
    if sha256_file(protocol_path) != settings["source_protocol_config_sha256"]:
        raise RuntimeError("Experiment 018 protocol checksum changed")
    source_config = json.loads(protocol_path.read_text(encoding="utf-8"))
    source_audit, contexts = _load_source(source_config["branch_separable_oracle"])
    if len(contexts) != int(settings["expected_contexts"]):
        raise RuntimeError("Experiment 020 context count changed")
    if int(source_audit["legal_branches"]) != int(settings["expected_legal_branches"]):
        raise RuntimeError("Experiment 020 legal branch count changed")

    cache_path = Path(settings["prior_oracle_cache"])
    metadata_path = Path(settings["prior_oracle_cache_metadata"])
    if cache_path.stat().st_size != int(settings["prior_oracle_cache_bytes"]):
        raise RuntimeError("Experiment 018 cache byte count changed")
    if sha256_file(cache_path) != settings["prior_oracle_cache_sha256"]:
        raise RuntimeError("Experiment 018 cache checksum changed")
    if metadata_path.stat().st_size != int(settings["prior_oracle_cache_metadata_bytes"]):
        raise RuntimeError("Experiment 018 cache metadata byte count changed")
    if sha256_file(metadata_path) != settings["prior_oracle_cache_metadata_sha256"]:
        raise RuntimeError("Experiment 018 cache metadata checksum changed")
    entries = _load_oracle_cache(cache_path)
    if {row["oracle_key"] for row in entries.values()} != {
        settings["prior_oracle_key"]
    }:
        raise RuntimeError("Experiment 018 oracle identity changed")
    tiers = aggregate_branch_records(entries)
    selectors = derive_temporal_selectors(
        tiers,
        checkpoint_nodes=[int(value) for value in settings["checkpoint_nodes"]],
        threshold_cp=int(settings["frozen_temporal_union"]["threshold_cp"]),
        score_clip_cp=int(settings["oracle"]["score_clip_cp"]),
    )
    actual = _selector_identity(selectors["temporal_union"], contexts)
    expected = {
        key: settings["frozen_temporal_union"][key]
        for key in (
            "retained_branches",
            "branch_key_digest",
            "root_legal_branches",
            "root_retained_branches",
            "root_micro_retained_fraction",
            "root_mean_context_retained_fraction",
            "root_branch_key_digest",
            "parent_legal_branches",
            "parent_retained_branches",
            "parent_micro_retained_fraction",
            "parent_mean_context_retained_fraction",
            "parent_branch_key_digest",
        )
    }
    if actual != expected:
        raise RuntimeError(f"Frozen temporal union changed: {actual}")
    return {**source_audit, **actual}, contexts, selectors


def audit_temporal_allocation_source(config: dict) -> dict:
    audit, _, _ = _load_source_and_selectors(_settings(config))
    return {**audit, "outcomes_probed": 0}


def _oracle_identity(engine: chess.engine.SimpleEngine, settings: dict) -> tuple[str, dict]:
    oracle = settings["oracle"]
    engine_name = engine.id.get("name", "unknown")
    engine_author = engine.id.get("author", "unknown")
    if not engine_name.startswith(str(oracle["engine"])):
        raise RuntimeError(
            f"Frozen temporal-allocation oracle requires {oracle['engine']}, "
            f"found {engine_name}"
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
        "nodes_per_move": int(settings["audit_nodes_per_move"]),
        "mate_score_cp": int(oracle["mate_score_cp"]),
        "score_clip_cp": int(oracle["score_clip_cp"]),
        "new_game_per_branch": bool(oracle["new_game_per_branch"]),
        "frozen_temporal_union_digest": settings["frozen_temporal_union"][
            "branch_key_digest"
        ],
        "protocol_version": settings["protocol_version"],
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    return key, identity


def populate_temporal_allocation_cache(
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
    nodes = int(settings["audit_nodes_per_move"])
    tier_id = f"per-move-{nodes}"
    expected_keys = {
        f"{tier_id}:{context_key}:{move.uci()}"
        for context_key, context in contexts.items()
        for move in chess.Board(context["fen"]).legal_moves
    }
    unexpected = set(entries) - expected_keys
    if unexpected:
        raise RuntimeError(
            f"Unexpected temporal-allocation cache keys: {sorted(unexpected)[:3]}"
        )
    engine = chess.engine.SimpleEngine.popen_uci(str(executable))
    started = time.perf_counter()
    new_analyses = 0
    cached_analyses = 0
    try:
        oracle_key, identity = _oracle_identity(engine, settings)
        metadata = {
            "oracle_key": oracle_key,
            "identity": identity,
            "source_protocol_config_sha256": settings[
                "source_protocol_config_sha256"
            ],
            "frozen_temporal_union_digest": settings["frozen_temporal_union"][
                "branch_key_digest"
            ],
        }
        if metadata_path.exists():
            if json.loads(metadata_path.read_text(encoding="utf-8")) != metadata:
                raise RuntimeError("Temporal-allocation cache metadata differs")
        else:
            write_json(metadata_path, metadata)
        if any(row["oracle_key"] != oracle_key for row in entries.values()):
            raise RuntimeError("Temporal-allocation cache oracle identity differs")
        with cache_path.open("a", encoding="utf-8") as output:
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
                        nodes=nodes,
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
                        "nodes_per_move": nodes,
                        "requested_nodes": nodes,
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
            f"Temporal-allocation cache incomplete: {len(entries)} != "
            f"{len(expected_keys)}"
        )
    return entries, {
        "oracle_key": next(iter(entries.values()))["oracle_key"],
        "analyses": len(entries),
        "new_analyses": new_analyses,
        "cached_analyses": cached_analyses,
        "runtime_seconds": time.perf_counter() - started,
    }


def measure_temporal_allocation(
    selectors: dict[str, dict[str, set[str]]],
    audit_tier: dict[str, dict],
    config: dict,
) -> dict:
    settings = _settings(config)
    evaluations = {
        name: evaluate_selector(
            selector,
            audit_tier,
            threshold_cp=int(settings["frozen_temporal_union"]["threshold_cp"]),
            score_clip_cp=int(settings["oracle"]["score_clip_cp"]),
        )
        for name, selector in selectors.items()
    }
    candidate = evaluations["temporal_union"]
    gate = settings["advancement_gate"]
    failures = []
    for kind in ("root", "parent"):
        metrics = candidate[kind]
        checks = {
            "decision_preservation_25cp": metrics["decision_preservation_25cp"]
            >= float(gate["minimum_decision_preservation_25cp"]),
            "maximum_pruning_loss_cp": metrics["maximum_pruning_loss_cp"]
            <= float(gate["maximum_pruning_loss_cp"]),
            "over_100cp_omissions": metrics["omissions_over_100cp"]
            <= int(gate["maximum_omissions_over_100cp"]),
            "over_300cp_omissions": metrics["omissions_over_300cp"]
            <= int(gate["maximum_omissions_over_300cp"]),
            "micro_retained_fraction": metrics["micro_retained_fraction"]
            < float(gate["maximum_micro_retained_fraction"][kind]),
            "mean_context_retained_fraction": metrics[
                "mean_context_retained_fraction"
            ]
            < float(gate["maximum_mean_context_retained_fraction"][kind]),
        }
        failures.extend(f"{kind}:{name}" for name, passed in checks.items() if not passed)
    return {
        "selectors": evaluations,
        "decision": {
            "passed": not failures,
            "failures": failures,
            "compact_selector_discovery_licensed": not failures,
            "exact_top_reply_recall_is_diagnostic": True,
            "complete_within25_set_recall_is_diagnostic": True,
            "models_trained": 0,
        },
    }


def _save_plot(artifact: Path, measurement: dict) -> None:
    names = ["10k", "40k", "160k", "late_union", "temporal_union"]
    labels = ["10k", "40k", "160k", "40k/160k", "10k/40k/160k"]
    pooled = [
        measurement["selectors"][name]["parent"]["micro_retained_fraction"]
        for name in names
    ]
    mean_context = [
        measurement["selectors"][name]["parent"][
            "mean_context_retained_fraction"
        ]
        for name in names
    ]
    preserved = [
        measurement["selectors"][name]["parent"]["decision_preservation_25cp"]
        for name in names
    ]
    max_loss = [
        measurement["selectors"][name]["parent"]["maximum_pruning_loss_cp"]
        for name in names
    ]
    x = np.arange(len(names))
    width = 0.36
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].bar(x - width / 2, pooled, width, label="pooled rho")
    axes[0].bar(x + width / 2, mean_context, width, label="mean context")
    axes[0].set_xticks(x, labels, rotation=15)
    axes[0].set_ylabel("Retained reply fraction")
    axes[0].set_title("Frozen selector size")
    axes[0].legend()
    axes[1].plot(x, preserved, marker="o", label="within-25 decision preservation")
    axes[1].set_xticks(x, labels, rotation=15)
    axes[1].set_ylim(0, 1.02)
    axes[1].set_ylabel("Preserved-context fraction")
    loss_axis = axes[1].twinx()
    loss_axis.plot(x, max_loss, marker="s", color="#e45756", label="maximum loss")
    loss_axis.set_ylabel("Maximum loss (cp)")
    axes[1].set_title("2.56M-node decision sufficiency")
    handles1, labels1 = axes[1].get_legend_handles_labels()
    handles2, labels2 = loss_axis.get_legend_handles_labels()
    axes[1].legend(handles1 + handles2, labels1 + labels2, loc="lower left")
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(artifact / "temporal_allocation_adjudication.png", dpi=160)
    plt.close(figure)


def _report(result: dict) -> str:
    decision = result["measurement"]["decision"]
    candidate = result["measurement"]["selectors"]["temporal_union"]
    parent = candidate["parent"]
    root = candidate["root"]
    root_preserved = root["decision_preservation_25cp"]
    root_maximum = root["maximum_pruning_loss_cp"]
    parent_preserved = parent["decision_preservation_25cp"]
    parent_maximum = parent["maximum_pruning_loss_cp"]
    parent_pooled = parent["micro_retained_fraction"]
    parent_mean = parent["mean_context_retained_fraction"]
    parent_top = parent["top_reply_recall"]
    parent_complete = parent["complete_within25_set_rate"]
    new_analyses = result["oracle"]["new_analyses"]
    cached_analyses = result["oracle"]["cached_analyses"]
    return f"""# Temporal computation-allocation adjudication

Experiment 020 prospectively audits the frozen 10k/40k/160k temporal union
with a new 2,560,000-node independent search of every legal move.

## Decision

- Advancement gate passed: **{decision['passed']}**
- Compact selector discovery licensed: **{decision['compact_selector_discovery_licensed']}**
- Failures: {decision['failures']}

## Candidate metrics

- Root decision preservation / maximum loss: {root_preserved:.2%} / {root_maximum:.0f} cp
- Parent decision preservation / maximum loss: {parent_preserved:.2%} / {parent_maximum:.0f} cp
- Parent pooled rho / mean-context fraction: {parent_pooled:.2%} / {parent_mean:.2%}
- Parent top / complete-within-25 recall diagnostics: {parent_top:.2%} / {parent_complete:.2%}

## Integrity

- Development contexts: {result['source_audit']['contexts']}
- Legal audit branches: {result['source_audit']['legal_branches']}
- Frozen temporal-union branches: {result['source_audit']['retained_branches']}
- New / cached audit analyses: {new_analyses} / {cached_analyses}
- Models trained: 0
- Selection outcomes probed: 0
- Confirmation outcomes probed: 0
- Runtime: {result['runtime_seconds']:.2f} seconds
- Git revision: `{result['git_commit']}`
"""


def run_temporal_allocation_adjudication(
    stockfish_path: str | Path,
    config: dict,
    *,
    results_dir: str | Path | None = None,
) -> tuple[dict, Path]:
    settings = _settings(config)
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    source_audit, contexts, selectors = _load_source_and_selectors(settings)
    entries, oracle_audit = populate_temporal_allocation_cache(
        stockfish_path, contexts, config
    )
    tiers = aggregate_branch_records(entries)
    tier_id = f"per-move-{int(settings['audit_nodes_per_move'])}"
    measurement = measure_temporal_allocation(selectors, tiers[tier_id], config)
    root = Path(results_dir or settings["results_directory"])
    experiment_id = _next_experiment_id(root, settings["experiment_name"])
    artifact = root / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    records_path = artifact / "adjudication_records.ndjson"
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
    _save_plot(artifact, measurement)
    return result, artifact
