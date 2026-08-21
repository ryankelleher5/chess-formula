from __future__ import annotations

import hashlib
import platform
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.engine
import chess.pgn
import numpy as np

from .config import set_deterministic_seed, write_json
from .ingest import position_hash
from .model import _git_commit, _next_experiment_id
from .uci_match import load_opening_suite, play_uci_game, summarize_match


def _opening_hash(opening: dict) -> str:
    board = chess.Board()
    for move_uci in opening["moves"]:
        board.push_uci(move_uci)
    return position_hash(board.fen())


def validate_confirmation_openings(
    opening_suite: str | Path,
    prior_opening_suite: str | Path,
    *,
    expected_openings: int,
    expected_plies: int,
) -> tuple[list[dict], dict]:
    path = Path(opening_suite)
    prior_path = Path(prior_opening_suite)
    openings = load_opening_suite(path)
    prior = load_opening_suite(prior_path)
    if len(openings) != expected_openings:
        raise ValueError(f"Expected {expected_openings} confirmation openings")
    if any(len(opening["moves"]) != expected_plies for opening in openings):
        raise ValueError(f"Every confirmation opening must contain {expected_plies} plies")
    hashes = [_opening_hash(opening) for opening in openings]
    if len(set(hashes)) != len(hashes):
        raise ValueError("Confirmation suite contains duplicate final rule states")
    prior_hashes = {_opening_hash(opening) for opening in prior}
    prior_lines = {tuple(opening["moves"]) for opening in prior}
    final_overlaps = len(set(hashes) & prior_hashes)
    line_overlaps = sum(tuple(opening["moves"]) in prior_lines for opening in openings)
    if final_overlaps or line_overlaps:
        raise ValueError("Confirmation opening suite overlaps the UCI pilot")
    return openings, {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "openings": len(openings),
        "plies_each": expected_plies,
        "unique_final_rule_states": len(set(hashes)),
        "pilot_final_state_overlaps": final_overlaps,
        "pilot_move_sequence_overlaps": line_overlaps,
        "prior_suite_sha256": hashlib.sha256(prior_path.read_bytes()).hexdigest(),
    }


def confirmation_decision(matches: dict, settings: dict) -> dict:
    primary = settings["primary_opponent"]
    if primary not in matches:
        raise ValueError(f"Missing primary opponent: {primary}")
    candidate_faults = {
        "illegal_moves": sum(match["candidate_illegal_moves"] for match in matches.values()),
        "timeouts": sum(match["candidate_timeouts"] for match in matches.values()),
        "engine_errors": sum(match["candidate_engine_errors"] for match in matches.values()),
    }
    opponent_forfeits = sum(match["opponent_forfeits"] for match in matches.values())
    protocol_gate = not any(candidate_faults.values()) and opponent_forfeits == 0
    lower_bound = float(matches[primary]["score_rate_bootstrap"]["p2_5"])
    primary_gate = lower_bound > 0.5
    return {
        "candidate_faults": candidate_faults,
        "opponent_forfeits": opponent_forfeits,
        "protocol_gate_passes": protocol_gate,
        "primary_score_lower_bound": lower_bound,
        "primary_strength_gate_passes": primary_gate,
        "forcing_3_confirms": protocol_gate and primary_gate,
        "accepted_policy_after_confirmation": (
            settings["candidate"] if protocol_gate and primary_gate else "searched-3"
        ),
    }


def _stockfish_identity(path: Path, settings: dict) -> dict:
    engine = chess.engine.SimpleEngine.popen_uci(str(path))
    try:
        options = {
            "Threads": int(settings["stockfish_threads"]),
            "Hash": int(settings["stockfish_hash_mb"]),
        }
        configured = {key: value for key, value in options.items() if key in engine.options}
        if configured:
            engine.configure(configured)
        return {
            "name": engine.id.get("name", path.name),
            "author": engine.id.get("author", "unknown"),
            "path": str(path.resolve()),
            "options": options,
        }
    finally:
        with suppress(Exception):
            engine.quit()


def _report(result: dict) -> str:
    rows = []
    for name, summary in result["matches"].items():
        score = summary["score_rate_bootstrap"]
        elo = summary["engine_pool_elo_bootstrap"]
        candidate = summary["candidate_resources"]
        opponent = summary["opponent_resources"]
        rows.append(
            f"| {name} | {summary['wins']}-{summary['draws']}-{summary['losses']} | "
            f"{summary['score_rate']:.1%} [{score['p2_5']:.1%}, {score['p97_5']:.1%}] | "
            f"{summary['engine_pool_elo_difference']:+.0f} "
            f"[{elo['p2_5']:+.0f}, {elo['p97_5']:+.0f}] | "
            f"{candidate['mean_time_ms_per_move']:.1f} | "
            f"{candidate['mean_reported_nodes_per_move']:.1f} | "
            f"{opponent['mean_time_ms_per_move']:.1f} | "
            f"{opponent['mean_reported_nodes_per_move']:.1f} |"
        )
    primary = result["primary_resources"]
    table_header = (
        "| Opponent | W-D-L | Score [95%] | Pool Elo [95%] | Candidate ms | "
        "Candidate states | Opponent ms | Opponent states/nodes |"
    )
    return f"""# Forcing-3 UCI Confirmation: {result["experiment_id"]}

## Frozen protocol

- Git revision: {result["git_commit"]}
- Candidate: Locked-3 formula with three forcing plies and 256 children per root.
- Twenty new eight-ply openings, reversed colors, 40 games per opponent.
- Pilot final-state and move-sequence overlaps: zero.
- Maximum 160 plies; claimable draws; no evaluation adjudication.
- Stockfish: {result["stockfish"]["name"]}, 100 nodes/move, one thread, 16 MB hash.
- Uncertainty: {result["bootstrap_repeats"]} complete-opening-pair bootstrap samples.

## Results

{table_header}
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Decision and compute

- Protocol gate passes: **{result["decision"]["protocol_gate_passes"]}**
- Primary lower score bound above 50%: **{result["decision"]["primary_strength_gate_passes"]}**
- Forcing-3 confirms: **{result["decision"]["forcing_3_confirms"]}**
- Accepted policy: **{result["decision"]["accepted_policy_after_confirmation"]}**
- Candidate/baseline mean state ratio: {primary["candidate_to_baseline_state_ratio"]:.2f}x
- Candidate/baseline mean latency ratio: {primary["candidate_to_baseline_latency_ratio"]:.2f}x
- Candidate faults: {sum(result["decision"]["candidate_faults"].values())}
- Opponent forfeits: {result["decision"]["opponent_forfeits"]}
- Runtime: {result["runtime_seconds"]:.2f} seconds

## Guardrail

This confirms or rejects the loss-derived candidate only on the frozen opening,
opponent, resource, and adjudication domain. Pool Elo is not human FIDE Elo.
"""


def run_forcing_3_confirmation(
    stockfish_path: str | Path,
    config: dict,
    *,
    results_dir: str | Path = "results",
) -> tuple[dict, Path]:
    path = Path(stockfish_path)
    if not path.exists():
        raise FileNotFoundError(path)
    settings = config["uci_confirmation"]
    if settings["candidate"] != "forcing-3":
        raise ValueError("forcing-3 confirmation requires the frozen forcing-3 candidate")
    if int(settings["games_per_opening"]) != 2:
        raise ValueError("Every opening must be played with colors reversed")
    opponents = {opponent["name"]: opponent for opponent in settings["opponents"]}
    if set(opponents) != {"searched-3-baseline", "stockfish-100n"}:
        raise ValueError("Confirmation opponent pool differs from the frozen protocol")
    openings, opening_audit = validate_confirmation_openings(
        settings["opening_suite"],
        settings["prior_opening_suite"],
        expected_openings=int(settings["expected_openings"]),
        expected_plies=int(settings["expected_opening_plies"]),
    )
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    seed = int(config["seed"])
    set_deterministic_seed(seed)
    stockfish = _stockfish_identity(path, settings)
    matches = {}
    all_games = []
    pgns = []
    for opponent_index, opponent in enumerate(settings["opponents"]):
        games = []
        for opening in openings:
            for candidate_color in (chess.WHITE, chess.BLACK):
                record, pgn = play_uci_game(
                    opening,
                    opponent,
                    candidate_color,
                    path,
                    settings,
                )
                games.append(record)
                all_games.append(record)
                pgns.append(pgn)
        matches[opponent["name"]] = summarize_match(
            games,
            repeats=int(settings["bootstrap_repeats"]),
            seed=seed + opponent_index,
        )
    decision = confirmation_decision(matches, settings)
    primary = matches[settings["primary_opponent"]]
    candidate_resources = primary["candidate_resources"]
    baseline_resources = primary["opponent_resources"]
    primary_resources = {
        "candidate_to_baseline_state_ratio": (
            candidate_resources["mean_reported_nodes_per_move"]
            / baseline_resources["mean_reported_nodes_per_move"]
        ),
        "candidate_to_baseline_latency_ratio": (
            candidate_resources["mean_time_ms_per_move"]
            / baseline_resources["mean_time_ms_per_move"]
        ),
    }
    experiment_id = _next_experiment_id(
        Path(results_dir), settings.get("experiment_name", "forcing-3-uci-confirmation")
    )
    artifact = Path(results_dir) / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "git_commit": _git_commit(),
        "candidate": settings["candidate"],
        "openings": len(openings),
        "games": len(all_games),
        "bootstrap_repeats": int(settings["bootstrap_repeats"]),
        "opening_audit": opening_audit,
        "stockfish": stockfish,
        "matches": matches,
        "primary_resources": primary_resources,
        "decision": decision,
        "runtime_seconds": time.perf_counter() - started,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    write_json(artifact / "config.json", config)
    write_json(artifact / "metrics.json", result)
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
    return result, artifact
