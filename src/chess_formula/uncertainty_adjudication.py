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
from .ordinary_branch import _digest_lines, _load_oracle_cache


def _settings(config: dict) -> dict:
    if "uncertainty_adjudication" not in config:
        raise ValueError("The active configuration has no uncertainty_adjudication section")
    return config["uncertainty_adjudication"]


def derive_frozen_selectors(
    tiers: dict[str, dict[str, dict]], *, threshold_cp: int, score_clip_cp: int
) -> dict[str, dict[str, set[str]]]:
    lower = tiers["per-move-40000"]
    upper = tiers["per-move-160000"]
    if set(lower) != set(upper):
        raise RuntimeError("Frozen selector tiers contain different context sets")
    selectors = {name: {} for name in ("40k", "160k", "intersection", "union")}
    for context_key in sorted(lower):
        _, lower_regret = _scores_and_regrets(lower[context_key], score_clip_cp)
        _, upper_regret = _scores_and_regrets(upper[context_key], score_clip_cp)
        lower_set = {
            move for move, regret in lower_regret.items() if regret <= threshold_cp
        }
        upper_set = {
            move for move, regret in upper_regret.items() if regret <= threshold_cp
        }
        selectors["40k"][context_key] = lower_set
        selectors["160k"][context_key] = upper_set
        selectors["intersection"][context_key] = lower_set & upper_set
        selectors["union"][context_key] = lower_set | upper_set
    return selectors


def _selector_digest(selector: dict[str, set[str]], context_keys: list[str]) -> str:
    return _digest_lines(
        sorted(
            f"{context_key}:{move}"
            for context_key in context_keys
            for move in selector[context_key]
        )
    )


def _load_source_and_selectors(
    settings: dict,
) -> tuple[dict, dict[str, dict], dict[str, dict[str, dict]], dict[str, dict[str, set[str]]]]:
    protocol_path = Path(settings["source_protocol_config"])
    if protocol_path.stat().st_size != int(settings["source_protocol_config_bytes"]):
        raise RuntimeError("Experiment 018 protocol byte count changed")
    if sha256_file(protocol_path) != settings["source_protocol_config_sha256"]:
        raise RuntimeError("Experiment 018 protocol checksum changed")
    source_config = json.loads(protocol_path.read_text(encoding="utf-8"))
    source_audit, contexts = _load_source(source_config["branch_separable_oracle"])
    if len(contexts) != int(settings["expected_contexts"]):
        raise RuntimeError("Experiment 019 context count changed")
    if int(source_audit["legal_branches"]) != int(settings["expected_legal_branches"]):
        raise RuntimeError("Experiment 019 legal branch count changed")

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
    if {row["oracle_key"] for row in entries.values()} != {settings["prior_oracle_key"]}:
        raise RuntimeError("Experiment 018 oracle identity changed")
    tiers = aggregate_branch_records(entries)
    selectors = derive_frozen_selectors(
        tiers,
        threshold_cp=int(settings["frozen_union"]["threshold_cp"]),
        score_clip_cp=int(settings["oracle"]["score_clip_cp"]),
    )
    union = selectors["union"]
    kinds = {context_key: context["kind"] for context_key, context in contexts.items()}
    actual = {
        "retained_branches": sum(len(moves) for moves in union.values()),
        "branch_key_digest": _selector_digest(union, sorted(union)),
        "root_retained_branches": sum(
            len(union[key]) for key in union if kinds[key] == "root"
        ),
        "parent_retained_branches": sum(
            len(union[key]) for key in union if kinds[key] == "parent"
        ),
        "root_branch_key_digest": _selector_digest(
            union, sorted(key for key in union if kinds[key] == "root")
        ),
        "parent_branch_key_digest": _selector_digest(
            union, sorted(key for key in union if kinds[key] == "parent")
        ),
    }
    expected = {
        key: settings["frozen_union"][key]
        for key in (
            "retained_branches",
            "branch_key_digest",
            "root_retained_branches",
            "parent_retained_branches",
            "root_branch_key_digest",
            "parent_branch_key_digest",
        )
    }
    if actual != expected:
        raise RuntimeError(f"Frozen conservative union changed: {actual}")
    return {**source_audit, **actual}, contexts, tiers, selectors


def audit_uncertainty_adjudication_source(config: dict) -> dict:
    audit, _, _, _ = _load_source_and_selectors(_settings(config))
    return {**audit, "outcomes_probed": 0}


def _oracle_identity(engine: chess.engine.SimpleEngine, settings: dict) -> tuple[str, dict]:
    oracle = settings["oracle"]
    engine_name = engine.id.get("name", "unknown")
    engine_author = engine.id.get("author", "unknown")
    if not engine_name.startswith(str(oracle["engine"])):
        raise RuntimeError(
            f"Frozen adjudication oracle requires {oracle['engine']}, found {engine_name}"
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
        "frozen_union_digest": settings["frozen_union"]["branch_key_digest"],
        "protocol_version": settings["protocol_version"],
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    return key, identity


def populate_adjudication_cache(
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
        raise RuntimeError(f"Unexpected adjudication cache keys: {sorted(unexpected)[:3]}")
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
            "frozen_union_digest": settings["frozen_union"]["branch_key_digest"],
        }
        if metadata_path.exists():
            if json.loads(metadata_path.read_text(encoding="utf-8")) != metadata:
                raise RuntimeError("Adjudication cache metadata differs")
        else:
            write_json(metadata_path, metadata)
        if any(row["oracle_key"] != oracle_key for row in entries.values()):
            raise RuntimeError("Adjudication cache oracle identity differs")
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
        raise RuntimeError(f"Adjudication cache incomplete: {len(entries)} != {len(expected_keys)}")
    return entries, {
        "oracle_key": next(iter(entries.values()))["oracle_key"],
        "analyses": len(entries),
        "new_analyses": new_analyses,
        "cached_analyses": cached_analyses,
        "runtime_seconds": time.perf_counter() - started,
    }


def evaluate_selector(
    selector: dict[str, set[str]],
    audit: dict[str, dict],
    *,
    threshold_cp: int,
    score_clip_cp: int,
) -> dict:
    result = {}
    for kind in ("root", "parent"):
        contexts = 0
        legal = 0
        retained = 0
        top_retained = 0
        near_total = 0
        near_retained = 0
        complete_near_contexts = 0
        preserved_contexts = 0
        losses = []
        fractions = []
        failure_records = []
        zero_retained_contexts = 0
        for context_key in sorted(audit):
            row = audit[context_key]
            if row["context_kind"] != kind:
                continue
            contexts += 1
            _, regrets = _scores_and_regrets(row, score_clip_cp)
            selected = selector[context_key]
            if not selected <= set(regrets):
                raise RuntimeError(f"Invalid frozen selector set for {context_key}")
            top = min(regrets, key=lambda move: (regrets[move], move))
            near = {move for move, regret in regrets.items() if regret <= threshold_cp}
            if selected:
                best_retained = min(selected, key=lambda move: (regrets[move], move))
                loss = float(regrets[best_retained])
            else:
                best_retained = None
                loss = float(2 * score_clip_cp)
                zero_retained_contexts += 1
            top_retained += int(top in selected)
            near_total += len(near)
            near_retained += len(near & selected)
            complete_near_contexts += int(near <= selected)
            preserved_contexts += int(loss <= threshold_cp)
            legal += len(regrets)
            retained += len(selected)
            fractions.append(len(selected) / len(regrets))
            losses.append(loss)
            if top not in selected or not near <= selected or loss > threshold_cp:
                failure_records.append(
                    {
                        "context_key": context_key,
                        "audit_top_move": top,
                        "best_retained_move": best_retained,
                        "best_retained_regret_cp": loss,
                        "near25_total": len(near),
                        "near25_retained": len(near & selected),
                    }
                )
        result[kind] = {
            "contexts": contexts,
            "legal_branches": legal,
            "retained_branches": retained,
            "micro_retained_fraction": retained / legal,
            "mean_context_retained_fraction": float(np.mean(fractions)),
            "top_reply_recall": top_retained / contexts,
            "top_replies_retained": top_retained,
            "within25_branches": near_total,
            "within25_branches_retained": near_retained,
            "within25_micro_recall": near_retained / near_total,
            "complete_within25_set_rate": complete_near_contexts / contexts,
            "decision_preservation_25cp": preserved_contexts / contexts,
            "mean_pruning_loss_cp": float(np.mean(losses)),
            "median_pruning_loss_cp": float(np.median(losses)),
            "maximum_pruning_loss_cp": max(losses),
            "omissions_over_25cp": sum(loss > 25 for loss in losses),
            "omissions_over_100cp": sum(loss > 100 for loss in losses),
            "omissions_over_300cp": sum(loss > 300 for loss in losses),
            "zero_retained_contexts": zero_retained_contexts,
            "contexts_with_any_within25_false_negative": contexts
            - complete_near_contexts,
            "failure_records": failure_records,
        }
    return result


def measure_adjudication(
    selectors: dict[str, dict[str, set[str]]],
    audit_tier: dict[str, dict],
    config: dict,
) -> dict:
    settings = _settings(config)
    evaluations = {
        name: evaluate_selector(
            selector,
            audit_tier,
            threshold_cp=int(settings["frozen_union"]["threshold_cp"]),
            score_clip_cp=int(settings["oracle"]["score_clip_cp"]),
        )
        for name, selector in selectors.items()
    }
    union = evaluations["union"]
    gate = settings["advancement_gate"]
    failures = []
    for kind in ("root", "parent"):
        metrics = union[kind]
        checks = {
            "top_reply_recall": metrics["top_reply_recall"]
            >= float(gate["minimum_top_reply_recall"]),
            "within25_micro_recall": metrics["within25_micro_recall"]
            >= float(gate["minimum_within25_micro_recall"]),
            "decision_preservation_25cp": metrics["decision_preservation_25cp"]
            >= float(gate["minimum_decision_preservation_25cp"]),
            "over_100cp_omissions": metrics["omissions_over_100cp"]
            <= int(gate["maximum_omissions_over_100cp"]),
            "over_300cp_omissions": metrics["omissions_over_300cp"]
            <= int(gate["maximum_omissions_over_300cp"]),
            "retained_fraction": metrics["mean_context_retained_fraction"]
            <= float(gate["maximum_mean_retained_fraction"][kind]),
        }
        failures.extend(f"{kind}:{name}" for name, passed in checks.items() if not passed)
    exact_containment = all(
        union[kind]["within25_micro_recall"] == 1.0 for kind in ("root", "parent")
    )
    return {
        "selectors": evaluations,
        "decision": {
            "passed": not failures,
            "failures": failures,
            "exact_every_within25_branch_contained": exact_containment,
            "uncertainty_labels_licensed_for_future_training_experiment": not failures,
            "models_trained": 0,
        },
    }


def _save_plot(artifact: Path, measurement: dict) -> None:
    names = ["intersection", "40k", "160k", "union"]
    labels = ["intersection", "40k only", "160k only", "conservative union"]
    retained = [
        measurement["selectors"][name]["parent"]["mean_context_retained_fraction"]
        for name in names
    ]
    top = [
        measurement["selectors"][name]["parent"]["top_reply_recall"] for name in names
    ]
    near = [
        measurement["selectors"][name]["parent"]["within25_micro_recall"]
        for name in names
    ]
    x = np.arange(len(names))
    width = 0.36
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].bar(x, retained, color="#4c78a8")
    axes[0].set_xticks(x, labels, rotation=15)
    axes[0].set_ylabel("Mean retained reply fraction")
    axes[0].set_title("Frozen selector size")
    axes[1].bar(x - width / 2, top, width, label="640k top-reply recall")
    axes[1].bar(x + width / 2, near, width, label="640k within-25-cp recall")
    axes[1].set_xticks(x, labels, rotation=15)
    axes[1].set_ylim(0, 1.02)
    axes[1].set_ylabel("Recall")
    axes[1].set_title("Deeper independent adjudication")
    axes[1].legend()
    for axis in axes:
        axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(artifact / "uncertainty_adjudication.png", dpi=160)
    plt.close(figure)


def _report(result: dict) -> str:
    decision = result["measurement"]["decision"]
    licensed = decision["uncertainty_labels_licensed_for_future_training_experiment"]
    new_analyses = result["oracle"]["new_analyses"]
    cached_analyses = result["oracle"]["cached_analyses"]
    return f"""# Uncertainty-aware branch adjudication

Experiment 019 prospectively audits the frozen 40k/160k conservative branch
union with a new 640,000-node independent search of every legal move.

## Decision

- Advancement gate passed: **{decision['passed']}**
- Exact every-within-25-cp containment: **{decision['exact_every_within25_branch_contained']}**
- Future training experiment licensed: **{licensed}**
- Failures: {decision['failures']}

## Integrity

- Development contexts: {result['source_audit']['contexts']}
- Legal audit branches: {result['source_audit']['legal_branches']}
- Frozen union branches: {result['source_audit']['retained_branches']}
- New / cached audit analyses: {new_analyses} / {cached_analyses}
- Models trained: 0
- Selection outcomes probed: 0
- Confirmation outcomes probed: 0
- Runtime: {result['runtime_seconds']:.2f} seconds
- Git revision: `{result['git_commit']}`
"""


def run_uncertainty_adjudication(
    stockfish_path: str | Path,
    config: dict,
    *,
    results_dir: str | Path | None = None,
) -> tuple[dict, Path]:
    settings = _settings(config)
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    source_audit, contexts, _, selectors = _load_source_and_selectors(settings)
    entries, oracle_audit = populate_adjudication_cache(
        stockfish_path, contexts, config
    )
    tiers = aggregate_branch_records(entries)
    tier_id = f"per-move-{int(settings['audit_nodes_per_move'])}"
    measurement = measure_adjudication(selectors, tiers[tier_id], config)
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
