from __future__ import annotations

import hashlib
import json
import platform
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.engine
import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .config import write_json
from .frozen_policy import frozen_formula
from .human_corpus import sha256_file
from .ingest import position_hash
from .march import PIECE_VALUES, forcing_moves
from .model import _git_commit, _next_experiment_id
from .oracle import normalize_score
from .search_frontier import frontier_moves

ROOT_SCHEMA_VERSION = "ordinary-root-record-v1"
BRANCH_SCHEMA_VERSION = "ordinary-branch-record-v1"
LABEL_VERSION = "ordinary-branch-foundation-v1"


def _digest_lines(values: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(values).encode()).hexdigest()


def _sample_rank(key: str) -> bytes:
    return hashlib.sha256(f"stability:{key}".encode()).digest()


def _source_settings(config: dict) -> dict:
    if "ordinary_branch_foundation" not in config:
        raise ValueError("The active configuration has no ordinary_branch_foundation section")
    return config["ordinary_branch_foundation"]


def load_ordinary_source(config: dict) -> tuple[list[dict], dict]:
    settings = _source_settings(config)
    path = Path(settings["source_positions"])
    if not path.exists():
        raise FileNotFoundError(path)
    if path.stat().st_size != int(settings["source_positions_bytes"]):
        raise RuntimeError("Ordinary branch source byte count differs from the frozen protocol")
    digest = sha256_file(path)
    if digest != settings["source_positions_sha256"]:
        raise RuntimeError("Ordinary branch source checksum differs from the frozen protocol")
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise RuntimeError("Ordinary branch source must be a JSON list")
    records = sorted(records, key=lambda row: row["position_hash"])
    if len(records) != int(settings["expected_positions"]):
        raise RuntimeError("Ordinary branch source position count changed")

    seen: set[str] = set()
    parent_keys: list[str] = []
    candidate_contexts = 0
    nonterminal_parents = 0
    terminal_candidates = 0
    reply_records = 0
    for record in records:
        board = chess.Board(record["fen"])
        digest = position_hash(board.fen())
        if digest != record["position_hash"]:
            raise RuntimeError(f"Source position hash mismatch: {record['position_hash']}")
        if digest in seen:
            raise RuntimeError(f"Duplicate ordinary branch source position: {digest}")
        seen.add(digest)
        if not board.is_valid() or board.is_game_over(claim_draw=False):
            raise RuntimeError(f"Invalid or terminal ordinary branch source: {board.fen()}")
        expected_color = "white" if board.turn else "black"
        if record["candidate_color"] != expected_color:
            raise RuntimeError(f"Candidate color mismatch for {digest}")
        for move in board.legal_moves:
            candidate_contexts += 1
            board.push(move)
            parent_hash = position_hash(board.fen())
            if board.is_game_over(claim_draw=False):
                terminal_candidates += 1
            else:
                nonterminal_parents += 1
                reply_records += board.legal_moves.count()
                parent_keys.append(f"parent:{parent_hash}")
            board.pop()

    source_games = sorted({record["source_game_key"] for record in records})
    pair_groups = sorted({record["pair_key"] for record in records})
    root_keys = [f"root:{record['position_hash']}" for record in records]
    stable = settings["stability_audit"]
    stable_roots = sorted(root_keys, key=_sample_rank)[: int(stable["root_contexts"])]
    stable_parents = sorted(parent_keys, key=_sample_rank)[: int(stable["parent_contexts"])]
    audit = {
        "source_path": str(path),
        "source_bytes": path.stat().st_size,
        "source_sha256": settings["source_positions_sha256"],
        "positions": len(records),
        "source_games": len(source_games),
        "pair_groups": len(pair_groups),
        "candidate_contexts": candidate_contexts,
        "nonterminal_parent_contexts": nonterminal_parents,
        "terminal_candidates": terminal_candidates,
        "opponent_reply_records": reply_records,
        "position_hash_digest": _digest_lines(sorted(seen)),
        "source_game_key_digest": _digest_lines(source_games),
        "parent_key_digest": _digest_lines(sorted(parent_keys)),
        "stability_root_sample_digest": _digest_lines(stable_roots),
        "stability_parent_sample_digest": _digest_lines(stable_parents),
        "outcomes_probed": 0,
    }
    expected = {
        "positions": int(settings["expected_positions"]),
        "source_games": int(settings["expected_source_games"]),
        "pair_groups": int(settings["expected_pair_groups"]),
        "candidate_contexts": int(settings["expected_candidate_contexts"]),
        "nonterminal_parent_contexts": int(
            settings["expected_nonterminal_parent_contexts"]
        ),
        "terminal_candidates": int(settings["expected_terminal_candidates"]),
        "opponent_reply_records": int(settings["expected_opponent_reply_records"]),
        "position_hash_digest": settings["source_position_hash_digest"],
        "source_game_key_digest": settings["source_game_key_digest"],
        "parent_key_digest": settings["parent_key_digest"],
        "stability_root_sample_digest": stable["root_sample_digest"],
        "stability_parent_sample_digest": stable["parent_sample_digest"],
    }
    actual = {key: audit[key] for key in expected}
    if actual != expected:
        raise RuntimeError(f"Ordinary branch source audit changed: {actual}")
    return records, audit


def audit_ordinary_branch_source(config: dict) -> dict:
    _, audit = load_ordinary_source(config)
    return audit


def _context_boards(records: list[dict]) -> dict[str, dict]:
    contexts: dict[str, dict] = {}
    for record in records:
        board = chess.Board(record["fen"])
        root_key = f"root:{record['position_hash']}"
        contexts[root_key] = {
            "kind": "root",
            "fen": board.fen(),
            "source_root_hash": record["position_hash"],
        }
        for move in board.legal_moves:
            board.push(move)
            if not board.is_game_over(claim_draw=False):
                parent_hash = position_hash(board.fen())
                contexts[f"parent:{parent_hash}"] = {
                    "kind": "parent",
                    "fen": board.fen(),
                    "source_root_hash": record["position_hash"],
                    "root_candidate_uci": move.uci(),
                }
            board.pop()
    return contexts


def _oracle_configuration(engine: chess.engine.SimpleEngine, settings: dict) -> tuple[str, dict]:
    oracle = settings["oracle"]
    engine_name = engine.id.get("name", "unknown")
    engine_author = engine.id.get("author", "unknown")
    if not engine_name.startswith(str(oracle["engine"])):
        raise RuntimeError(
            f"Frozen ordinary oracle requires {oracle['engine']}, found {engine_name}"
        )
    parameters = {"Threads": int(oracle["threads"]), "Hash": int(oracle["hash_mb"])}
    configurable = {name: value for name, value in parameters.items() if name in engine.options}
    if configurable:
        engine.configure(configurable)
    if "UCI_ShowWDL" in engine.options:
        engine.configure({"UCI_ShowWDL": True})
    identity = {
        "engine": f"{engine_name} ({engine_author})",
        "limit_type": oracle["limit_type"],
        "limit_value": int(oracle["limit_value"]),
        "multipv": oracle["multipv"],
        "mate_score_cp": int(oracle["mate_score_cp"]),
        "parameters": parameters,
        "new_game_per_context": bool(oracle["new_game_per_context"]),
        "stability_limit_value": int(settings["stability_audit"]["limit_value"]),
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    return key, identity


def _load_oracle_cache(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    entries: dict[str, dict] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            key = record["cache_key"]
            if key in entries:
                raise RuntimeError(f"Duplicate ordinary oracle cache key on line {line_number}")
            entries[key] = record
    return entries


def _analyse_all_legal(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    *,
    nodes: int,
    mate_score_cp: int,
    game_key: str,
) -> dict:
    legal = sorted(board.legal_moves, key=lambda move: move.uci())
    if not legal:
        raise ValueError("Cannot run all-legal analysis on a terminal context")
    started = time.perf_counter()
    infos = engine.analyse(
        board,
        chess.engine.Limit(nodes=nodes),
        multipv=len(legal),
        game=game_key,
    )
    if isinstance(infos, dict):
        infos = [infos]
    moves = []
    seen = set()
    for info in infos:
        pv = info.get("pv", [])
        if not pv:
            raise RuntimeError(f"Oracle returned an empty PV for {game_key}")
        move_uci = pv[0].uci()
        if move_uci in seen:
            raise RuntimeError(f"Oracle returned duplicate move {move_uci} for {game_key}")
        seen.add(move_uci)
        score, mate = normalize_score(info["score"], mate_score_cp)
        moves.append(
            {
                "move_uci": move_uci,
                "eval_cp": score,
                "mate": mate,
                "depth": info.get("depth"),
                "seldepth": info.get("seldepth"),
                "nodes": info.get("nodes"),
            }
        )
    expected = {move.uci() for move in legal}
    if seen != expected:
        missing = sorted(expected - seen)
        raise RuntimeError(f"Incomplete all-legal oracle response for {game_key}: {missing}")
    return {
        "fen": board.fen(),
        "side_to_move": "white" if board.turn else "black",
        "legal_moves": len(legal),
        "limit_nodes": nodes,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
        "moves": sorted(moves, key=lambda row: row["move_uci"]),
    }


def populate_ordinary_oracle_cache(
    records: list[dict], stockfish_path: str | Path, config: dict
) -> tuple[dict[str, dict], dict]:
    settings = _source_settings(config)
    path = Path(stockfish_path)
    if not path.exists():
        raise FileNotFoundError(path)
    contexts = _context_boards(records)
    cache_path = Path(settings["oracle_cache"])
    metadata_path = Path(settings["oracle_cache_metadata"])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    entries = _load_oracle_cache(cache_path)
    engine = chess.engine.SimpleEngine.popen_uci(str(path))
    started = time.perf_counter()
    new_base = 0
    new_stability = 0
    try:
        oracle_key, identity = _oracle_configuration(engine, settings)
        metadata = {
            "oracle_key": oracle_key,
            "identity": identity,
            "protocol_version": settings["protocol_version"],
            "source_positions_sha256": settings["source_positions_sha256"],
        }
        if metadata_path.exists():
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            if existing != metadata:
                raise RuntimeError("Ordinary branch oracle cache metadata differs")
        else:
            write_json(metadata_path, metadata)
        for record in entries.values():
            if record["oracle_key"] != oracle_key:
                raise RuntimeError("Ordinary branch oracle cache identity differs")

        base_nodes = int(settings["oracle"]["limit_value"])
        mate_score = int(settings["oracle"]["mate_score_cp"])
        stable = settings["stability_audit"]
        root_keys = sorted(key for key in contexts if key.startswith("root:"))
        parent_keys = sorted(key for key in contexts if key.startswith("parent:"))
        stable_keys = {
            *sorted(root_keys, key=_sample_rank)[: int(stable["root_contexts"])],
            *sorted(parent_keys, key=_sample_rank)[: int(stable["parent_contexts"])],
        }
        requests = [("base", key, base_nodes) for key in sorted(contexts)]
        requests.extend(
            ("stability", key, int(stable["limit_value"])) for key in sorted(stable_keys)
        )
        with cache_path.open("a", encoding="utf-8") as output:
            for tier, context_key, nodes in requests:
                cache_key = f"{tier}:{context_key}"
                if cache_key in entries:
                    continue
                context = contexts[context_key]
                board = chess.Board(context["fen"])
                analysis = _analyse_all_legal(
                    engine,
                    board,
                    nodes=nodes,
                    mate_score_cp=mate_score,
                    game_key=cache_key,
                )
                result = {
                    "cache_key": cache_key,
                    "context_key": context_key,
                    "context_kind": context["kind"],
                    "oracle_key": oracle_key,
                    **analysis,
                }
                output.write(json.dumps(result, sort_keys=True) + "\n")
                output.flush()
                entries[cache_key] = result
                if tier == "base":
                    new_base += 1
                else:
                    new_stability += 1
    finally:
        engine.quit()
    expected_base = len(contexts)
    expected_stability = int(settings["stability_audit"]["root_contexts"]) + int(
        settings["stability_audit"]["parent_contexts"]
    )
    base_total = sum(key.startswith("base:") for key in entries)
    stability_total = sum(key.startswith("stability:") for key in entries)
    if base_total != expected_base or stability_total != expected_stability:
        raise RuntimeError("Ordinary branch oracle cache is incomplete")
    return entries, {
        "oracle_key": next(iter(entries.values()))["oracle_key"],
        "base_contexts": base_total,
        "new_base_contexts": new_base,
        "cached_base_contexts": base_total - new_base,
        "stability_contexts": stability_total,
        "new_stability_contexts": new_stability,
        "cached_stability_contexts": stability_total - new_stability,
        "runtime_seconds": time.perf_counter() - started,
    }


def _clipped(value: int | float, clip: float) -> float:
    return float(np.clip(value, -clip, clip))


def _select_move(values: dict[str, float], turn: chess.Color) -> str:
    if not values:
        raise ValueError("Cannot select from an empty move-value mapping")
    return min(
        values,
        key=lambda move: ((-values[move]) if turn else values[move], move),
    )


def _mover_regret(best: float, value: float, turn: chess.Color) -> float:
    raw = best - value if turn else value - best
    return max(0.0, raw)


def _terminal_eval(board: chess.Board, clip: float) -> float:
    outcome = board.outcome(claim_draw=False)
    if outcome is None:
        raise ValueError("Terminal evaluation requested for a nonterminal board")
    if outcome.winner is chess.WHITE:
        return clip
    if outcome.winner is chess.BLACK:
        return -clip
    return 0.0


def _tactical_key(board: chess.Board, move: chess.Move) -> tuple[int, int, int, float, str]:
    captured = board.piece_at(move.to_square)
    captured_value = PIECE_VALUES[captured.piece_type] if captured else 0.0
    return (
        -int(board.gives_check(move)),
        -int(move.promotion is not None),
        -int(board.is_capture(move)),
        -captured_value,
        move.uci(),
    )


def ordinary_baseline_ordering(
    board: chess.Board,
    reply_scores: dict[str, float],
    baseline: str,
    *,
    seed: int,
    repeat: int = 0,
    parent_hash: str | None = None,
) -> list[str]:
    legal = sorted(board.legal_moves, key=lambda move: move.uci())
    if set(reply_scores) != {move.uci() for move in legal}:
        raise RuntimeError("Reply scores do not cover the complete legal move set")
    if baseline == "random":
        identity = parent_hash or position_hash(board.fen())
        ordered = sorted(
            legal,
            key=lambda move: (
                hashlib.sha256(
                    f"{seed}:{repeat}:{identity}:{move.uci()}".encode()
                ).digest(),
                move.uci(),
            ),
        )
        return [move.uci() for move in ordered]
    if baseline in {"forcing", "all-captures"}:
        priority = (
            forcing_moves(board)
            if baseline == "forcing"
            else frontier_moves(board, "all-captures")
        )
        present = set(priority)
        ordered = priority + [move for move in legal if move not in present]
        return [move.uci() for move in ordered]
    if baseline == "locked-3":
        formula = frozen_formula("locked-3")
        scored = []
        turn = board.turn
        for move in legal:
            board.push(move)
            score = formula.evaluate(board)
            board.pop()
            scored.append((move, score))
        scored.sort(key=lambda item: ((-item[1]) if turn else item[1], item[0].uci()))
        return [move.uci() for move, _ in scored]
    if baseline == "oracle":
        return sorted(
            reply_scores,
            key=lambda move: (
                (-reply_scores[move]) if board.turn else reply_scores[move],
                move,
            ),
        )
    raise ValueError(f"Unknown ordinary branch baseline: {baseline}")


def _threshold_labels(regret: float, thresholds: list[int]) -> dict[str, bool]:
    return {f"within_{threshold}cp": regret <= threshold for threshold in thresholds}


def _top_labels(rank: int) -> dict[str, bool]:
    return {"top_1": rank <= 1, "top_3": rank <= 3, "top_5": rank <= 5}


def prepare_ordinary_roots(
    records: list[dict], entries: dict[str, dict], config: dict
) -> list[dict]:
    settings = _source_settings(config)
    clip = float(settings["oracle"]["score_clip_cp"])
    thresholds = [int(value) for value in settings["regret_thresholds_cp"]]
    roots = []
    for source in records:
        board = chess.Board(source["fen"])
        root_turn = board.turn
        root_hash = source["position_hash"]
        root_analysis = entries[f"base:root:{root_hash}"]
        direct_raw = {
            row["move_uci"]: row for row in root_analysis["moves"]
        }
        direct_scores = {
            move: _clipped(row["eval_cp"], clip) for move, row in direct_raw.items()
        }
        direct_order = sorted(
            direct_scores,
            key=lambda move: (
                (-direct_scores[move]) if root_turn else direct_scores[move],
                move,
            ),
        )
        direct_best = direct_scores[direct_order[0]]
        direct_ranks = {move: rank for rank, move in enumerate(direct_order, start=1)}
        forcing_root = {move.uci() for move in forcing_moves(board)}
        capture_root = {move.uci() for move in frontier_moves(board, "all-captures")}
        candidates = []
        for move in sorted(board.legal_moves, key=lambda candidate: candidate.uci()):
            move_uci = move.uci()
            board.push(move)
            parent_fen = board.fen()
            parent_hash = position_hash(parent_fen)
            terminal = board.is_game_over(claim_draw=False)
            replies = []
            natural_forcing: set[str] = set()
            natural_captures: set[str] = set()
            if terminal:
                search_value = _terminal_eval(board, clip)
            else:
                parent_analysis = entries[f"base:parent:{parent_hash}"]
                reply_raw = {
                    row["move_uci"]: row for row in parent_analysis["moves"]
                }
                reply_scores = {
                    reply: _clipped(row["eval_cp"], clip)
                    for reply, row in reply_raw.items()
                }
                opponent_order = sorted(
                    reply_scores,
                    key=lambda reply: (
                        (-reply_scores[reply]) if board.turn else reply_scores[reply],
                        reply,
                    ),
                )
                best_reply_score = reply_scores[opponent_order[0]]
                opponent_ranks = {
                    reply: rank for rank, reply in enumerate(opponent_order, start=1)
                }
                natural_forcing = {reply.uci() for reply in forcing_moves(board)}
                natural_captures = {
                    reply.uci() for reply in frontier_moves(board, "all-captures")
                }
                for reply_move in sorted(
                    board.legal_moves, key=lambda candidate: candidate.uci()
                ):
                    reply_uci = reply_move.uci()
                    opponent_regret = _mover_regret(
                        best_reply_score, reply_scores[reply_uci], board.turn
                    )
                    board.push(reply_move)
                    reply_successor_fen = board.fen()
                    board.pop()
                    replies.append(
                        {
                            "move_uci": reply_uci,
                            "successor_fen": reply_successor_fen,
                            "eval_cp": reply_scores[reply_uci],
                            "eval_cp_raw": int(reply_raw[reply_uci]["eval_cp"]),
                            "mate": reply_raw[reply_uci]["mate"],
                            "rank": opponent_ranks[reply_uci],
                            "regret_cp": opponent_regret,
                            "top_k_labels": _top_labels(opponent_ranks[reply_uci]),
                            "regret_threshold_labels": _threshold_labels(
                                opponent_regret, thresholds
                            ),
                            "forcing_eligible": reply_uci in natural_forcing,
                            "capture_eligible": reply_uci in natural_captures,
                        }
                    )
                search_value = best_reply_score
            board.pop()
            direct_regret = _mover_regret(
                direct_best, direct_scores[move_uci], root_turn
            )
            candidates.append(
                {
                    "move_uci": move_uci,
                    "parent_fen": parent_fen,
                    "parent_hash": parent_hash,
                    "terminal": terminal,
                    "search_value": search_value,
                    "direct_eval_cp": direct_scores[move_uci],
                    "direct_eval_cp_raw": int(direct_raw[move_uci]["eval_cp"]),
                    "direct_mate": direct_raw[move_uci]["mate"],
                    "direct_rank": direct_ranks[move_uci],
                    "direct_regret_cp": direct_regret,
                    "top_k_labels": _top_labels(direct_ranks[move_uci]),
                    "regret_threshold_labels": _threshold_labels(
                        direct_regret, thresholds
                    ),
                    "forcing_eligible": move_uci in forcing_root,
                    "capture_eligible": move_uci in capture_root,
                    "replies": replies,
                    "natural_forcing": natural_forcing,
                    "natural_captures": natural_captures,
                }
            )

        search_values = {
            candidate["move_uci"]: candidate["search_value"] for candidate in candidates
        }
        all_reply_choice = _select_move(search_values, root_turn)
        direct_choice = direct_order[0]
        all_reply_absolute_regret = _mover_regret(
            direct_best, direct_scores[all_reply_choice], root_turn
        )
        candidate_by_move = {candidate["move_uci"]: candidate for candidate in candidates}
        for candidate in candidates:
            replies = candidate["replies"]
            if not replies:
                continue
            for reply in replies:
                remaining = {
                    row["move_uci"]: row["eval_cp"]
                    for row in replies
                    if row["move_uci"] != reply["move_uci"]
                }
                forced = not remaining
                if forced:
                    candidate_value_without = None
                    omission_gain = None
                    omission_choice = None
                    raw_root_loss = None
                    root_loss = None
                else:
                    candidate_value_without = remaining[
                        _select_move(remaining, not root_turn)
                    ]
                    raw_gain = (
                        candidate_value_without - candidate["search_value"]
                        if root_turn
                        else candidate["search_value"] - candidate_value_without
                    )
                    omission_gain = max(0.0, raw_gain)
                    omission_values = dict(search_values)
                    omission_values[candidate["move_uci"]] = candidate_value_without
                    omission_choice = _select_move(omission_values, root_turn)
                    omission_regret = _mover_regret(
                        direct_best, direct_scores[omission_choice], root_turn
                    )
                    raw_root_loss = omission_regret - all_reply_absolute_regret
                    root_loss = max(0.0, raw_root_loss)
                reply["refutation"] = {
                    "forced_reply": forced,
                    "candidate_value_without_reply_cp": candidate_value_without,
                    "candidate_omission_gain_cp": omission_gain,
                    "candidate_critical": {
                        f"over_{threshold}cp": forced
                        or bool(omission_gain is not None and omission_gain > threshold)
                        for threshold in thresholds
                    },
                }
                reply["root_consequence"] = {
                    "omission_defined": not forced,
                    "omission_choice_uci": omission_choice,
                    "changes_all_reply_choice": (
                        None if forced else omission_choice != all_reply_choice
                    ),
                    "raw_pruning_loss_cp": raw_root_loss,
                    "pruning_loss_cp": root_loss,
                    "root_critical": {
                        f"over_{threshold}cp": bool(
                            root_loss is not None and root_loss > threshold
                        )
                        for threshold in thresholds
                    },
                }

        roots.append(
            {
                "source": source,
                "turn": root_turn,
                "direct_scores": direct_scores,
                "direct_best_score": direct_best,
                "direct_choice": direct_choice,
                "all_reply_choice": all_reply_choice,
                "all_reply_absolute_regret_cp": all_reply_absolute_regret,
                "candidate_by_move": candidate_by_move,
                "candidates": candidates,
            }
        )
    return roots


def _random_ordering(candidate: dict, seed: int, repeat: int) -> list[str]:
    scores = {reply["move_uci"]: reply["eval_cp"] for reply in candidate["replies"]}
    board = chess.Board(candidate["parent_fen"])
    return ordinary_baseline_ordering(
        board,
        scores,
        "random",
        seed=seed,
        repeat=repeat,
        parent_hash=candidate["parent_hash"],
    )


def _retention_threshold(points: list[dict], threshold: float) -> float | None:
    for index, point in enumerate(points):
        if all(later["decision_preservation_25cp"] >= threshold for later in points[index:]):
            return float(point["retained_fraction"])
    return None


def measure_ordinary_branch_curves(roots: list[dict], config: dict) -> dict:
    settings = _source_settings(config)
    budgets = settings["branch_budgets"]
    seed = int(config["seed"])
    threshold = float(settings["decision_preservation_threshold_cp"])
    results = {}
    for baseline in settings["baseline_orderings"]:
        started = time.perf_counter()
        repeats = int(settings["random_repeats"]) if baseline == "random" else 1
        accumulators = {
            str(budget): {
                "positions": 0,
                "contexts": 0,
                "legal": 0,
                "retained": 0,
                "preserved": 0,
                "same_choice": 0,
                "loss_sum": 0.0,
                "full_abs_regret_sum": 0.0,
                "pruned_abs_regret_sum": 0.0,
                "catastrophic_100": 0,
                "catastrophic_300": 0,
                "candidate_critical_total": 0,
                "candidate_critical_retained": 0,
                "root_critical_total": 0,
                "root_critical_retained": 0,
                "all_candidate_critical": 0,
                "oracle_inversions": 0,
            }
            for budget in budgets
        }
        natural = {
            "legal": 0,
            "retained": 0,
            "candidate_critical_total": 0,
            "candidate_critical_retained": 0,
            "root_critical_total": 0,
            "root_critical_retained": 0,
            "zero_reply_contexts": 0,
            "contexts": 0,
        }
        selector_operations = 0
        ordering_seconds = 0.0
        for repeat in range(repeats):
            for root in roots:
                turn = root["turn"]
                full_choice = root["all_reply_choice"]
                full_regret = root["all_reply_absolute_regret_cp"]
                best_direct = root["direct_best_score"]
                root_orderings = {}
                for candidate in root["candidates"]:
                    if not candidate["replies"]:
                        continue
                    ordering_started = time.perf_counter()
                    if baseline == "random":
                        ordering = _random_ordering(candidate, seed, repeat)
                    elif baseline in candidate.get("orderings", {}):
                        ordering = candidate["orderings"][baseline]
                    else:
                        reply_scores = {
                            reply["move_uci"]: reply["eval_cp"]
                            for reply in candidate["replies"]
                        }
                        ordering = ordinary_baseline_ordering(
                            chess.Board(candidate["parent_fen"]),
                            reply_scores,
                            baseline,
                            seed=seed,
                            repeat=repeat,
                            parent_hash=candidate["parent_hash"],
                        )
                    ordering_seconds += time.perf_counter() - ordering_started
                    root_orderings[candidate["move_uci"]] = ordering
                    selector_operations += len(ordering)
                for budget in budgets:
                    approximate_values = {}
                    retained_by_candidate: dict[str, set[str]] = {}
                    legal_total = 0
                    retained_total = 0
                    contexts = 0
                    for candidate in root["candidates"]:
                        move_uci = candidate["move_uci"]
                        replies = candidate["replies"]
                        if not replies:
                            approximate_values[move_uci] = candidate["search_value"]
                            retained_by_candidate[move_uci] = set()
                            continue
                        contexts += 1
                        ordering = root_orderings[move_uci]
                        count = (
                            len(ordering)
                            if budget == "all"
                            else min(int(budget), len(ordering))
                        )
                        retained = set(ordering[:count])
                        retained_by_candidate[move_uci] = retained
                        scores = {
                            reply["move_uci"]: reply["eval_cp"]
                            for reply in replies
                            if reply["move_uci"] in retained
                        }
                        chosen_reply = _select_move(scores, not turn)
                        approximate_values[move_uci] = scores[chosen_reply]
                        legal_total += len(ordering)
                        retained_total += count
                    selected = _select_move(approximate_values, turn)
                    pruned_regret = _mover_regret(
                        best_direct, root["direct_scores"][selected], turn
                    )
                    raw_loss = pruned_regret - full_regret
                    loss = max(0.0, raw_loss)
                    accumulator = accumulators[str(budget)]
                    accumulator["positions"] += 1
                    accumulator["contexts"] += contexts
                    accumulator["legal"] += legal_total
                    accumulator["retained"] += retained_total
                    accumulator["preserved"] += int(loss <= threshold)
                    accumulator["same_choice"] += int(selected == full_choice)
                    accumulator["loss_sum"] += loss
                    accumulator["full_abs_regret_sum"] += full_regret
                    accumulator["pruned_abs_regret_sum"] += pruned_regret
                    accumulator["catastrophic_100"] += int(loss > 100)
                    accumulator["catastrophic_300"] += int(loss > 300)
                    accumulator["oracle_inversions"] += int(raw_loss < 0)
                    all_candidate_critical = True
                    for candidate in root["candidates"]:
                        retained = retained_by_candidate[candidate["move_uci"]]
                        for reply in candidate["replies"]:
                            candidate_critical = reply["refutation"][
                                "candidate_critical"
                            ]["over_25cp"]
                            root_critical = reply["root_consequence"]["root_critical"][
                                "over_25cp"
                            ]
                            if candidate_critical:
                                accumulator["candidate_critical_total"] += 1
                                kept = reply["move_uci"] in retained
                                accumulator["candidate_critical_retained"] += int(kept)
                                all_candidate_critical &= kept
                            if root_critical:
                                accumulator["root_critical_total"] += 1
                                accumulator["root_critical_retained"] += int(
                                    reply["move_uci"] in retained
                                )
                    accumulator["all_candidate_critical"] += int(all_candidate_critical)

                if baseline in {"forcing", "all-captures"}:
                    for candidate in root["candidates"]:
                        replies = candidate["replies"]
                        if not replies:
                            continue
                        field = (
                            "forcing_eligible"
                            if baseline == "forcing"
                            else "capture_eligible"
                        )
                        natural["contexts"] += 1
                        natural["legal"] += len(replies)
                        retained = {reply["move_uci"] for reply in replies if reply[field]}
                        natural["retained"] += len(retained)
                        natural["zero_reply_contexts"] += int(not retained)
                        for reply in replies:
                            if reply["refutation"]["candidate_critical"]["over_25cp"]:
                                natural["candidate_critical_total"] += 1
                                natural["candidate_critical_retained"] += int(
                                    reply["move_uci"] in retained
                                )
                            if reply["root_consequence"]["root_critical"]["over_25cp"]:
                                natural["root_critical_total"] += 1
                                natural["root_critical_retained"] += int(
                                    reply["move_uci"] in retained
                                )
        points = []
        for budget in budgets:
            accumulator = accumulators[str(budget)]
            positions = accumulator["positions"]
            candidate_total = accumulator["candidate_critical_total"]
            root_total = accumulator["root_critical_total"]
            points.append(
                {
                    "budget": budget,
                    "positions": positions,
                    "mean_legal_replies_per_context": accumulator["legal"]
                    / accumulator["contexts"],
                    "mean_retained_replies_per_context": accumulator["retained"]
                    / accumulator["contexts"],
                    "retained_fraction": accumulator["retained"] / accumulator["legal"],
                    "decision_preservation_25cp": accumulator["preserved"] / positions,
                    "exact_all_reply_choice_agreement": accumulator["same_choice"]
                    / positions,
                    "mean_pruning_loss_cp": accumulator["loss_sum"] / positions,
                    "mean_full_reference_absolute_regret_cp": accumulator[
                        "full_abs_regret_sum"
                    ]
                    / positions,
                    "mean_pruned_absolute_regret_cp": accumulator[
                        "pruned_abs_regret_sum"
                    ]
                    / positions,
                    "catastrophic_omission_rate_100cp": accumulator[
                        "catastrophic_100"
                    ]
                    / positions,
                    "catastrophic_omission_rate_300cp": accumulator[
                        "catastrophic_300"
                    ]
                    / positions,
                    "candidate_refutation_recall_25cp": (
                        accumulator["candidate_critical_retained"] / candidate_total
                        if candidate_total
                        else 1.0
                    ),
                    "root_critical_recall_25cp": (
                        accumulator["root_critical_retained"] / root_total
                        if root_total
                        else 1.0
                    ),
                    "all_candidate_refutations_preserved_rate": accumulator[
                        "all_candidate_critical"
                    ]
                    / positions,
                    "oracle_inversion_rate": accumulator["oracle_inversions"] / positions,
                }
            )
        if points[-1]["decision_preservation_25cp"] != 1.0 or points[-1][
            "exact_all_reply_choice_agreement"
        ] != 1.0:
            raise RuntimeError(f"All-legal ordinary endpoint failed for {baseline}")
        if baseline == "oracle" and points[0]["exact_all_reply_choice_agreement"] != 1.0:
            raise RuntimeError("Oracle budget-one ordering failed to preserve all-reply choice")
        natural_metrics = None
        if natural["contexts"]:
            natural_metrics = {
                "contexts": natural["contexts"],
                "zero_reply_context_rate": natural["zero_reply_contexts"]
                / natural["contexts"],
                "retained_fraction": natural["retained"] / natural["legal"],
                "candidate_refutation_recall_25cp": (
                    natural["candidate_critical_retained"]
                    / natural["candidate_critical_total"]
                    if natural["candidate_critical_total"]
                    else 1.0
                ),
                "root_critical_recall_25cp": (
                    natural["root_critical_retained"] / natural["root_critical_total"]
                    if natural["root_critical_total"]
                    else 1.0
                ),
            }
        results[baseline] = {
            "points": points,
            "rho_95": _retention_threshold(points, 0.95),
            "random_repeats": repeats,
            "selector_operations": selector_operations,
            "selector_runtime_seconds": ordering_seconds,
            "curve_runtime_seconds": time.perf_counter() - started,
            "natural_category_metrics": natural_metrics,
        }
    return results


def ordinary_oracle_stability(entries: dict[str, dict], config: dict) -> dict:
    settings = _source_settings(config)
    clip = float(settings["oracle"]["score_clip_cp"])
    by_kind = {}
    for kind in ("root", "parent"):
        selected = sorted(
            record["context_key"]
            for key, record in entries.items()
            if key.startswith("stability:") and record["context_kind"] == kind
        )
        top_agreement = []
        move_errors = []
        jaccards = []
        for context_key in selected:
            base = entries[f"base:{context_key}"]
            stable = entries[f"stability:{context_key}"]
            board = chess.Board(base["fen"])
            base_scores = {
                row["move_uci"]: _clipped(row["eval_cp"], clip) for row in base["moves"]
            }
            stable_scores = {
                row["move_uci"]: _clipped(row["eval_cp"], clip)
                for row in stable["moves"]
            }
            if set(base_scores) != set(stable_scores):
                raise RuntimeError(f"Stability legal move set changed for {context_key}")
            base_best_move = _select_move(base_scores, board.turn)
            stable_best_move = _select_move(stable_scores, board.turn)
            top_agreement.append(base_best_move == stable_best_move)
            move_errors.extend(
                abs(base_scores[move] - stable_scores[move]) for move in base_scores
            )
            base_best = base_scores[base_best_move]
            stable_best = stable_scores[stable_best_move]
            base_near = {
                move
                for move, score in base_scores.items()
                if _mover_regret(base_best, score, board.turn) <= 25
            }
            stable_near = {
                move
                for move, score in stable_scores.items()
                if _mover_regret(stable_best, score, board.turn) <= 25
            }
            jaccards.append(len(base_near & stable_near) / len(base_near | stable_near))
        by_kind[kind] = {
            "contexts": len(selected),
            "top_move_agreement": float(np.mean(top_agreement)),
            "mean_common_move_score_difference_cp": float(np.mean(move_errors)),
            "median_common_move_score_difference_cp": float(np.median(move_errors)),
            "mean_within_25cp_set_jaccard": float(np.mean(jaccards)),
        }
    return by_kind


def _oracle_metadata(oracle_key: str, settings: dict) -> dict:
    return {
        "kind": "uci-engine",
        "identity": oracle_key,
        "configuration": settings["oracle"],
    }


def _root_output_record(root: dict) -> dict:
    source = root["source"]
    return {
        "schema_version": ROOT_SCHEMA_VERSION,
        "position_hash": source["position_hash"],
        "fen": source["fen"],
        "source_game": source["source_game_key"],
        "pair_group": source["pair_key"],
        "source_ply": source["ply"],
        "opening_id": source["opening_id"],
        "opponent": source["opponent"],
        "partition": "development",
        "side_to_move": "white" if root["turn"] else "black",
        "legal_root_moves": len(root["candidates"]),
        "all_reply_reference_move": root["all_reply_choice"],
        "direct_oracle_move": root["direct_choice"],
        "all_reply_reference_absolute_regret_cp": root[
            "all_reply_absolute_regret_cp"
        ],
    }


def _branch_output_records(root: dict, oracle_key: str, settings: dict) -> Iterable[dict]:
    source = root["source"]
    side = "white" if root["turn"] else "black"
    oracle = _oracle_metadata(oracle_key, settings)
    for candidate in root["candidates"]:
        move_uci = candidate["move_uci"]
        yield {
            "schema_version": BRANCH_SCHEMA_VERSION,
            "source_state_hash": source["position_hash"],
            "source_root_hash": source["position_hash"],
            "source_fen": source["fen"],
            "successor_fen": candidate["parent_fen"],
            "move_uci": move_uci,
            "side_to_move": side,
            "source_game": source["source_game_key"],
            "source_ply": source["ply"],
            "pair_group": source["pair_key"],
            "partition": "development",
            "root_candidate_uci": move_uci,
            "node_role": "root-candidate",
            "path_moves": [],
            "remaining_depth": 2,
            "branch_budget": "all",
            "move_rank": candidate["direct_rank"],
            "regret_cp": candidate["direct_regret_cp"],
            "top_k_labels": candidate["top_k_labels"],
            "regret_threshold_labels": candidate["regret_threshold_labels"],
            "root_decision_consequence": {
                "direct_oracle_eval_cp": candidate["direct_eval_cp"],
                "all_reply_candidate_eval_cp": candidate["search_value"],
                "selected_by_all_reply_reference": move_uci == root["all_reply_choice"],
                "selected_by_direct_oracle": move_uci == root["direct_choice"],
            },
            "refutation_necessity": None,
            "value_of_information": None,
            "label_definition_version": LABEL_VERSION,
            "representation_version": None,
            "forcing_eligible": candidate["forcing_eligible"],
            "capture_eligible": candidate["capture_eligible"],
            "terminal_successor": candidate["terminal"],
            "oracle_eval_cp_raw": candidate["direct_eval_cp_raw"],
            "oracle_mate": candidate["direct_mate"],
            "oracle": oracle,
        }
        opponent_side = "black" if root["turn"] else "white"
        for reply in candidate["replies"]:
            yield {
                "schema_version": BRANCH_SCHEMA_VERSION,
                "source_state_hash": candidate["parent_hash"],
                "source_root_hash": source["position_hash"],
                "source_fen": candidate["parent_fen"],
                "successor_fen": reply["successor_fen"],
                "move_uci": reply["move_uci"],
                "side_to_move": opponent_side,
                "source_game": source["source_game_key"],
                "source_ply": source["ply"],
                "pair_group": source["pair_key"],
                "partition": "development",
                "root_candidate_uci": move_uci,
                "node_role": "opponent-reply",
                "path_moves": [move_uci],
                "remaining_depth": 1,
                "branch_budget": "all",
                "move_rank": reply["rank"],
                "regret_cp": reply["regret_cp"],
                "top_k_labels": reply["top_k_labels"],
                "regret_threshold_labels": reply["regret_threshold_labels"],
                "root_decision_consequence": reply["root_consequence"],
                "refutation_necessity": reply["refutation"],
                "value_of_information": reply["refutation"][
                    "candidate_omission_gain_cp"
                ],
                "label_definition_version": LABEL_VERSION,
                "representation_version": None,
                "forcing_eligible": reply["forcing_eligible"],
                "capture_eligible": reply["capture_eligible"],
                "oracle_eval_cp": reply["eval_cp"],
                "oracle_eval_cp_raw": reply["eval_cp_raw"],
                "oracle_mate": reply["mate"],
                "oracle": oracle,
            }


def _save_plot(artifact: Path, curves: dict) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for baseline, result in curves.items():
        points = result["points"]
        x_values = [point["retained_fraction"] for point in points]
        axes[0].plot(
            x_values,
            [point["decision_preservation_25cp"] for point in points],
            marker="o",
            label=baseline,
        )
        axes[1].plot(
            x_values,
            [point["candidate_refutation_recall_25cp"] for point in points],
            marker="o",
            label=baseline,
        )
    axes[0].axhline(0.95, color="gray", linestyle="--", linewidth=1)
    axes[0].set_ylabel("Root decisions preserved within 25 cp")
    axes[1].set_ylabel("Candidate-refutation recall (>25 cp)")
    for axis in axes:
        axis.set_xlabel("Fraction of opponent replies retained")
        axis.set_xlim(0, 1.02)
        axis.set_ylim(0, 1.02)
        axis.grid(alpha=0.25)
    axes[0].legend(fontsize=8)
    figure.suptitle("Ordinary development branch-budget curves")
    figure.tight_layout()
    figure.savefig(artifact / "ordinary_branch_budget_curve.png", dpi=160)
    plt.close(figure)


def _report(result: dict) -> str:
    rows = []
    for baseline, curve in result["curves"].items():
        point = curve["points"][0]
        rows.append(
            f"| {baseline} | {point['retained_fraction']:.2%} | "
            f"{point['decision_preservation_25cp']:.2%} | "
            f"{point['candidate_refutation_recall_25cp']:.2%} | "
            f"{point['mean_pruning_loss_cp']:.2f} | {curve['rho_95']:.4f} |"
        )
    return f"""# Ordinary Branch-Law Foundation: {result['experiment_id']}

## Guardrail

This experiment uses 240 development-only source positions, retains every legal
root candidate, and varies opponent-reply information only. It trains no model
and exposes no selection or confirmation outcome.

## Budget-one result

| Ordering | Retained fraction | DPR_25 | Refutation recall | Mean pruning loss | rho_95 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Integrity

- Source positions: {result['source_audit']['positions']}
- Root candidates: {result['source_audit']['candidate_contexts']}
- Opponent replies: {result['source_audit']['opponent_reply_records']}
- Root records emitted: {result['root_records']}
- Branch records emitted: {result['branch_records']}
- Selection outcomes probed: 0
- Confirmation outcomes probed: 0
- Runtime: {result['runtime_seconds']:.2f} seconds
- Git revision: `{result['git_commit']}`

These are development measurement baselines, not a learned branch law or a
confirmation result.
"""


def run_ordinary_branch_foundation(
    stockfish_path: str | Path,
    config: dict,
    *,
    results_dir: str | Path | None = None,
) -> tuple[dict, Path]:
    settings = _source_settings(config)
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    records, source_audit = load_ordinary_source(config)
    entries, oracle_audit = populate_ordinary_oracle_cache(
        records, stockfish_path, config
    )
    roots = prepare_ordinary_roots(records, entries, config)
    curves = measure_ordinary_branch_curves(roots, config)
    stability = ordinary_oracle_stability(entries, config)
    root = Path(results_dir or settings["results_directory"])
    experiment_id = _next_experiment_id(root, settings["experiment_name"])
    artifact = root / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    root_path = artifact / "ordinary_roots.ndjson"
    branch_path = artifact / "ordinary_branch_records.ndjson"
    root_count = 0
    branch_count = 0
    with (
        root_path.open("w", encoding="utf-8") as root_output,
        branch_path.open("w", encoding="utf-8") as branch_output,
    ):
        for root_record in roots:
            root_output.write(json.dumps(_root_output_record(root_record), sort_keys=True) + "\n")
            root_count += 1
            for branch_record in _branch_output_records(
                root_record, oracle_audit["oracle_key"], settings
            ):
                branch_output.write(json.dumps(branch_record, sort_keys=True) + "\n")
                branch_count += 1
    expected_branches = int(settings["expected_candidate_contexts"]) + int(
        settings["expected_opponent_reply_records"]
    )
    if root_count != int(settings["expected_positions"]) or branch_count != expected_branches:
        raise RuntimeError("Ordinary branch artifact record counts changed")
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
        "oracle_stability": stability,
        "curves": curves,
        "root_records": root_count,
        "branch_records": branch_count,
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
    _save_plot(artifact, curves)
    return result, artifact
