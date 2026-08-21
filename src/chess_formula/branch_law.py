from __future__ import annotations

import hashlib
import heapq
import json
import platform
import time
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.syzygy
import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .config import write_json
from .frozen_policy import frozen_formula
from .human_corpus import download_verified, sha256_file
from .march import PIECE_VALUES, forcing_moves
from .model import _git_commit, _next_experiment_id

EXACT_STATE_SCHEMA_VERSION = "exact-state-v1"
BRANCH_RECORD_SCHEMA_VERSION = "branch-record-v1"
LABEL_DEFINITION_VERSION = "branch-law-foundation-v1"

DOMAIN_PIECES = {
    "KQvK": chess.QUEEN,
    "KRvK": chess.ROOK,
    "KPvK": chess.PAWN,
}


def _transform_coordinates(file_index: int, rank_index: int, transform: int) -> tuple[int, int]:
    transforms = (
        (file_index, rank_index),
        (7 - rank_index, file_index),
        (7 - file_index, 7 - rank_index),
        (rank_index, 7 - file_index),
        (7 - file_index, rank_index),
        (file_index, 7 - rank_index),
        (rank_index, file_index),
        (7 - rank_index, 7 - file_index),
    )
    return transforms[transform]


def transform_square(square: chess.Square, transform: int) -> chess.Square:
    if not 0 <= transform < 8:
        raise ValueError(f"Unknown board transform: {transform}")
    file_index, rank_index = _transform_coordinates(
        chess.square_file(square), chess.square_rank(square), transform
    )
    return chess.square(file_index, rank_index)


def symmetry_transforms(domain: str) -> tuple[int, ...]:
    if domain in {"KQvK", "KRvK"}:
        return tuple(range(8))
    if domain == "KPvK":
        return (0, 4)
    raise ValueError(f"Unknown exact domain: {domain}")


def _domain_squares(board: chess.Board, domain: str) -> tuple[chess.Square, ...]:
    piece_type = DOMAIN_PIECES.get(domain)
    if piece_type is None:
        raise ValueError(f"Unknown exact domain: {domain}")
    white_king = board.king(chess.WHITE)
    black_king = board.king(chess.BLACK)
    extras = list(board.pieces(piece_type, chess.WHITE))
    if white_king is None or black_king is None or len(extras) != 1:
        raise ValueError(f"Board does not match {domain}: {board.fen()}")
    if len(board.piece_map()) != 3:
        raise ValueError(f"Board does not have exactly three pieces: {board.fen()}")
    return white_king, extras[0], black_king


def canonical_state_key(board: chess.Board, domain: str) -> str:
    squares = _domain_squares(board, domain)
    variants = [
        tuple(transform_square(square, transform) for square in squares)
        for transform in symmetry_transforms(domain)
    ]
    canonical = min(variants)
    turn = "w" if board.turn else "b"
    encoded = ":".join(f"{square:02d}" for square in canonical)
    return f"{domain}:{turn}:{encoded}"


def canonical_state_hash(canonical_key: str) -> str:
    return hashlib.sha256(canonical_key.encode()).hexdigest()


def partition_for_key(canonical_key: str, seed: int, partition: dict) -> str:
    digest = hashlib.sha256(f"{seed}:{canonical_key}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") % 10000
    development = int(partition["development_upper_exclusive"])
    selection = int(partition["selection_upper_exclusive"])
    confirmation = int(partition["confirmation_upper_exclusive"])
    if not 0 < development < selection < confirmation == 10000:
        raise ValueError("Exact partition boundaries must increase to 10000")
    if bucket < development:
        return "development"
    if bucket < selection:
        return "selection"
    return "confirmation"


def iter_legal_exact_boards(domain: str) -> Iterator[chess.Board]:
    piece_type = DOMAIN_PIECES.get(domain)
    if piece_type is None:
        raise ValueError(f"Unknown exact domain: {domain}")
    extra_squares = tuple(chess.SQUARES)
    if piece_type == chess.PAWN:
        extra_squares = tuple(
            square for square in chess.SQUARES if 1 <= chess.square_rank(square) <= 6
        )
    for white_king in chess.SQUARES:
        for black_king in chess.SQUARES:
            if white_king == black_king:
                continue
            if chess.BB_KING_ATTACKS[white_king] & chess.BB_SQUARES[black_king]:
                continue
            for extra_square in extra_squares:
                if extra_square in {white_king, black_king}:
                    continue
                for turn in (chess.WHITE, chess.BLACK):
                    board = chess.Board.empty()
                    board.set_piece_at(white_king, chess.Piece(chess.KING, chess.WHITE))
                    board.set_piece_at(extra_square, chess.Piece(piece_type, chess.WHITE))
                    board.set_piece_at(black_king, chess.Piece(chess.KING, chess.BLACK))
                    board.turn = turn
                    board.castling_rights = chess.BB_EMPTY
                    board.ep_square = None
                    board.halfmove_clock = 0
                    board.fullmove_number = 1
                    if board.is_valid():
                        yield board


def _sample_rank(seed: int, canonical_key: str) -> int:
    digest = hashlib.sha256(f"sample:{seed}:{canonical_key}".encode()).digest()
    return int.from_bytes(digest, "big")


def audit_domain_census(domain: str, settings: dict, seed: int) -> dict:
    domain_settings = settings["domains"][domain]
    sample_limit = int(domain_settings["development_sample_positions"])
    partition_settings = settings["partition"]
    seen: set[str] = set()
    sample_heap: list[tuple[int, str, str, str]] = []
    raw_legal_states = 0
    raw_terminal_states = 0
    canonical_terminal_states = 0
    partition_counts: Counter[str] = Counter()
    partition_nonterminal_counts: Counter[str] = Counter()
    turns: Counter[str] = Counter()
    for board in iter_legal_exact_boards(domain):
        raw_legal_states += 1
        terminal = board.is_game_over(claim_draw=False)
        raw_terminal_states += int(terminal)
        key = canonical_state_key(board, domain)
        if key in seen:
            continue
        seen.add(key)
        partition = partition_for_key(key, seed, partition_settings)
        partition_counts[partition] += 1
        turns["white" if board.turn else "black"] += 1
        if terminal:
            canonical_terminal_states += 1
            continue
        partition_nonterminal_counts[partition] += 1
        if partition != "development":
            continue
        rank = _sample_rank(seed, key)
        item = (-rank, key, board.fen(), canonical_state_hash(key))
        if len(sample_heap) < sample_limit:
            heapq.heappush(sample_heap, item)
        elif rank < -sample_heap[0][0]:
            heapq.heapreplace(sample_heap, item)
    if len(sample_heap) != sample_limit:
        raise RuntimeError(f"Only {len(sample_heap)} development states available for {domain}")
    sample = [
        {
            "canonical_key": key,
            "canonical_hash": digest,
            "fen": fen,
            "sample_rank": -negative_rank,
        }
        for negative_rank, key, fen, digest in sorted(
            sample_heap, key=lambda item: (-item[0], item[1])
        )
    ]
    return {
        "domain": domain,
        "raw_legal_states": raw_legal_states,
        "raw_terminal_states": raw_terminal_states,
        "canonical_states": len(seen),
        "canonical_terminal_states": canonical_terminal_states,
        "canonical_nonterminal_states": len(seen) - canonical_terminal_states,
        "partition_counts": dict(sorted(partition_counts.items())),
        "partition_nonterminal_counts": dict(sorted(partition_nonterminal_counts.items())),
        "canonical_turn_counts": dict(sorted(turns.items())),
        "development_sample_positions": len(sample),
        "development_sample": sample,
    }


def _validate_expected_census(census: dict, settings: dict) -> None:
    expected = settings["expected_census"][census["domain"]]
    actual = {
        "raw_legal_states": census["raw_legal_states"],
        "canonical_states": census["canonical_states"],
        "canonical_terminal_states": census["canonical_terminal_states"],
        "development": census["partition_counts"]["development"],
        "selection": census["partition_counts"]["selection"],
        "confirmation": census["partition_counts"]["confirmation"],
        "development_sample_digest": census["development_sample_digest"],
    }
    if actual != expected:
        raise RuntimeError(
            f"Exact census changed for {census['domain']}: expected {expected}, got {actual}"
        )


def audit_exact_census(config: dict) -> dict:
    settings = config["branch_law_foundation"]
    seed = int(config["seed"])
    started = time.perf_counter()
    domains = {}
    for domain in settings["domains"]:
        census = audit_domain_census(domain, settings, seed)
        sample = census.pop("development_sample")
        census["development_sample_digest"] = hashlib.sha256(
            "\n".join(record["canonical_hash"] for record in sample).encode()
        ).hexdigest()
        _validate_expected_census(census, settings)
        domains[domain] = census
    return {
        "protocol_version": settings["protocol_version"],
        "seed": seed,
        "domains": domains,
        "runtime_seconds": time.perf_counter() - started,
        "outcomes_probed": 0,
    }


def _manifest_identity(entries: list[dict]) -> str:
    encoded = "\n".join(f"{entry['file']}:{entry['sha256']}" for entry in entries)
    return hashlib.sha256(encoded.encode()).hexdigest()


def prepare_branch_tablebases(
    config: dict, *, directory: str | Path | None = None
) -> dict:
    settings = config["branch_law_foundation"]
    destination = Path(directory or settings["tablebase_directory"])
    files = []
    for entry in settings["tablebases"]:
        files.append(
            {
                **entry,
                **download_verified(
                    entry["url"],
                    destination / entry["file"],
                    entry["sha256"],
                    expected_bytes=int(entry["bytes"]),
                ),
            }
        )
    provenance = {
        "format": "Syzygy WDL50 and DTZ50",
        "directory": str(destination),
        "manifest_identity": _manifest_identity(settings["tablebases"]),
        "files": files,
        "outcomes_probed": 0,
    }
    write_json(destination / "provenance.json", provenance)
    return provenance


def verify_branch_tablebases(
    config: dict, *, directory: str | Path | None = None
) -> dict:
    settings = config["branch_law_foundation"]
    source = Path(directory or settings["tablebase_directory"])
    files = []
    for entry in settings["tablebases"]:
        path = source / entry["file"]
        if not path.exists():
            raise FileNotFoundError(path)
        actual_bytes = path.stat().st_size
        if actual_bytes != int(entry["bytes"]):
            raise RuntimeError(
                f"Tablebase size mismatch for {path}: expected {entry['bytes']}, "
                f"got {actual_bytes}"
            )
        digest = sha256_file(path)
        if digest != entry["sha256"]:
            raise RuntimeError(
                f"Tablebase checksum mismatch for {path}: expected {entry['sha256']}, "
                f"got {digest}"
            )
        files.append({**entry, "path": str(path)})
    return {
        "format": "Syzygy WDL50 and DTZ50",
        "directory": str(source),
        "manifest_identity": _manifest_identity(settings["tablebases"]),
        "files": files,
    }


def _dtz_before_zeroing(wdl: int) -> int:
    return {2: 1, 1: 101, 0: 0, -1: -101, -2: -1}[wdl]


def _move_dtz_from_successor(
    move_wdl: int, successor_dtz: int, *, zeroing: bool, terminal: bool
) -> int:
    if zeroing or terminal:
        return _dtz_before_zeroing(move_wdl)
    if move_wdl > 0:
        return -successor_dtz + 1
    if move_wdl < 0:
        return -successor_dtz - 1
    return 0


def label_exact_state(
    board: chess.Board,
    domain: str,
    canonical_key: str,
    tablebase: chess.syzygy.Tablebase,
    oracle_identity: str,
) -> tuple[dict, list[dict], dict]:
    if board.is_game_over(claim_draw=False):
        raise ValueError("Terminal states do not have branch labels")
    root_wdl = int(tablebase.probe_wdl(board))
    root_dtz = int(tablebase.probe_dtz(board))
    side = "white" if board.turn else "black"
    state_hash = canonical_state_hash(canonical_key)
    forcing = {move.uci() for move in forcing_moves(board)}
    capture_priority = {
        move.uci()
        for move in board.legal_moves
        if board.is_check()
        or board.gives_check(move)
        or board.is_capture(move)
        or move.promotion is not None
    }
    moves = []
    for move in sorted(board.legal_moves, key=lambda candidate: candidate.uci()):
        move_uci = move.uci()
        zeroing = board.is_zeroing(move)
        gives_check = board.gives_check(move)
        is_capture = board.is_capture(move)
        board.push(move)
        successor_fen = board.fen()
        terminal = board.is_game_over(claim_draw=False)
        successor_wdl = int(tablebase.probe_wdl(board))
        successor_dtz = int(tablebase.probe_dtz(board))
        board.pop()
        move_wdl = -successor_wdl
        move_dtz = _move_dtz_from_successor(
            move_wdl, successor_dtz, zeroing=zeroing, terminal=terminal
        )
        moves.append(
            {
                "schema_version": BRANCH_RECORD_SCHEMA_VERSION,
                "source_state_hash": state_hash,
                "source_fen": board.fen(),
                "successor_fen": successor_fen,
                "move_uci": move_uci,
                "side_to_move": side,
                "source_game": None,
                "source_ply": None,
                "partition": "development",
                "root_candidate_uci": move_uci,
                "node_role": "root-candidate",
                "path_moves": [],
                "remaining_depth": 1,
                "branch_budget": "all",
                "move_rank": None,
                "move_wdl": move_wdl,
                "move_dtz": move_dtz,
                "successor_wdl": successor_wdl,
                "successor_dtz": successor_dtz,
                "regret_cp": None,
                "top_k_labels": {},
                "regret_threshold_labels": {},
                "root_decision_consequence": None,
                "refutation_necessity": None,
                "value_of_information": None,
                "label_definition_version": LABEL_DEFINITION_VERSION,
                "representation_version": None,
                "forcing_eligible": move_uci in forcing,
                "capture_eligible": move_uci in capture_priority,
                "zeroing": zeroing,
                "gives_check": gives_check,
                "is_capture": is_capture,
                "promotion": chess.piece_name(move.promotion) if move.promotion else None,
                "oracle": {
                    "kind": "syzygy",
                    "identity": oracle_identity,
                    "configuration": {"root_wdl": root_wdl, "root_dtz": root_dtz},
                },
            }
        )
    best_wdl = max(record["move_wdl"] for record in moves)
    if root_wdl != best_wdl:
        raise RuntimeError(
            f"One-ply WDL recurrence failed for {board.fen()}: root={root_wdl}, moves={best_wdl}"
        )
    best_dtz = min(record["move_dtz"] for record in moves if record["move_wdl"] == best_wdl)
    ordered = sorted(
        moves,
        key=lambda record: (-record["move_wdl"], record["move_dtz"], record["move_uci"]),
    )
    for rank, record in enumerate(ordered, start=1):
        record["move_rank"] = rank
        record["wdl_optimal"] = record["move_wdl"] == best_wdl
        record["dtz_optimal"] = record["wdl_optimal"] and record["move_dtz"] == best_dtz
        record["top_k_labels"] = {
            "top_1": rank <= 1,
            "top_3": rank <= 3,
            "top_5": rank <= 5,
        }
        record["root_decision_consequence"] = {
            "preserves_wdl": record["wdl_optimal"],
            "wdl_degradation": root_wdl - record["move_wdl"],
        }
    state = {
        "schema_version": EXACT_STATE_SCHEMA_VERSION,
        "domain": domain,
        "fen": board.fen(),
        "canonical_key": canonical_key,
        "canonical_hash": state_hash,
        "partition": "development",
        "side_to_move": side,
        "terminal": False,
        "legal_moves": len(moves),
        "root_wdl": root_wdl,
        "root_dtz": root_dtz,
    }
    return state, moves, {
        "root_dtz_recurrence_match": root_dtz == best_dtz,
        "wdl_optimal_moves": sum(record["wdl_optimal"] for record in moves),
        "dtz_optimal_moves": sum(record["dtz_optimal"] for record in moves),
    }


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


def baseline_ordering(
    board: chess.Board,
    branches: list[dict],
    baseline: str,
    *,
    seed: int,
    repeat: int = 0,
) -> tuple[list[str], int]:
    legal = sorted(board.legal_moves, key=lambda move: move.uci())
    if baseline == "random":
        key = canonical_state_hash(board.fen())
        ordered = sorted(
            legal,
            key=lambda move: (
                hashlib.sha256(f"{seed}:{repeat}:{key}:{move.uci()}".encode()).digest(),
                move.uci(),
            ),
        )
        return [move.uci() for move in ordered], len(legal)
    if baseline in {"forcing", "all-captures"}:
        if baseline == "forcing":
            priority = forcing_moves(board)
        else:
            priority = [
                move
                for move in legal
                if board.is_check()
                or board.gives_check(move)
                or board.is_capture(move)
                or move.promotion is not None
            ]
            priority.sort(key=lambda move: _tactical_key(board, move))
        present = set(priority)
        ordered = priority + [move for move in legal if move not in present]
        return [move.uci() for move in ordered], len(legal)
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
        return [move.uci() for move, _ in scored], len(legal)
    if baseline == "oracle-wdl-dtz":
        ordered = sorted(branches, key=lambda record: (record["move_rank"], record["move_uci"]))
        return [record["move_uci"] for record in ordered], 0
    raise ValueError(f"Unknown branch baseline: {baseline}")


def _retention_threshold(points: list[dict], threshold: float) -> float | None:
    for index, point in enumerate(points):
        if all(later["wdl_preservation_rate"] >= threshold for later in points[index:]):
            return float(point["retained_fraction"])
    return None


def measure_exact_branch_curves(
    labeled: list[tuple[dict, list[dict]]], settings: dict, seed: int
) -> dict:
    results = {}
    budgets = settings["branch_budgets"]
    random_repeats = int(settings["random_repeats"])
    for baseline in settings["baseline_orderings"]:
        repeats = random_repeats if baseline == "random" else 1
        accumulators = {
            str(budget): {
                "positions": 0,
                "legal": 0,
                "retained": 0,
                "preserved": 0,
                "optimal_total": 0,
                "optimal_retained": 0,
                "dtz_preserved": 0,
            }
            for budget in budgets
        }
        selector_operations = 0
        natural = {
            "positions": 0,
            "legal": 0,
            "retained": 0,
            "preserved": 0,
            "optimal_total": 0,
            "optimal_retained": 0,
        }
        started = time.perf_counter()
        for repeat in range(repeats):
            for state, branches in labeled:
                board = chess.Board(state["fen"])
                ordering, operations = baseline_ordering(
                    board, branches, baseline, seed=seed, repeat=repeat
                )
                selector_operations += operations
                by_move = {record["move_uci"]: record for record in branches}
                optimal = {record["move_uci"] for record in branches if record["wdl_optimal"]}
                dtz = {record["move_uci"] for record in branches if record["dtz_optimal"]}
                for budget in budgets:
                    count = len(ordering) if budget == "all" else min(int(budget), len(ordering))
                    retained = set(ordering[:count])
                    accumulator = accumulators[str(budget)]
                    accumulator["positions"] += 1
                    accumulator["legal"] += len(ordering)
                    accumulator["retained"] += count
                    accumulator["preserved"] += int(bool(retained & optimal))
                    accumulator["optimal_total"] += len(optimal)
                    accumulator["optimal_retained"] += len(retained & optimal)
                    accumulator["dtz_preserved"] += int(bool(retained & dtz))
                if baseline in {"forcing", "all-captures"}:
                    field = "forcing_eligible" if baseline == "forcing" else "capture_eligible"
                    retained = {move for move, record in by_move.items() if record[field]}
                    natural["positions"] += 1
                    natural["legal"] += len(ordering)
                    natural["retained"] += len(retained)
                    natural["preserved"] += int(bool(retained & optimal))
                    natural["optimal_total"] += len(optimal)
                    natural["optimal_retained"] += len(retained & optimal)
        points = []
        for budget in budgets:
            accumulator = accumulators[str(budget)]
            points.append(
                {
                    "budget": budget,
                    "positions": accumulator["positions"],
                    "mean_legal_moves": accumulator["legal"] / accumulator["positions"],
                    "mean_retained_moves": accumulator["retained"] / accumulator["positions"],
                    "retained_fraction": accumulator["retained"] / accumulator["legal"],
                    "wdl_preservation_rate": accumulator["preserved"]
                    / accumulator["positions"],
                    "wdl_optimal_move_recall": accumulator["optimal_retained"]
                    / accumulator["optimal_total"],
                    "dtz_optimal_retention_rate": accumulator["dtz_preserved"]
                    / accumulator["positions"],
                }
            )
        natural_metrics = None
        if natural["positions"]:
            natural_metrics = {
                "mean_retained_moves": natural["retained"] / natural["positions"],
                "retained_fraction": natural["retained"] / natural["legal"],
                "wdl_preservation_rate": natural["preserved"] / natural["positions"],
                "wdl_optimal_move_recall": natural["optimal_retained"]
                / natural["optimal_total"],
            }
        if points[-1]["wdl_preservation_rate"] != 1.0:
            raise RuntimeError(f"All-legal endpoint failed exact WDL preservation for {baseline}")
        results[baseline] = {
            "points": points,
            "rho_95_wdl": _retention_threshold(points, 0.95),
            "rho_perfect_development": _retention_threshold(points, 1.0),
            "selector_operations": selector_operations,
            "selector_runtime_seconds": time.perf_counter() - started,
            "random_repeats": repeats,
            "natural_category_metrics": natural_metrics,
        }
    return results


def _save_curve_plot(artifact: Path, domain_results: dict) -> None:
    figure, axes = plt.subplots(1, len(domain_results), figsize=(6 * len(domain_results), 5))
    if len(domain_results) == 1:
        axes = [axes]
    for axis, (domain, result) in zip(axes, domain_results.items(), strict=True):
        for baseline, metrics in result["curves"].items():
            axis.plot(
                [point["retained_fraction"] for point in metrics["points"]],
                [point["wdl_preservation_rate"] for point in metrics["points"]],
                marker="o",
                label=baseline,
            )
        axis.axhline(0.95, color="gray", linestyle="--", linewidth=1)
        axis.set_title(domain)
        axis.set_xlabel("Fraction of legal branches retained")
        axis.set_ylabel("Exact WDL decision preservation")
        axis.set_xlim(0, 1.02)
        axis.set_ylim(0, 1.02)
        axis.grid(alpha=0.25)
    axes[0].legend(fontsize=8)
    figure.suptitle("Development exact branch-budget curves")
    figure.tight_layout()
    figure.savefig(artifact / "branch_budget_curve.png", dpi=160)
    plt.close(figure)


def _report(result: dict) -> str:
    rows = []
    for domain, domain_result in result["domains"].items():
        for baseline, curve in domain_result["curves"].items():
            budget_one = curve["points"][0]
            rows.append(
                f"| {domain} | {baseline} | {budget_one['wdl_preservation_rate']:.2%} | "
                f"{curve['rho_95_wdl']:.4f} | {curve['rho_perfect_development']:.4f} |"
            )
    return f"""# Branch-Law Measurement Foundation: {result['experiment_id']}

## Guardrail

This experiment labels deterministic development samples only. It fits no model
and exposes no selection or confirmation outcomes.

## Exact development curves

| Domain | Baseline | WDL preserved at budget 1 | rho_95_wdl | rho_perfect development |
|---|---|---:|---:|---:|
{chr(10).join(rows)}

## Integrity

- Exact development positions: {result['development_positions']}
- Exact legal branches: {result['development_branches']}
- Selection outcomes probed: 0
- Confirmation outcomes probed: 0
- Tablebase manifest: `{result['tablebases']['manifest_identity']}`
- Runtime: {result['runtime_seconds']:.2f} seconds
- Git revision: `{result['git_commit']}`

These are measurement baselines, not a learned branch law or confirmation result.
"""


def run_branch_law_foundation(
    config: dict,
    *,
    tablebase_directory: str | Path | None = None,
    results_dir: str | Path | None = None,
) -> tuple[dict, Path]:
    settings = config["branch_law_foundation"]
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    seed = int(config["seed"])
    provenance = verify_branch_tablebases(config, directory=tablebase_directory)
    root = Path(results_dir or settings["results_directory"])
    experiment_id = _next_experiment_id(root, settings["experiment_name"])
    artifact = root / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    domains = {}
    development_positions = 0
    development_branches = 0
    dtz_recurrence_mismatches = 0
    states_path = artifact / "exact_states.ndjson"
    branches_path = artifact / "branch_records.ndjson"
    with (
        chess.syzygy.open_tablebase(provenance["directory"]) as tablebase,
        states_path.open("w", encoding="utf-8") as state_output,
        branches_path.open("w", encoding="utf-8") as branch_output,
    ):
        for domain in settings["domains"]:
            census = audit_domain_census(domain, settings, seed)
            labeled = []
            sample = census.pop("development_sample")
            census["development_sample_digest"] = hashlib.sha256(
                "\n".join(record["canonical_hash"] for record in sample).encode()
            ).hexdigest()
            _validate_expected_census(census, settings)
            for record in sample:
                board = chess.Board(record["fen"])
                state, branches, label_meta = label_exact_state(
                    board,
                    domain,
                    record["canonical_key"],
                    tablebase,
                    provenance["manifest_identity"],
                )
                state_output.write(json.dumps(state, sort_keys=True) + "\n")
                for branch in branches:
                    branch_output.write(json.dumps(branch, sort_keys=True) + "\n")
                labeled.append((state, branches))
                development_positions += 1
                development_branches += len(branches)
                dtz_recurrence_mismatches += int(
                    not label_meta["root_dtz_recurrence_match"]
                )
            curves = measure_exact_branch_curves(labeled, settings, seed)
            domains[domain] = {"census": census, "curves": curves}
    finished_at = datetime.now(UTC)
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "protocol_version": settings["protocol_version"],
        "seed": seed,
        "git_commit": _git_commit(),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "runtime_seconds": time.perf_counter() - started,
        "development_positions": development_positions,
        "development_branches": development_branches,
        "selection_outcomes_probed": 0,
        "confirmation_outcomes_probed": 0,
        "dtz_recurrence_mismatches": dtz_recurrence_mismatches,
        "tablebases": provenance,
        "domains": domains,
    }
    write_json(artifact / "config.json", config)
    write_json(artifact / "metrics.json", result)
    write_json(artifact / "tablebase_provenance.json", provenance)
    write_json(
        artifact / "environment.json",
        {
            "python": platform.python_version(),
            "python_chess": chess.__version__,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "git_commit": result["git_commit"],
        },
    )
    (artifact / "report.md").write_text(_report(result), encoding="utf-8")
    _save_curve_plot(artifact, domains)
    return result, artifact
