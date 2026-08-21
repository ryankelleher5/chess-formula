from __future__ import annotations

import json
import math
import platform
import sys
import time
from collections import Counter
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.engine
import chess.pgn
import numpy as np

from .config import set_deterministic_seed, write_json
from .model import _git_commit, _next_experiment_id
from .stability import _interval


def load_opening_suite(path: str | Path) -> list[dict]:
    openings = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(openings, list) or not openings:
        raise ValueError("Opening suite must be a non-empty JSON list")
    seen = set()
    for opening in openings:
        if set(opening) != {"id", "moves"} or not opening["id"] or opening["id"] in seen:
            raise ValueError("Every opening needs a unique id and moves list")
        seen.add(opening["id"])
        board = chess.Board()
        for move_uci in opening["moves"]:
            move = chess.Move.from_uci(move_uci)
            if move not in board.legal_moves:
                raise ValueError(f"Illegal move {move_uci} in opening {opening['id']}")
            board.push(move)
        if board.is_game_over(claim_draw=False):
            raise ValueError(f"Opening {opening['id']} is already terminal")
    return openings


def score_to_elo(score_rate: float, games: int) -> float:
    if games < 1:
        raise ValueError("At least one game is required for Elo conversion")
    epsilon = 0.5 / (games + 1)
    adjusted = min(max(score_rate, epsilon), 1.0 - epsilon)
    return float(400 * math.log10(adjusted / (1.0 - adjusted)))


def _policy_command(policy: str) -> list[str]:
    return [sys.executable, "-m", "chess_formula.uci", "--policy", policy]


def _open_engine(
    specification: dict,
    *,
    stockfish_path: str | Path,
    timeout: float,
    settings: dict,
) -> chess.engine.SimpleEngine:
    if specification["type"] == "policy":
        command: str | list[str] = _policy_command(specification["policy"])
    elif specification["type"] == "stockfish":
        command = str(stockfish_path)
    else:
        raise ValueError(f"Unknown opponent type: {specification['type']}")
    engine = chess.engine.SimpleEngine.popen_uci(command, timeout=timeout)
    if specification["type"] == "stockfish":
        options = {
            "Threads": int(settings["stockfish_threads"]),
            "Hash": int(settings["stockfish_hash_mb"]),
        }
        engine.configure({key: value for key, value in options.items() if key in engine.options})
    return engine


def _opening_board(opening: dict) -> chess.Board:
    board = chess.Board()
    for move_uci in opening["moves"]:
        board.push_uci(move_uci)
    return board


def _result_for_winner(winner: chess.Color | None) -> str:
    if winner is chess.WHITE:
        return "1-0"
    if winner is chess.BLACK:
        return "0-1"
    return "1/2-1/2"


def _telemetry() -> dict:
    return {"moves": 0, "total_time_ms": 0.0, "reported_nodes": 0}


def play_uci_game(
    opening: dict,
    opponent: dict,
    candidate_color: chess.Color,
    stockfish_path: str | Path,
    settings: dict,
) -> tuple[dict, str]:
    timeout = float(settings["engine_timeout_seconds"])
    candidate_spec = {"type": "policy", "policy": settings["candidate"]}
    candidate = _open_engine(
        candidate_spec,
        stockfish_path=stockfish_path,
        timeout=timeout,
        settings=settings,
    )
    adversary = _open_engine(
        opponent,
        stockfish_path=stockfish_path,
        timeout=timeout,
        settings=settings,
    )
    board = _opening_board(opening)
    game_token = object()
    candidate_stats = _telemetry()
    opponent_stats = _telemetry()
    failure_actor = None
    failure_kind = None
    termination = None
    winner = None
    try:
        while len(board.move_stack) < int(settings["maximum_total_plies"]):
            outcome = board.outcome(claim_draw=bool(settings["draw_claims"]))
            if outcome is not None:
                winner = outcome.winner
                termination = outcome.termination.name.lower().replace("_", "-")
                break
            candidate_turn = board.turn == candidate_color
            active = candidate if candidate_turn else adversary
            active_stats = candidate_stats if candidate_turn else opponent_stats
            if candidate_turn or opponent["type"] == "policy":
                limit = chess.engine.Limit(nodes=int(settings["policy_go_nodes"]))
            else:
                limit = chess.engine.Limit(nodes=int(opponent["nodes_per_move"]))
            started = time.perf_counter()
            try:
                played = active.play(
                    board,
                    limit,
                    game=game_token,
                    info=chess.engine.INFO_ALL,
                )
            except TimeoutError:
                failure_actor = "candidate" if candidate_turn else "opponent"
                failure_kind = "timeout"
                winner = not board.turn
                termination = f"{failure_actor}-timeout-forfeit"
                break
            except (chess.engine.EngineError, chess.engine.EngineTerminatedError, OSError):
                failure_actor = "candidate" if candidate_turn else "opponent"
                failure_kind = "engine-error"
                winner = not board.turn
                termination = f"{failure_actor}-engine-error-forfeit"
                break
            elapsed_ms = (time.perf_counter() - started) * 1000
            active_stats["moves"] += 1
            active_stats["total_time_ms"] += elapsed_ms
            active_stats["reported_nodes"] += int(played.info.get("nodes", 0) or 0)
            if played.move is None:
                failure_actor = "candidate" if candidate_turn else "opponent"
                failure_kind = "null-move"
                winner = not board.turn
                termination = f"{failure_actor}-null-move-forfeit"
                break
            if played.move not in board.legal_moves:
                failure_actor = "candidate" if candidate_turn else "opponent"
                failure_kind = "illegal-move"
                winner = not board.turn
                termination = f"{failure_actor}-illegal-move-forfeit"
                break
            board.push(played.move)
        else:
            winner = None
            termination = "maximum-plies"
    finally:
        with suppress(Exception):
            candidate.quit()
        with suppress(Exception):
            adversary.quit()

    result = _result_for_winner(winner)
    if winner is None:
        candidate_score = 0.5
    else:
        candidate_score = float(winner == candidate_color)
    record = {
        "opening_id": opening["id"],
        "candidate_color": "white" if candidate_color else "black",
        "opponent": opponent["name"],
        "result": result,
        "candidate_score": candidate_score,
        "termination": termination,
        "failure_actor": failure_actor,
        "failure_kind": failure_kind,
        "total_plies": len(board.move_stack),
        "moves_uci": [move.uci() for move in board.move_stack],
        "candidate_telemetry": candidate_stats,
        "opponent_telemetry": opponent_stats,
    }
    pgn = chess.pgn.Game.from_board(board)
    pgn.headers.update(
        {
            "Event": "Chess Formula UCI Playing Pilot",
            "Site": "local",
            "Round": opening["id"],
            "White": settings["candidate"] if candidate_color else opponent["name"],
            "Black": opponent["name"] if candidate_color else settings["candidate"],
            "Result": result,
            "Termination": termination or "unknown",
        }
    )
    return record, str(pgn)


def summarize_match(games: list[dict], *, repeats: int, seed: int) -> dict:
    if not games:
        raise ValueError("Cannot summarize an empty match")
    scores = np.asarray([game["candidate_score"] for game in games], dtype=float)
    opening_ids = sorted({game["opening_id"] for game in games})
    pair_scores = {
        opening_id: np.asarray(
            [game["candidate_score"] for game in games if game["opening_id"] == opening_id],
            dtype=float,
        )
        for opening_id in opening_ids
    }
    if any(len(values) != 2 for values in pair_scores.values()):
        raise ValueError("Every opening must contribute exactly one reversed-color pair")
    rng = np.random.default_rng(seed)
    bootstrap_scores = []
    for _ in range(repeats):
        sampled = rng.choice(opening_ids, size=len(opening_ids), replace=True)
        bootstrap_scores.append(
            float(np.mean(np.concatenate([pair_scores[opening] for opening in sampled])))
        )
    score_interval = _interval(bootstrap_scores)
    elo_runs = [score_to_elo(score, len(games)) for score in bootstrap_scores]
    candidate_telemetry = [game["candidate_telemetry"] for game in games]
    opponent_telemetry = [game["opponent_telemetry"] for game in games]

    def resource_summary(rows: list[dict]) -> dict:
        moves = sum(row["moves"] for row in rows)
        total_ms = sum(row["total_time_ms"] for row in rows)
        nodes = sum(row["reported_nodes"] for row in rows)
        return {
            "moves": moves,
            "mean_time_ms_per_move": total_ms / moves if moves else 0.0,
            "mean_reported_nodes_per_move": nodes / moves if moves else 0.0,
        }

    score_rate = float(np.mean(scores))
    return {
        "games": len(games),
        "opening_pairs": len(opening_ids),
        "wins": int(np.sum(scores == 1.0)),
        "draws": int(np.sum(scores == 0.5)),
        "losses": int(np.sum(scores == 0.0)),
        "score_rate": score_rate,
        "score_rate_bootstrap": score_interval,
        "engine_pool_elo_difference": score_to_elo(score_rate, len(games)),
        "engine_pool_elo_bootstrap": _interval(elo_runs),
        "terminations": dict(Counter(game["termination"] for game in games)),
        "candidate_illegal_moves": sum(
            game["failure_actor"] == "candidate" and game["failure_kind"] == "illegal-move"
            for game in games
        ),
        "candidate_timeouts": sum(
            game["failure_actor"] == "candidate" and game["failure_kind"] == "timeout"
            for game in games
        ),
        "candidate_engine_errors": sum(
            game["failure_actor"] == "candidate"
            and game["failure_kind"] in {"engine-error", "null-move"}
            for game in games
        ),
        "opponent_forfeits": sum(game["failure_actor"] == "opponent" for game in games),
        "candidate_resources": resource_summary(candidate_telemetry),
        "opponent_resources": resource_summary(opponent_telemetry),
    }


def _report(result: dict) -> str:
    rows = []
    for name, summary in result["matches"].items():
        score = summary["score_rate_bootstrap"]
        elo = summary["engine_pool_elo_bootstrap"]
        resources = summary["candidate_resources"]
        rows.append(
            f"| {name} | {summary['wins']}-{summary['draws']}-{summary['losses']} | "
            f"{summary['score_rate']:.1%} "
            f"[{score['p2_5']:.1%}, {score['p97_5']:.1%}] | "
            f"{summary['engine_pool_elo_difference']:+.0f} "
            f"[{elo['p2_5']:+.0f}, {elo['p97_5']:+.0f}] | "
            f"{resources['mean_time_ms_per_move']:.1f} | "
            f"{resources['mean_reported_nodes_per_move']:.1f} |"
        )
    table_header = (
        "| Opponent | W-D-L | Score [95%] | Engine-pool Elo [95%] | "
        "Candidate ms/move | Candidate nodes/move |"
    )
    return f"""# UCI Playing-Strength Pilot: {result['experiment_id']}

## Frozen protocol

- Git revision: {result['git_commit']}
- Candidate: frozen Searched Locked-3 through a UCI subprocess.
- Twenty eight-ply openings, reversed colors, 40 games per opponent.
- Maximum 160 total plies; claimable draws enabled; no evaluation adjudication.
- Candidate computation is fixed; Stockfish receives 100 nodes per move.
- Uncertainty uses {result['bootstrap_repeats']} opening-pair bootstrap samples.

## Results

{table_header}
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

- Candidate illegal moves: **{result['candidate_faults']['illegal_moves']}**
- Candidate timeouts: **{result['candidate_faults']['timeouts']}**
- Candidate engine errors/null moves: **{result['candidate_faults']['engine_errors']}**
- Protocol gate passes: **{result['decision']['protocol_gate_passes']}**

## Guardrail

These engine-pool Elo differences apply only to this opening suite, adjudication,
resource control, and opponent pool. They are not human FIDE ratings.
"""


def run_uci_pilot(
    stockfish_path: str | Path,
    config: dict,
    *,
    results_dir: str | Path = "results",
) -> tuple[dict, Path]:
    path = Path(stockfish_path)
    if not path.exists():
        raise FileNotFoundError(path)
    settings = config["uci_pilot"]
    openings = load_opening_suite(settings["opening_suite"])
    if len(openings) != 20 or int(settings["games_per_opening"]) != 2:
        raise ValueError("Opening/game count does not match uci-playing-pilot-v1")
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    seed = int(config["seed"])
    set_deterministic_seed(seed)
    matches = {}
    all_games = []
    pgns = []
    for opponent_index, opponent in enumerate(settings["opponents"]):
        opponent_games = []
        for opening in openings:
            for candidate_color in (chess.WHITE, chess.BLACK):
                record, pgn = play_uci_game(
                    opening,
                    opponent,
                    candidate_color,
                    path,
                    settings,
                )
                opponent_games.append(record)
                all_games.append(record)
                pgns.append(pgn)
        matches[opponent["name"]] = summarize_match(
            opponent_games,
            repeats=int(settings["bootstrap_repeats"]),
            seed=seed + opponent_index,
        )
    faults = {
        "illegal_moves": sum(match["candidate_illegal_moves"] for match in matches.values()),
        "timeouts": sum(match["candidate_timeouts"] for match in matches.values()),
        "engine_errors": sum(match["candidate_engine_errors"] for match in matches.values()),
    }
    decision = {"protocol_gate_passes": not any(faults.values())}
    experiment_name = settings.get("experiment_name", "uci-playing-pilot")
    experiment_id = _next_experiment_id(Path(results_dir), experiment_name)
    artifact = Path(results_dir) / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    runtime = time.perf_counter() - started
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "git_commit": _git_commit(),
        "candidate": settings["candidate"],
        "opening_suite": settings["opening_suite"],
        "openings": len(openings),
        "games": len(all_games),
        "bootstrap_repeats": int(settings["bootstrap_repeats"]),
        "matches": matches,
        "candidate_faults": faults,
        "decision": decision,
        "runtime_seconds": runtime,
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
