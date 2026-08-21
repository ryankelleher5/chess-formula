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

from .config import write_json
from .human_corpus import sha256_file
from .model import _git_commit, _next_experiment_id
from .ordinary_branch import (
    _analyse_all_legal,
    _context_boards,
    _digest_lines,
    _load_oracle_cache,
    _mover_regret,
    _sample_rank,
    load_ordinary_source,
)


def _settings(config: dict) -> dict:
    if "oracle_convergence" not in config:
        raise ValueError("The active configuration has no oracle_convergence section")
    return config["oracle_convergence"]


def _load_frozen_source(settings: dict) -> tuple[list[dict], dict, dict[str, dict]]:
    protocol_path = Path(settings["source_protocol_config"])
    if protocol_path.stat().st_size != int(settings["source_protocol_config_bytes"]):
        raise RuntimeError("Source protocol byte count differs from Experiment 017")
    if sha256_file(protocol_path) != settings["source_protocol_config_sha256"]:
        raise RuntimeError("Source protocol checksum differs from Experiment 017")
    source_config = json.loads(protocol_path.read_text(encoding="utf-8"))
    records, source_audit = load_ordinary_source(source_config)
    ordinary = source_config["ordinary_branch_foundation"]
    contexts = _context_boards(records)
    stability = ordinary["stability_audit"]
    root_keys = sorted(key for key in contexts if key.startswith("root:"))
    parent_keys = sorted(key for key in contexts if key.startswith("parent:"))
    selected_keys = sorted(
        {
            *sorted(root_keys, key=_sample_rank)[: int(stability["root_contexts"])],
            *sorted(parent_keys, key=_sample_rank)[: int(stability["parent_contexts"])],
        }
    )
    selected = {key: contexts[key] for key in selected_keys}
    actual = {
        "contexts": len(selected),
        "root_contexts": sum(key.startswith("root:") for key in selected),
        "parent_contexts": sum(key.startswith("parent:") for key in selected),
        "context_key_digest": _digest_lines(selected_keys),
    }
    expected = {
        "contexts": int(settings["expected_contexts"]),
        "root_contexts": int(settings["expected_root_contexts"]),
        "parent_contexts": int(settings["expected_parent_contexts"]),
        "context_key_digest": settings["context_key_digest"],
    }
    if actual != expected:
        raise RuntimeError(f"Oracle-convergence context sample changed: {actual}")
    return records, {**source_audit, **actual}, selected


def audit_oracle_convergence_source(config: dict) -> dict:
    settings = _settings(config)
    _, audit, _ = _load_frozen_source(settings)
    return audit


def _tier_requests(settings: dict, contexts: dict[str, dict]) -> list[dict]:
    requests = []
    for family in settings["budget_families"]:
        family_id = family["id"]
        for level in family["levels"]:
            for context_key, context in sorted(contexts.items()):
                legal_moves = chess.Board(context["fen"]).legal_moves.count()
                if family["cost_rule"] == "fixed-total-nodes":
                    requested_nodes = int(level["value"])
                elif family["cost_rule"] == "nodes-per-legal-reply":
                    requested_nodes = int(level["value"]) * legal_moves
                else:
                    raise ValueError(f"Unknown cost rule: {family['cost_rule']}")
                requests.append(
                    {
                        "family": family_id,
                        "cost_rule": family["cost_rule"],
                        "tier_id": level["id"],
                        "tier_value": int(level["value"]),
                        "context_key": context_key,
                        "context": context,
                        "legal_moves": legal_moves,
                        "requested_nodes": requested_nodes,
                        "reuse_prefix": level.get("reuse_prefix"),
                    }
                )
    return requests


def _oracle_identity(engine: chess.engine.SimpleEngine, settings: dict) -> tuple[str, dict]:
    oracle = settings["oracle"]
    engine_name = engine.id.get("name", "unknown")
    engine_author = engine.id.get("author", "unknown")
    if not engine_name.startswith(str(oracle["engine"])):
        raise RuntimeError(
            f"Frozen convergence oracle requires {oracle['engine']}, found {engine_name}"
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
        "multipv": oracle["multipv"],
        "mate_score_cp": int(oracle["mate_score_cp"]),
        "score_clip_cp": int(oracle["score_clip_cp"]),
        "new_game_per_context": bool(oracle["new_game_per_context"]),
        "budget_families": settings["budget_families"],
        "protocol_version": settings["protocol_version"],
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    return key, identity


def _load_prior_cache(settings: dict) -> dict[str, dict]:
    path = Path(settings["prior_oracle_cache"])
    metadata_path = Path(settings["prior_oracle_cache_metadata"])
    if path.stat().st_size != int(settings["prior_oracle_cache_bytes"]):
        raise RuntimeError("Experiment 016 oracle cache byte count changed")
    if sha256_file(path) != settings["prior_oracle_cache_sha256"]:
        raise RuntimeError("Experiment 016 oracle cache checksum changed")
    if metadata_path.stat().st_size != int(settings["prior_oracle_cache_metadata_bytes"]):
        raise RuntimeError("Experiment 016 oracle metadata byte count changed")
    if sha256_file(metadata_path) != settings["prior_oracle_cache_metadata_sha256"]:
        raise RuntimeError("Experiment 016 oracle metadata checksum changed")
    entries = _load_oracle_cache(path)
    if not entries:
        raise RuntimeError("Experiment 016 oracle cache is empty")
    if {row["oracle_key"] for row in entries.values()} != {settings["prior_oracle_key"]}:
        raise RuntimeError("Experiment 016 oracle identity changed")
    return entries


def populate_convergence_cache(
    stockfish_path: str | Path,
    contexts: dict[str, dict],
    config: dict,
) -> tuple[dict[str, dict], dict]:
    settings = _settings(config)
    executable = Path(stockfish_path)
    if not executable.exists():
        raise FileNotFoundError(executable)
    prior = _load_prior_cache(settings)
    cache_path = Path(settings["oracle_cache"])
    metadata_path = Path(settings["oracle_cache_metadata"])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    entries = _load_oracle_cache(cache_path)
    requests = _tier_requests(settings, contexts)
    engine = chess.engine.SimpleEngine.popen_uci(str(executable))
    started = time.perf_counter()
    new_analyses = 0
    reused_analyses = 0
    cached_analyses = 0
    try:
        oracle_key, identity = _oracle_identity(engine, settings)
        metadata = {
            "oracle_key": oracle_key,
            "identity": identity,
            "source_protocol_config_sha256": settings["source_protocol_config_sha256"],
            "context_key_digest": settings["context_key_digest"],
            "prior_oracle_cache_sha256": settings["prior_oracle_cache_sha256"],
        }
        if metadata_path.exists():
            if json.loads(metadata_path.read_text(encoding="utf-8")) != metadata:
                raise RuntimeError("Oracle-convergence cache metadata differs")
        else:
            write_json(metadata_path, metadata)
        if any(row["oracle_key"] != oracle_key for row in entries.values()):
            raise RuntimeError("Oracle-convergence cache identity differs")
        with cache_path.open("a", encoding="utf-8") as output:
            for request in requests:
                cache_key = f"{request['tier_id']}:{request['context_key']}"
                if cache_key in entries:
                    cached_analyses += 1
                    continue
                reuse_prefix = request["reuse_prefix"]
                if reuse_prefix:
                    prior_key = f"{reuse_prefix}:{request['context_key']}"
                    if prior_key not in prior:
                        raise RuntimeError(f"Missing frozen reused oracle record: {prior_key}")
                    source = prior[prior_key]
                    if int(source["limit_nodes"]) != int(request["requested_nodes"]):
                        raise RuntimeError(f"Reused node limit differs for {prior_key}")
                    analysis = {
                        key: source[key]
                        for key in (
                            "fen",
                            "side_to_move",
                            "legal_moves",
                            "limit_nodes",
                            "elapsed_ms",
                            "moves",
                        )
                    }
                    reused_analyses += 1
                else:
                    analysis = _analyse_all_legal(
                        engine,
                        chess.Board(request["context"]["fen"]),
                        nodes=int(request["requested_nodes"]),
                        mate_score_cp=int(settings["oracle"]["mate_score_cp"]),
                        game_key=cache_key,
                    )
                    new_analyses += 1
                result = {
                    "cache_key": cache_key,
                    "context_key": request["context_key"],
                    "context_kind": request["context"]["kind"],
                    "family": request["family"],
                    "cost_rule": request["cost_rule"],
                    "tier_id": request["tier_id"],
                    "tier_value": request["tier_value"],
                    "requested_nodes": request["requested_nodes"],
                    "oracle_key": oracle_key,
                    "reused_from_experiment_016": bool(reuse_prefix),
                    **analysis,
                }
                output.write(json.dumps(result, sort_keys=True) + "\n")
                output.flush()
                entries[cache_key] = result
    finally:
        engine.quit()
    if len(entries) != len(requests):
        raise RuntimeError(
            f"Oracle-convergence cache is incomplete: {len(entries)} != {len(requests)}"
        )
    return entries, {
        "oracle_key": next(iter(entries.values()))["oracle_key"],
        "analyses": len(entries),
        "new_analyses": new_analyses,
        "reused_experiment_016_analyses": reused_analyses,
        "cached_analyses": cached_analyses,
        "runtime_seconds": time.perf_counter() - started,
    }


def _ranked_moves(scores: dict[str, float], turn: chess.Color) -> list[str]:
    return sorted(scores, key=lambda move: ((-scores[move]) if turn else scores[move], move))


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left or right else 1.0


def compare_oracle_tiers(
    left: dict[str, dict],
    right: dict[str, dict],
    *,
    thresholds: list[int],
    score_clip_cp: int,
) -> dict:
    if set(left) != set(right):
        raise RuntimeError("Oracle tiers contain different context sets")
    by_kind = {}
    for kind in ("root", "parent"):
        top_agreement = []
        top_jaccards = {3: [], 5: []}
        near_jaccards = {threshold: [] for threshold in thresholds}
        label_matches = {threshold: [] for threshold in thresholds}
        regret_errors = []
        score_errors = []
        rank_correlations = []
        contexts = 0
        moves = 0
        for context_key in sorted(left):
            a = left[context_key]
            b = right[context_key]
            if a["context_kind"] != kind:
                continue
            contexts += 1
            board = chess.Board(a["fen"])
            a_scores = {
                row["move_uci"]: float(np.clip(row["eval_cp"], -score_clip_cp, score_clip_cp))
                for row in a["moves"]
            }
            b_scores = {
                row["move_uci"]: float(np.clip(row["eval_cp"], -score_clip_cp, score_clip_cp))
                for row in b["moves"]
            }
            if set(a_scores) != set(b_scores):
                raise RuntimeError(f"Legal move set changed for {context_key}")
            moves += len(a_scores)
            a_ranked = _ranked_moves(a_scores, board.turn)
            b_ranked = _ranked_moves(b_scores, board.turn)
            top_agreement.append(a_ranked[0] == b_ranked[0])
            for k in top_jaccards:
                top_jaccards[k].append(_jaccard(set(a_ranked[:k]), set(b_ranked[:k])))
            n = len(a_ranked)
            if n > 1:
                b_ranks = {move: index for index, move in enumerate(b_ranked)}
                squared = sum((index - b_ranks[move]) ** 2 for index, move in enumerate(a_ranked))
                rank_correlations.append(1 - 6 * squared / (n * (n * n - 1)))
            else:
                rank_correlations.append(1.0)
            a_best = a_scores[a_ranked[0]]
            b_best = b_scores[b_ranked[0]]
            a_regrets = {
                move: _mover_regret(a_best, value, board.turn)
                for move, value in a_scores.items()
            }
            b_regrets = {
                move: _mover_regret(b_best, value, board.turn)
                for move, value in b_scores.items()
            }
            for move in a_scores:
                score_errors.append(abs(a_scores[move] - b_scores[move]))
                regret_errors.append(abs(a_regrets[move] - b_regrets[move]))
            for threshold in thresholds:
                a_near = {move for move, regret in a_regrets.items() if regret <= threshold}
                b_near = {move for move, regret in b_regrets.items() if regret <= threshold}
                near_jaccards[threshold].append(_jaccard(a_near, b_near))
                label_matches[threshold].extend(
                    (a_regrets[move] <= threshold) == (b_regrets[move] <= threshold)
                    for move in a_scores
                )
        by_kind[kind] = {
            "contexts": contexts,
            "moves": moves,
            "top_move_agreement": float(np.mean(top_agreement)),
            "mean_top3_set_jaccard": float(np.mean(top_jaccards[3])),
            "mean_top5_set_jaccard": float(np.mean(top_jaccards[5])),
            "mean_rank_spearman": float(np.mean(rank_correlations)),
            "mean_common_move_score_difference_cp": float(np.mean(score_errors)),
            "median_common_move_score_difference_cp": float(np.median(score_errors)),
            "mean_move_regret_difference_cp": float(np.mean(regret_errors)),
            "median_move_regret_difference_cp": float(np.median(regret_errors)),
            "mean_near_set_jaccard": {
                str(threshold): float(np.mean(values))
                for threshold, values in near_jaccards.items()
            },
            "threshold_label_agreement": {
                str(threshold): float(np.mean(values))
                for threshold, values in label_matches.items()
            },
        }
    return by_kind


def _passes_gate(comparison: dict, gate: dict) -> tuple[bool, list[str]]:
    failures = []
    for kind in ("root", "parent"):
        metrics = comparison[kind]
        checks = {
            "top_move_agreement": metrics["top_move_agreement"]
            >= float(gate["minimum_top_move_agreement"]),
            "top3_set_jaccard": metrics["mean_top3_set_jaccard"]
            >= float(gate["minimum_top3_set_jaccard"]),
            "near25_set_jaccard": metrics["mean_near_set_jaccard"]["25"]
            >= float(gate["minimum_near25_set_jaccard"]),
            "median_regret_difference": metrics["median_move_regret_difference_cp"]
            <= float(gate["maximum_median_regret_difference_cp"]),
        }
        for threshold in gate["required_label_thresholds_cp"]:
            checks[f"label_agreement_{threshold}"] = metrics[
                "threshold_label_agreement"
            ][str(threshold)] >= float(gate["minimum_threshold_label_agreement"])
        failures.extend(f"{kind}:{name}" for name, passed in checks.items() if not passed)
    return not failures, failures


def measure_convergence(entries: dict[str, dict], config: dict) -> dict:
    settings = _settings(config)
    thresholds = [int(value) for value in settings["regret_thresholds_cp"]]
    clip = int(settings["oracle"]["score_clip_cp"])
    tier_entries: dict[str, dict[str, dict]] = {}
    tier_summary = {}
    for family in settings["budget_families"]:
        for level in family["levels"]:
            tier_id = level["id"]
            rows = {
                row["context_key"]: row
                for row in entries.values()
                if row["tier_id"] == tier_id
            }
            tier_entries[tier_id] = rows
            requested = [row["requested_nodes"] for row in rows.values()]
            tier_summary[tier_id] = {
                "family": family["id"],
                "cost_rule": family["cost_rule"],
                "tier_value": int(level["value"]),
                "contexts": len(rows),
                "mean_requested_nodes": float(np.mean(requested)),
                "median_requested_nodes": float(np.median(requested)),
                "minimum_requested_nodes": min(requested),
                "maximum_requested_nodes": max(requested),
                "total_requested_nodes": sum(requested),
            }
    comparisons = {}
    eligibility = {}
    family_maxima = {}
    for family in settings["budget_families"]:
        levels = family["levels"]
        maximum_id = levels[-1]["id"]
        family_maxima[family["id"]] = maximum_id
        for index, level in enumerate(levels):
            tier_id = level["id"]
            targets = {"family_maximum": maximum_id}
            if index + 1 < len(levels):
                targets["next_level"] = levels[index + 1]["id"]
            for relation, target_id in targets.items():
                key = f"{tier_id}__vs__{target_id}"
                if key not in comparisons:
                    comparisons[key] = compare_oracle_tiers(
                        tier_entries[tier_id],
                        tier_entries[target_id],
                        thresholds=thresholds,
                        score_clip_cp=clip,
                    )
                passed, failures = _passes_gate(comparisons[key], settings["stability_gate"])
                eligibility[f"{tier_id}:{relation}"] = {
                    "comparison": key,
                    "passed": passed,
                    "failures": failures,
                }
    cross = settings["cross_cost_rule_comparison"]
    cross_key = f"{cross['left_tier']}__vs__{cross['right_tier']}"
    comparisons[cross_key] = compare_oracle_tiers(
        tier_entries[cross["left_tier"]],
        tier_entries[cross["right_tier"]],
        thresholds=thresholds,
        score_clip_cp=clip,
    )
    cross_passed, cross_failures = _passes_gate(
        comparisons[cross_key], settings["stability_gate"]
    )
    candidates = []
    if cross_passed:
        for family in settings["budget_families"]:
            maximum_id = family_maxima[family["id"]]
            for level in family["levels"]:
                tier_id = level["id"]
                relation = eligibility[f"{tier_id}:family_maximum"]
                adjacent = eligibility.get(f"{tier_id}:next_level", relation)
                if relation["passed"] and adjacent["passed"]:
                    candidates.append(tier_id)
    candidates.sort(key=lambda tier: (tier_summary[tier]["mean_requested_nodes"], tier))
    selected = candidates[0] if candidates else None
    return {
        "tiers": tier_summary,
        "comparisons": comparisons,
        "eligibility": eligibility,
        "cross_cost_rule": {
            "comparison": cross_key,
            "passed": cross_passed,
            "failures": cross_failures,
        },
        "decision": {
            "stability_gate_passed": selected is not None,
            "selected_training_reference": selected,
            "eligible_tiers": candidates,
            "model_training_unblocked": selected is not None,
        },
    }


def _save_plot(artifact: Path, convergence: dict, settings: dict) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for family in settings["budget_families"]:
        levels = family["levels"]
        maximum = levels[-1]["id"]
        x = []
        top = []
        near = []
        for level in levels:
            tier = level["id"]
            comparison = convergence["comparisons"][f"{tier}__vs__{maximum}"]["parent"]
            x.append(convergence["tiers"][tier]["mean_requested_nodes"])
            top.append(comparison["top_move_agreement"])
            near.append(comparison["mean_near_set_jaccard"]["25"])
        label = family["label"]
        axes[0].plot(x, top, marker="o", label=label)
        axes[1].plot(x, near, marker="o", label=label)
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
    axes[0].set_title("Opponent top-reply stability")
    axes[1].set_title("Opponent within-25-cp set stability")
    for axis in axes:
        axis.set_xscale("log")
        axis.set_ylim(0, 1.02)
        axis.set_xlabel("Mean requested nodes per context")
        axis.grid(alpha=0.25)
        axis.legend()
    axes[0].set_ylabel("Agreement with family maximum")
    axes[1].set_ylabel("Jaccard agreement with family maximum")
    figure.tight_layout()
    figure.savefig(artifact / "oracle_convergence_curve.png", dpi=160)
    plt.close(figure)


def _report(result: dict) -> str:
    decision = result["convergence"]["decision"]
    cross = result["convergence"]["cross_cost_rule"]
    lines = [
        "# Ordinary branch-oracle convergence",
        "",
        "Experiment 017 tests whether ordinary root and opponent-reply labels stabilize as",
        "Stockfish computation increases under fixed-total and per-legal-reply budgets.",
        "",
        "## Decision",
        "",
        f"- Stability gate passed: **{decision['stability_gate_passed']}**",
        f"- Selected training reference: `{decision['selected_training_reference']}`",
        f"- Model training unblocked: **{decision['model_training_unblocked']}**",
        f"- Deepest cross-cost-rule gate passed: **{cross['passed']}**",
        "",
        "## Integrity",
        "",
        f"- Development contexts: {result['source_audit']['contexts']}",
        f"- Root / opponent-parent contexts: {result['source_audit']['root_contexts']} / "
        f"{result['source_audit']['parent_contexts']}",
        f"- Oracle analyses: {result['oracle']['analyses']}",
        f"- New / reused / cached analyses: {result['oracle']['new_analyses']} / "
        f"{result['oracle']['reused_experiment_016_analyses']} / "
        f"{result['oracle']['cached_analyses']}",
        "- Selection outcomes probed: 0",
        "- Confirmation outcomes probed: 0",
        f"- Runtime: {result['runtime_seconds']:.2f} seconds",
        f"- Git revision: `{result['git_commit']}`",
        "",
        "Passing this finite-budget gate means only that the sampled labels reached the",
        "preregistered empirical plateau. It does not make Stockfish an infallible oracle.",
    ]
    return "\n".join(lines) + "\n"


def run_oracle_convergence(
    stockfish_path: str | Path,
    config: dict,
    *,
    results_dir: str | Path | None = None,
) -> tuple[dict, Path]:
    settings = _settings(config)
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    _, source_audit, contexts = _load_frozen_source(settings)
    entries, oracle_audit = populate_convergence_cache(stockfish_path, contexts, config)
    convergence = measure_convergence(entries, config)
    root = Path(results_dir or settings["results_directory"])
    experiment_id = _next_experiment_id(root, settings["experiment_name"])
    artifact = root / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
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
        "convergence": convergence,
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
    _save_plot(artifact, convergence, settings)
    return result, artifact
