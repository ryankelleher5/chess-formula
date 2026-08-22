from __future__ import annotations

import hashlib
import heapq
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.syzygy
import numpy as np

from .human_corpus import sha256_file

KPKP_TRANSFORMS = (0, 1, 2, 3)
PIECE_TYPES = (
    chess.PAWN,
    chess.KNIGHT,
    chess.BISHOP,
    chess.ROOK,
    chess.QUEEN,
    chess.KING,
)


def _square_transform(square: chess.Square, transform: int) -> chess.Square:
    file_index = chess.square_file(square)
    rank_index = chess.square_rank(square)
    if transform == 0:
        return square
    if transform == 1:
        return chess.square(7 - file_index, rank_index)
    if transform == 2:
        return chess.square(7 - file_index, 7 - rank_index)
    if transform == 3:
        return chess.square(file_index, 7 - rank_index)
    raise ValueError(f"Unknown KPKP transform: {transform}")


def _swaps_colors(transform: int) -> bool:
    return transform in (2, 3)


def _decision_ep_square(board: chess.Board) -> chess.Square | None:
    """Returns an EP square only when it changes the legal move set."""
    return board.ep_square if board.has_legal_en_passant() else None


def transform_board(board: chess.Board, transform: int) -> chess.Board:
    transformed = chess.Board.empty()
    swap = _swaps_colors(transform)
    for square, piece in board.piece_map().items():
        transformed.set_piece_at(
            _square_transform(square, transform),
            chess.Piece(piece.piece_type, not piece.color if swap else piece.color),
        )
    transformed.turn = not board.turn if swap else board.turn
    transformed.castling_rights = 0
    decision_ep_square = _decision_ep_square(board)
    transformed.ep_square = (
        _square_transform(decision_ep_square, transform) if decision_ep_square is not None else None
    )
    transformed.halfmove_clock = 0
    transformed.fullmove_number = 1
    return transformed


def transform_move(move: chess.Move, transform: int) -> chess.Move:
    return chess.Move(
        _square_transform(move.from_square, transform),
        _square_transform(move.to_square, transform),
        promotion=move.promotion,
        drop=move.drop,
    )


def _rule_key(board: chess.Board) -> str:
    fields = board.fen(en_passant="legal").split()
    return " ".join(fields[:4])


def _kpkp_variant_tuple(board: chess.Board, transform: int) -> tuple[int, ...]:
    white_king = board.king(chess.WHITE)
    black_king = board.king(chess.BLACK)
    white_pawns = list(board.pieces(chess.PAWN, chess.WHITE))
    black_pawns = list(board.pieces(chess.PAWN, chess.BLACK))
    if white_king is None or black_king is None or len(white_pawns) != 1 or len(black_pawns) != 1:
        raise ValueError("Board is not fixed-material KPKP")
    if _swaps_colors(transform):
        roles = (black_king, black_pawns[0], white_king, white_pawns[0])
        turn = not board.turn
    else:
        roles = (white_king, white_pawns[0], black_king, black_pawns[0])
        turn = board.turn
    squares = tuple(_square_transform(square, transform) for square in roles)
    decision_ep_square = _decision_ep_square(board)
    ep_square = (
        _square_transform(decision_ep_square, transform) + 1
        if decision_ep_square is not None
        else 0
    )
    return (*squares, int(turn), ep_square)


def _encoded_kpkp_key(values: tuple[int, ...]) -> str:
    wk, wp, bk, bp, turn, ep = values
    return f"KPKP:{turn}:{wk:02d}:{wp:02d}:{bk:02d}:{bp:02d}:{ep:02d}"


def raw_kpkp_state_key(board: chess.Board) -> str:
    return _encoded_kpkp_key(_kpkp_variant_tuple(board, 0))


def canonical_state_key(board: chess.Board, domain: str = "KPKP") -> str:
    if domain == "KPKP" and matches_domain(board, "KPKP"):
        return _encoded_kpkp_key(
            min(_kpkp_variant_tuple(board, transform) for transform in KPKP_TRANSFORMS)
        )
    return f"{domain}:{min(_rule_key(transform_board(board, t)) for t in KPKP_TRANSFORMS)}"


def canonical_transition(
    board: chess.Board, move: chess.Move, domain: str = "KPKP"
) -> tuple[chess.Board, chess.Move, int]:
    candidates = []
    for transform in KPKP_TRANSFORMS:
        transformed_board = transform_board(board, transform)
        transformed_move = transform_move(move, transform)
        candidates.append(
            (
                f"{domain}:{_rule_key(transformed_board)}:{transformed_move.uci()}",
                transformed_board,
                transformed_move,
                transform,
            )
        )
    _, canonical_board, canonical_move, transform = min(candidates, key=lambda item: item[0])
    return canonical_board, canonical_move, transform


def matches_domain(board: chess.Board, domain: str) -> bool:
    counts = {
        (color, piece_type): len(board.pieces(piece_type, color))
        for color in chess.COLORS
        for piece_type in PIECE_TYPES
    }
    if counts[(chess.WHITE, chess.KING)] != 1 or counts[(chess.BLACK, chess.KING)] != 1:
        return False
    if domain == "KPKP":
        expected = {(chess.WHITE, chess.PAWN): 1, (chess.BLACK, chess.PAWN): 1}
    elif domain == "KPPvK":
        expected = {(chess.WHITE, chess.PAWN): 2, (chess.BLACK, chess.PAWN): 0}
    else:
        raise ValueError(f"Unknown exact domain: {domain}")
    for key, value in counts.items():
        if key[1] == chess.KING:
            continue
        if value != expected.get(key, 0):
            return False
    return len(board.piece_map()) == (4 if domain in {"KPKP", "KPPvK"} else -1)


def has_reachable_ep_state(board: chess.Board) -> bool:
    if board.ep_square is None:
        return False
    moved_color = not board.turn
    destination = board.ep_square + (8 if moved_color == chess.WHITE else -8)
    source = board.ep_square + (-8 if moved_color == chess.WHITE else 8)
    pawn = board.piece_at(destination)
    if pawn != chess.Piece(chess.PAWN, moved_color) or board.piece_at(source):
        return False
    predecessor = board.copy(stack=False)
    predecessor.ep_square = None
    predecessor.turn = moved_color
    predecessor.remove_piece_at(destination)
    predecessor.set_piece_at(source, pawn)
    double_push = chess.Move(source, destination)
    if not predecessor.is_valid() or double_push not in predecessor.legal_moves:
        return False
    predecessor.push(double_push)
    return (
        predecessor.board_fen() == board.board_fen()
        and predecessor.turn == board.turn
        and predecessor.ep_square == board.ep_square
    )


def _ep_variant(board: chess.Board) -> chess.Board | None:
    moved_color = not board.turn
    pawn_rank = 3 if moved_color == chess.WHITE else 4
    pawns = board.pieces(chess.PAWN, moved_color) & chess.BB_RANKS[pawn_rank]
    if len(pawns) != 1:
        return None
    destination = next(iter(pawns))
    candidate = board.copy(stack=False)
    candidate.ep_square = destination + (-8 if moved_color == chess.WHITE else 8)
    return candidate if has_reachable_ep_state(candidate) else None


def iter_legal_kpkp_states() -> Iterator[chess.Board]:
    pawn_squares = tuple(square for square in chess.SQUARES if 0 < chess.square_rank(square) < 7)
    for white_king in chess.SQUARES:
        for black_king in chess.SQUARES:
            if black_king == white_king or chess.square_distance(white_king, black_king) <= 1:
                continue
            for white_pawn in pawn_squares:
                if white_pawn in (white_king, black_king):
                    continue
                for black_pawn in pawn_squares:
                    if black_pawn in (white_king, black_king, white_pawn):
                        continue
                    for turn in chess.COLORS:
                        board = chess.Board.empty()
                        board.set_piece_at(white_king, chess.Piece(chess.KING, chess.WHITE))
                        board.set_piece_at(white_pawn, chess.Piece(chess.PAWN, chess.WHITE))
                        board.set_piece_at(black_king, chess.Piece(chess.KING, chess.BLACK))
                        board.set_piece_at(black_pawn, chess.Piece(chess.PAWN, chess.BLACK))
                        board.turn = turn
                        if not board.is_valid():
                            continue
                        yield board
                        ep_board = _ep_variant(board)
                        if ep_board is not None and ep_board.is_valid():
                            yield ep_board


def outcome_free_stratum(board: chess.Board) -> str:
    side = "white" if board.turn else "black"
    ep = "ep" if board.has_legal_en_passant() else "noep"
    return f"{side}:{ep}"


def partition_for_key(key: str, seed: int) -> str:
    bucket = int(hashlib.sha256(f"{seed}:{key}".encode()).hexdigest(), 16) % 10_000
    if bucket < 6_000:
        return "development"
    if bucket < 8_000:
        return "selection"
    return "confirmation"


def canonical_successors(board: chess.Board, domain: str = "KPKP") -> set[str]:
    successors = set()
    for move in board.legal_moves:
        board.push(move)
        if matches_domain(board, domain):
            successors.add(canonical_state_key(board, domain))
        board.pop()
    return successors


def transition_isolation_audit(samples: dict[str, list[chess.Board]], domain: str = "KPKP") -> dict:
    exact_roots = {
        split: {_rule_key(board) for board in boards} for split, boards in samples.items()
    }
    roots = {
        split: {canonical_state_key(board, domain) for board in boards}
        for split, boards in samples.items()
    }
    exact_root_overlap = 0
    symmetry_overlap = 0
    directed_overlap = 0
    details = []
    splits = sorted(samples)
    for index, left in enumerate(splits):
        for right in splits[index + 1 :]:
            exact_root_overlap += len(exact_roots[left] & exact_roots[right])
            overlap = roots[left] & roots[right]
            symmetry_overlap += len(overlap)
            for source, target in ((left, right), (right, left)):
                for board in samples[source]:
                    hits = canonical_successors(board, domain) & roots[target]
                    directed_overlap += len(hits)
                    if hits and len(details) < 20:
                        details.append(
                            {"source": source, "target": target, "successors": sorted(hits)}
                        )
    return {
        "exact_root_overlap": exact_root_overlap,
        "symmetry_class_root_overlap": symmetry_overlap,
        "directed_predecessor_successor_overlap": directed_overlap,
        "passed": exact_root_overlap == 0 and symmetry_overlap == 0 and directed_overlap == 0,
        "details": details,
    }


class _UnionFind:
    def __init__(self, keys: set[str]) -> None:
        self.parent = {key: key for key in keys}

    def find(self, key: str) -> str:
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


def connected_fold_assignments(
    boards: list[chess.Board], *, seed: int, folds: int, domain: str = "KPKP"
) -> dict[str, int]:
    components = transition_components(boards, domain=domain)
    assignments = {}
    for members in components:
        identity = min(members)
        fold = int(hashlib.sha256(f"{seed}:{identity}".encode()).hexdigest(), 16) % folds
        assignments.update({member: fold for member in members})
    return assignments


def transition_components(boards: list[chess.Board], *, domain: str = "KPKP") -> list[list[str]]:
    by_key = {canonical_state_key(board, domain): board for board in boards}
    union_find = _UnionFind(set(by_key))
    sampled_keys = set(by_key)
    for key, board in by_key.items():
        for successor in canonical_successors(board, domain) & sampled_keys:
            union_find.union(key, successor)
    components: dict[str, list[str]] = defaultdict(list)
    for key in by_key:
        components[union_find.find(key)].append(key)
    return [sorted(members) for _, members in sorted(components.items())]


def nested_fold_assignments(
    boards: list[chess.Board], *, seed: int, outer_folds: int, inner_folds: int
) -> tuple[dict[str, int], dict[int, dict[str, int]]]:
    components = transition_components(boards)
    outer = {}
    component_identity = {}
    for members in components:
        identity = min(members)
        fold = int(hashlib.sha256(f"{seed}:{identity}".encode()).hexdigest(), 16) % outer_folds
        for member in members:
            outer[member] = fold
            component_identity[member] = identity
    inner_by_outer = {}
    for held_out in range(outer_folds):
        inner = {}
        for key, outer_fold in outer.items():
            if outer_fold == held_out:
                continue
            identity = component_identity[key]
            fold = (
                int(
                    hashlib.sha256(f"inner:{seed}:{held_out}:{identity}".encode()).hexdigest(),
                    16,
                )
                % inner_folds
            )
            inner[key] = fold
        inner_by_outer[held_out] = inner
    return outer, inner_by_outer


def cross_fit_plan_audit(
    outer: dict[str, int], inner_by_outer: dict[int, dict[str, int]], *, inner_folds: int
) -> dict:
    leakage = 0
    evaluations = {}
    all_keys = set(outer)
    for held_out, inner in sorted(inner_by_outer.items()):
        validation = {key for key, fold in outer.items() if fold == held_out}
        outer_training = all_keys - validation
        if set(inner) != outer_training:
            raise RuntimeError(f"Inner assignment coverage changed for outer fold {held_out}")
        model_training_sizes = {"outer_training_full": len(outer_training)}
        for inner_fold in range(inner_folds):
            model_training = {key for key in outer_training if inner[key] != inner_fold}
            leakage += len(model_training & validation)
            model_training_sizes[f"inner_excluding_{inner_fold}"] = len(model_training)
        leakage += len(outer_training & validation)
        evaluations[str(held_out)] = {
            "validation": len(validation),
            "outer_training": len(outer_training),
            "model_training_sizes": model_training_sizes,
        }
    return {
        "evaluation_fold_model_overlap": leakage,
        "passed": leakage == 0,
        "evaluations": evaluations,
    }


def weighted_estimands(rows: list[dict], population_counts: dict[str, int]) -> dict:
    sample_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        sample_counts[row["stratum"]] += 1
    weighted_retained = weighted_legal = weighted_context = total_weight = 0.0
    for row in rows:
        stratum = row["stratum"]
        weight = population_counts[stratum] / sample_counts[stratum]
        weighted_retained += weight * row["retained"]
        weighted_legal += weight * row["legal"]
        weighted_context += weight * row["retained"] / row["legal"]
        total_weight += weight
    balanced = np.mean(
        [
            np.mean([row["retained"] / row["legal"] for row in rows if row["stratum"] == s])
            for s in sorted(population_counts)
        ]
    )
    return {
        "population_pooled_retained_fraction": weighted_retained / weighted_legal,
        "population_mean_context_retained_fraction": weighted_context / total_weight,
        "stratum_balanced_mean_context_retained_fraction": float(balanced),
    }


def _plane_names(prefix: str) -> list[str]:
    return [
        f"{prefix}:{owner}:{chess.piece_name(piece_type)}:{chess.square_name(square)}"
        for owner in ("self", "opponent")
        for piece_type in PIECE_TYPES
        for square in chess.SQUARES
    ]


def transition_feature_names() -> list[str]:
    names = _plane_names("before") + _plane_names("after")
    names += [
        f"attack:{phase}:{owner}:{chess.square_name(square)}"
        for phase in ("before", "after")
        for owner in ("self", "opponent")
        for square in chess.SQUARES
    ]
    names += [f"moving_piece:{chess.piece_name(piece_type)}" for piece_type in PIECE_TYPES]
    names += ["captured_piece:none"] + [
        f"captured_piece:{chess.piece_name(piece_type)}" for piece_type in PIECE_TYPES
    ]
    names += ["promotion:none"] + [
        f"promotion:{chess.piece_name(piece_type)}"
        for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
    ]
    names += [
        "source_file",
        "source_rank",
        "destination_file",
        "destination_rank",
        "capture",
        "gives_check",
        "zeroing",
        "ep_available",
        "legal_moves_before",
        "legal_moves_after",
        "self_pawns",
        "opponent_pawns",
        "self_min_promotion_distance",
        "opponent_min_promotion_distance",
    ]
    return names


def _occupancy(board: chess.Board, perspective: chess.Color) -> list[float]:
    values = []
    for owner in (perspective, not perspective):
        for piece_type in PIECE_TYPES:
            occupied = board.pieces(piece_type, owner)
            values.extend(float(square in occupied) for square in chess.SQUARES)
    return values


def _attacks(board: chess.Board, perspective: chess.Color) -> list[float]:
    values = []
    for owner in (perspective, not perspective):
        attacked = chess.SquareSet()
        for square in chess.scan_forward(board.occupied_co[owner]):
            attacked |= board.attacks(square)
        values.extend(float(square in attacked) for square in chess.SQUARES)
    return values


def _promotion_distance(board: chess.Board, color: chess.Color) -> float:
    pawns = board.pieces(chess.PAWN, color)
    if not pawns:
        return 1.0
    distances = [
        (7 - chess.square_rank(square)) if color == chess.WHITE else chess.square_rank(square)
        for square in pawns
    ]
    return min(distances) / 6.0


def transition_features(board: chess.Board, move: chess.Move) -> np.ndarray:
    canonical_board, canonical_move, _ = canonical_transition(board, move)
    perspective = canonical_board.turn
    before_occupancy = _occupancy(canonical_board, perspective)
    before_attacks = _attacks(canonical_board, perspective)
    capture = canonical_board.is_capture(canonical_move)
    moving_piece = canonical_board.piece_type_at(canonical_move.from_square)
    if canonical_board.is_en_passant(canonical_move):
        captured_piece = chess.PAWN
    else:
        captured_piece = canonical_board.piece_type_at(canonical_move.to_square)
    gives_check = canonical_board.gives_check(canonical_move)
    zeroing = canonical_board.is_zeroing(canonical_move)
    ep_available = canonical_board.has_legal_en_passant()
    legal_before = canonical_board.legal_moves.count()
    canonical_board.push(canonical_move)
    after_occupancy = _occupancy(canonical_board, not canonical_board.turn)
    after_attacks = _attacks(canonical_board, not canonical_board.turn)
    legal_after = canonical_board.legal_moves.count()
    canonical_board.pop()
    categorical = [float(moving_piece == piece_type) for piece_type in PIECE_TYPES]
    categorical += [float(captured_piece is None)] + [
        float(captured_piece == piece_type) for piece_type in PIECE_TYPES
    ]
    categorical += [float(canonical_move.promotion is None)] + [
        float(canonical_move.promotion == piece_type)
        for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
    ]
    scalars = [
        chess.square_file(canonical_move.from_square) / 7.0,
        chess.square_rank(canonical_move.from_square) / 7.0,
        chess.square_file(canonical_move.to_square) / 7.0,
        chess.square_rank(canonical_move.to_square) / 7.0,
        float(capture),
        float(gives_check),
        float(zeroing),
        float(ep_available),
        legal_before / 218.0,
        legal_after / 218.0,
        len(canonical_board.pieces(chess.PAWN, perspective)) / 8.0,
        len(canonical_board.pieces(chess.PAWN, not perspective)) / 8.0,
        _promotion_distance(canonical_board, perspective),
        _promotion_distance(canonical_board, not perspective),
    ]
    return np.asarray(
        before_occupancy + after_occupancy + before_attacks + after_attacks + categorical + scalars,
        dtype=np.float32,
    )


def random_move_ordering(board: chess.Board, *, seed: int, repeat: int) -> list[chess.Move]:
    state_key = canonical_state_key(board)
    ranked = []
    for move in board.legal_moves:
        _, canonical_move, _ = canonical_transition(board, move)
        payload = f"random-v1:{seed}:{repeat}:{state_key}:{canonical_move.uci()}"
        ranked.append((hashlib.sha256(payload.encode()).hexdigest(), canonical_move.uci(), move))
    return [move for _, _, move in sorted(ranked)]


def primitive_geometry_strata(board: chess.Board, move: chess.Move) -> dict[str, str | list[str]]:
    legal_moves = board.legal_moves.count()
    legal_move_bin = "1-4" if legal_moves <= 4 else "5-8" if legal_moves <= 8 else "9-or-more"
    white_king = board.king(chess.WHITE)
    black_king = board.king(chess.BLACK)
    if white_king is None or black_king is None:
        raise ValueError("Primitive geometry requires both kings")
    king_distance = chess.square_distance(white_king, black_king)
    king_bin = "2" if king_distance == 2 else "3-4" if king_distance <= 4 else "5-or-more"
    white_pawns = board.pieces(chess.PAWN, chess.WHITE)
    black_pawns = board.pieces(chess.PAWN, chess.BLACK)
    file_distances = [
        abs(chess.square_file(white) - chess.square_file(black))
        for white in white_pawns
        for black in black_pawns
    ]
    pawn_file_distance = min(file_distances) if file_distances else 8
    pawn_file_bin = (
        "0"
        if pawn_file_distance == 0
        else "1"
        if pawn_file_distance == 1
        else "2-3"
        if pawn_file_distance <= 3
        else "4-or-more"
    )
    promotion_distances = []
    for square in white_pawns:
        promotion_distances.append(7 - chess.square_rank(square))
    for square in black_pawns:
        promotion_distances.append(chess.square_rank(square))
    minimum_promotion = min(promotion_distances) if promotion_distances else 6
    promotion_bin = (
        "1"
        if minimum_promotion == 1
        else "2"
        if minimum_promotion == 2
        else "3-4"
        if minimum_promotion <= 4
        else "5-6"
    )
    move_kinds = []
    if board.is_capture(move):
        move_kinds.append("capture")
    if move.promotion is not None:
        move_kinds.append("promotion")
    if board.gives_check(move):
        move_kinds.append("check")
    if board.is_en_passant(move):
        move_kinds.append("legal-en-passant")
    if not move_kinds:
        move_kinds.append("quiet")
    return {
        "legal_move_count": legal_move_bin,
        "king_chebyshev_distance": king_bin,
        "pawn_file_distance": pawn_file_bin,
        "minimum_promotion_distance": promotion_bin,
        "legal_en_passant": str(board.has_legal_en_passant()).lower(),
        "move_kind": move_kinds,
    }


@dataclass(frozen=True)
class SampleQuota:
    white_noep: int
    black_noep: int
    white_ep: int
    black_ep: int

    def as_dict(self) -> dict[str, int]:
        return {
            "white:noep": self.white_noep,
            "black:noep": self.black_noep,
            "white:ep": self.white_ep,
            "black:ep": self.black_ep,
        }


def _digest_keys(keys: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(keys)).encode()).hexdigest()


def _reservoir_add(
    heap: list[tuple[int, str, str]], *, capacity: int, rank: int, key: str, fen: str
) -> None:
    item = (-rank, key, fen)
    if len(heap) < capacity:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def _boards_from_reservoir(heap: list[tuple[int, str, str]]) -> list[chess.Board]:
    ordered = sorted(((-rank, key, fen) for rank, key, fen in heap))
    return [chess.Board(fen) for _, _, fen in ordered]


def _select_with_embargo(
    candidates: dict[str, list[chess.Board]],
    quotas: dict[str, int],
    prior: list[chess.Board],
) -> list[chess.Board]:
    prior_roots = {canonical_state_key(board) for board in prior}
    prior_successors = set()
    for board in prior:
        prior_successors.update(canonical_successors(board))
    selected = []
    for stratum, required in quotas.items():
        accepted = []
        for board in candidates[stratum]:
            key = canonical_state_key(board)
            if key in prior_roots or key in prior_successors:
                continue
            if canonical_successors(board) & prior_roots:
                continue
            accepted.append(board)
            if len(accepted) == required:
                break
        if len(accepted) != required:
            raise RuntimeError(
                f"Outcome-free embargo leaves {len(accepted)} of {required} "
                f"required {stratum} states"
            )
        selected.extend(accepted)
    return selected


def audit_kpkp_outcome_free_source(
    *,
    seed: int,
    development_quota: SampleQuota,
    selection_quota: SampleQuota,
    confirmation_quota: SampleQuota,
    reservoir_multiplier: int = 4,
    folds: int = 5,
    inner_folds: int = 4,
    _include_samples: bool = False,
) -> dict:
    quotas = {
        "development": development_quota.as_dict(),
        "selection": selection_quota.as_dict(),
        "confirmation": confirmation_quota.as_dict(),
    }
    heaps: dict[tuple[str, str], list[tuple[int, str, str]]] = defaultdict(list)
    counts = {
        "raw_valid_states": 0,
        "behaviorally_irrelevant_ep_history_states": 0,
        "canonical_states": 0,
        "canonical_terminal_states": 0,
        "canonical_en_passant_states": 0,
    }
    partition_counts: dict[str, int] = defaultdict(int)
    stratum_counts: dict[str, int] = defaultdict(int)
    nonterminal_stratum_counts: dict[str, int] = defaultdict(int)
    partition_hashes = {
        split: hashlib.sha256() for split in ("development", "selection", "confirmation")
    }
    for board in iter_legal_kpkp_states():
        counts["raw_valid_states"] += 1
        if board.ep_square is not None and not board.has_legal_en_passant():
            counts["behaviorally_irrelevant_ep_history_states"] += 1
            continue
        key = canonical_state_key(board)
        if key != raw_kpkp_state_key(board):
            continue
        counts["canonical_states"] += 1
        counts["canonical_terminal_states"] += int(board.is_game_over(claim_draw=False))
        counts["canonical_en_passant_states"] += int(board.ep_square is not None)
        split = partition_for_key(key, seed)
        stratum = outcome_free_stratum(board)
        partition_counts[split] += 1
        stratum_counts[f"{split}:{stratum}"] += 1
        partition_hashes[split].update(f"{key}\n".encode())
        if board.is_game_over(claim_draw=False):
            continue
        nonterminal_stratum_counts[f"{split}:{stratum}"] += 1
        capacity = quotas[split][stratum] * reservoir_multiplier
        rank = int(hashlib.sha256(f"sample:{seed}:{key}".encode()).hexdigest(), 16)
        _reservoir_add(
            heaps[(split, stratum)],
            capacity=capacity,
            rank=rank,
            key=key,
            fen=board.fen(en_passant="fen"),
        )
    reservoirs = {
        split: {stratum: _boards_from_reservoir(heaps[(split, stratum)]) for stratum in quota}
        for split, quota in quotas.items()
    }
    development = _select_with_embargo(reservoirs["development"], quotas["development"], [])
    selection = _select_with_embargo(reservoirs["selection"], quotas["selection"], development)
    confirmation = _select_with_embargo(
        reservoirs["confirmation"],
        quotas["confirmation"],
        development + selection,
    )
    samples = {
        "development": development,
        "selection": selection,
        "confirmation": confirmation,
    }
    isolation = transition_isolation_audit(samples)
    if not isolation["passed"]:
        raise RuntimeError(f"Outcome-free split isolation failed: {isolation}")
    fold_assignments, inner_assignments = nested_fold_assignments(
        development, seed=seed, outer_folds=folds, inner_folds=inner_folds
    )
    fold_counts: dict[int, int] = defaultdict(int)
    for fold in fold_assignments.values():
        fold_counts[fold] += 1
    inner_fold_counts = {}
    inner_fold_digests = {}
    for held_out, assignments in sorted(inner_assignments.items()):
        counts_by_fold: dict[int, int] = defaultdict(int)
        for fold in assignments.values():
            counts_by_fold[fold] += 1
        inner_fold_counts[str(held_out)] = {
            str(fold): count for fold, count in sorted(counts_by_fold.items())
        }
        inner_fold_digests[str(held_out)] = hashlib.sha256(
            "\n".join(f"{key}:{fold}" for key, fold in sorted(assignments.items())).encode()
        ).hexdigest()
    cross_fit_audit = cross_fit_plan_audit(
        fold_assignments, inner_assignments, inner_folds=inner_folds
    )
    if not cross_fit_audit["passed"]:
        raise RuntimeError(f"Cross-fit source audit failed: {cross_fit_audit}")
    result = {
        **counts,
        "partition_counts": dict(sorted(partition_counts.items())),
        "partition_stratum_counts": dict(sorted(stratum_counts.items())),
        "nonterminal_partition_stratum_counts": dict(sorted(nonterminal_stratum_counts.items())),
        "partition_digests": {
            split: digest.hexdigest() for split, digest in partition_hashes.items()
        },
        "sample_counts": {split: len(boards) for split, boards in samples.items()},
        "sample_digests": {
            split: _digest_keys([canonical_state_key(board) for board in boards])
            for split, boards in samples.items()
        },
        "sample_stratum_counts": {
            split: dict(
                sorted(
                    (stratum, sum(outcome_free_stratum(board) == stratum for board in boards))
                    for stratum in quotas[split]
                )
            )
            for split, boards in samples.items()
        },
        "development_fold_counts": {
            str(fold): count for fold, count in sorted(fold_counts.items())
        },
        "development_fold_digest": hashlib.sha256(
            "\n".join(f"{key}:{fold}" for key, fold in sorted(fold_assignments.items())).encode()
        ).hexdigest(),
        "inner_fold_counts_by_outer": inner_fold_counts,
        "inner_fold_digests_by_outer": inner_fold_digests,
        "cross_fit_plan": cross_fit_audit,
        "transition_isolation": isolation,
        "outcomes_probed": 0,
        "tablebase_files_opened": 0,
    }
    if _include_samples:
        result["_samples"] = samples
    return result


def tablebase_manifest_identity(entries: list[dict]) -> str:
    encoded = "\n".join(
        f"{entry['file']}:{entry['bytes']}:{entry['sha256']}:{entry['url']}"
        for entry in sorted(entries, key=lambda item: item["file"])
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def audit_kpkp_tablebase_manifest(config: dict) -> dict:
    settings = config["experiment_021_kpkp_review"]
    manifest = settings["tablebase_manifest"]
    entries = manifest["files"]
    required = {
        f"{material}.{suffix}"
        for material in (
            "KPvKP",
            "KQvKP",
            "KRvKP",
            "KBvKP",
            "KNvKP",
            "KPvK",
            "KQvK",
            "KRvK",
            "KBvK",
            "KNvK",
        )
        for suffix in ("rtbw", "rtbz")
    }
    actual = {entry["file"] for entry in entries}
    if actual != required:
        raise RuntimeError(
            f"KPKP tablebase closure mismatch: missing={sorted(required - actual)}, "
            f"extra={sorted(actual - required)}"
        )
    for entry in entries:
        if int(entry["bytes"]) <= 0:
            raise RuntimeError(f"Invalid byte count for {entry['file']}")
        digest = str(entry["sha256"])
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise RuntimeError(f"Invalid SHA-256 for {entry['file']}")
    identity = tablebase_manifest_identity(entries)
    if identity != manifest["identity"]:
        raise RuntimeError(
            f"KPKP manifest identity changed: expected {manifest['identity']}, got {identity}"
        )
    return {
        "files": len(entries),
        "bytes": sum(int(entry["bytes"]) for entry in entries),
        "identity": identity,
        "metadata_source": manifest["metadata_source"],
        "tablebase_files_opened": 0,
        "outcomes_probed": 0,
    }


def verify_kpkp_tablebase_files(config: dict, directory: str | Path) -> dict:
    manifest = config["experiment_021_kpkp_review"]["tablebase_manifest"]
    source = Path(directory)
    verified = []
    for entry in manifest["files"]:
        path = source / entry["file"]
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size != int(entry["bytes"]):
            raise RuntimeError(f"Tablebase byte count mismatch for {path}")
        if sha256_file(path) != entry["sha256"]:
            raise RuntimeError(f"Tablebase checksum mismatch for {path}")
        verified.append(str(path))
    return {"verified_files": verified, "manifest_identity": manifest["identity"]}


def enforce_kpkp_probe_partition(config: dict, partition: str) -> None:
    settings = config["experiment_021_kpkp_review"]
    if partition != "development":
        raise PermissionError(
            "Experiment 021 probe path permanently denies selection and confirmation"
        )
    if not settings["development_outcomes_authorized"]:
        raise PermissionError("Experiment 021 development outcomes are not authorized")
    if not settings["tablebase_probes_authorized"]:
        raise PermissionError("Experiment 021 tablebase probes are not authorized")


def probe_kpkp_development_labels(
    config: dict, *, directory: str | Path, partition: str
) -> list[dict]:
    """The only Experiment 021 label path; inaccessible in the review config."""
    enforce_kpkp_probe_partition(config, partition)
    manifest_audit = audit_kpkp_tablebase_manifest(config)
    verify_kpkp_tablebase_files(config, directory)
    settings = config["experiment_021_kpkp_review"]
    samples = settings["samples"]
    source = audit_kpkp_outcome_free_source(
        seed=int(config["seed"]),
        development_quota=SampleQuota(**samples["development"]),
        selection_quota=SampleQuota(**samples["selection"]),
        confirmation_quota=SampleQuota(**samples["confirmation"]),
        reservoir_multiplier=int(settings["reservoir_multiplier"]),
        folds=int(settings["development_folds"]),
        inner_folds=int(settings["inner_folds"]),
        _include_samples=True,
    )
    expected = settings["expected_outcome_free_audit"]
    actual = {key: source[key] for key in expected}
    if actual != expected:
        raise RuntimeError("KPKP source identities changed before development probe")
    from .branch_law import label_exact_state

    records = []
    with chess.syzygy.open_tablebase(str(directory)) as tablebase:
        for board in source["_samples"]["development"]:
            key = canonical_state_key(board)
            state, moves, recurrence = label_exact_state(
                board,
                "KPKP",
                key,
                tablebase,
                manifest_audit["identity"],
            )
            records.append({"state": state, "moves": moves, "recurrence": recurrence})
    return records


def audit_kpkp_review_config(config: dict) -> dict:
    settings = config["experiment_021_kpkp_review"]
    samples = settings["samples"]
    result = audit_kpkp_outcome_free_source(
        seed=int(config["seed"]),
        development_quota=SampleQuota(**samples["development"]),
        selection_quota=SampleQuota(**samples["selection"]),
        confirmation_quota=SampleQuota(**samples["confirmation"]),
        reservoir_multiplier=int(settings["reservoir_multiplier"]),
        folds=int(settings["development_folds"]),
        inner_folds=int(settings["inner_folds"]),
    )
    expected = settings["expected_outcome_free_audit"]
    actual = {key: result[key] for key in expected}
    if actual != expected:
        raise RuntimeError(f"KPKP outcome-free audit changed: {actual}")
    return {**result, "tablebase_manifest": audit_kpkp_tablebase_manifest(config)}
