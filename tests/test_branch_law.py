from __future__ import annotations

import hashlib
import json
from itertools import islice
from pathlib import Path

import chess

from chess_formula.branch_law import (
    baseline_ordering,
    canonical_state_key,
    iter_legal_exact_boards,
    label_exact_state,
    measure_exact_branch_curves,
    partition_for_key,
    prepare_branch_tablebases,
    symmetry_transforms,
    verify_branch_tablebases,
)


def _board(
    white_king: chess.Square,
    extra: chess.Square,
    black_king: chess.Square,
    piece_type: chess.PieceType,
    *,
    turn: chess.Color = chess.WHITE,
) -> chess.Board:
    board = chess.Board.empty()
    board.set_piece_at(white_king, chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(extra, chess.Piece(piece_type, chess.WHITE))
    board.set_piece_at(black_king, chess.Piece(chess.KING, chess.BLACK))
    board.turn = turn
    return board


def test_pawnless_canonicalization_matches_file_reflection() -> None:
    first = _board(chess.A1, chess.C3, chess.H8, chess.QUEEN)
    reflected = _board(chess.H1, chess.F3, chess.A8, chess.QUEEN)
    assert canonical_state_key(first, "KQvK") == canonical_state_key(reflected, "KQvK")
    assert symmetry_transforms("KQvK") == tuple(range(8))


def test_pawn_canonicalization_uses_only_file_reflection() -> None:
    first = _board(chess.A2, chess.C4, chess.H8, chess.PAWN)
    reflected = _board(chess.H2, chess.F4, chess.A8, chess.PAWN)
    rank_reflected = _board(chess.A7, chess.C5, chess.H1, chess.PAWN)
    assert canonical_state_key(first, "KPvK") == canonical_state_key(reflected, "KPvK")
    assert canonical_state_key(first, "KPvK") != canonical_state_key(rank_reflected, "KPvK")
    assert symmetry_transforms("KPvK") == (0, 4)


def test_partition_is_stable_for_a_canonical_class() -> None:
    boundaries = {
        "development_upper_exclusive": 6000,
        "selection_upper_exclusive": 8000,
        "confirmation_upper_exclusive": 10000,
    }
    key = "KQvK:w:00:18:63"
    assert partition_for_key(key, 17, boundaries) == partition_for_key(key, 17, boundaries)


def test_exact_generator_emits_only_valid_fixed_material_states() -> None:
    for board in islice(iter_legal_exact_boards("KRvK"), 100):
        assert board.is_valid()
        assert len(board.piece_map()) == 3
        assert len(board.pieces(chess.ROOK, chess.WHITE)) == 1
        assert board.castling_rights == 0
        assert board.ep_square is None


def test_verified_tablebase_manifest_fails_closed_and_reuses_files(tmp_path: Path) -> None:
    source = tmp_path / "source.rtbw"
    source.write_bytes(b"exact table")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    config = {
        "branch_law_foundation": {
            "tablebase_directory": str(tmp_path / "tables"),
            "tablebases": [
                {
                    "file": "KQvK.rtbw",
                    "kind": "wdl",
                    "url": source.as_uri(),
                    "bytes": source.stat().st_size,
                    "sha256": digest,
                }
            ],
        }
    }
    first = prepare_branch_tablebases(config)
    second = prepare_branch_tablebases(config)
    verified = verify_branch_tablebases(config)
    assert first["files"][0]["cached"] is False
    assert second["files"][0]["cached"] is True
    assert verified["files"][0]["sha256"] == digest


class _TurnTablebase:
    def probe_wdl(self, board: chess.Board) -> int:
        return 2 if board.turn == chess.WHITE else -2

    def probe_dtz(self, board: chess.Board) -> int:
        return 1 if board.turn == chess.WHITE else -1


def test_exact_labels_are_mover_oriented_and_complete() -> None:
    board = _board(chess.A1, chess.C3, chess.H8, chess.ROOK)
    key = canonical_state_key(board, "KRvK")
    state, branches, metadata = label_exact_state(
        board, "KRvK", key, _TurnTablebase(), "test-tablebase"
    )
    assert state["root_wdl"] == 2
    assert len(branches) == board.legal_moves.count()
    assert all(branch["move_wdl"] == 2 for branch in branches)
    assert all(branch["wdl_optimal"] for branch in branches)
    assert metadata["wdl_optimal_moves"] == len(branches)


def test_oracle_curve_preserves_exact_wdl_at_every_budget() -> None:
    board = _board(chess.A1, chess.C3, chess.H8, chess.ROOK)
    moves = sorted(board.legal_moves, key=lambda move: move.uci())
    branches = [
        {
            "move_uci": move.uci(),
            "move_rank": index + 1,
            "wdl_optimal": index == 0,
            "dtz_optimal": index == 0,
        }
        for index, move in enumerate(moves)
    ]
    state = {"fen": board.fen()}
    settings = {
        "branch_budgets": [1, "all"],
        "random_repeats": 2,
        "baseline_orderings": ["oracle-wdl-dtz"],
    }
    result = measure_exact_branch_curves([(state, branches)], settings, seed=11)
    assert result["oracle-wdl-dtz"]["rho_95_wdl"] == 1 / len(moves)
    assert all(
        point["wdl_preservation_rate"] == 1.0
        for point in result["oracle-wdl-dtz"]["points"]
    )


def test_baselines_return_complete_deterministic_orderings() -> None:
    board = _board(chess.A1, chess.C3, chess.H8, chess.ROOK)
    branches = [
        {"move_uci": move.uci(), "move_rank": index + 1}
        for index, move in enumerate(sorted(board.legal_moves, key=lambda move: move.uci()))
    ]
    expected = {move.uci() for move in board.legal_moves}
    for baseline in ("random", "forcing", "all-captures", "locked-3", "oracle-wdl-dtz"):
        first, _ = baseline_ordering(board, branches, baseline, seed=7)
        second, _ = baseline_ordering(board, branches, baseline, seed=7)
        assert first == second
        assert set(first) == expected


def test_branch_law_json_contracts_parse() -> None:
    for path in (
        Path("configs/branch-law-foundation.json"),
        Path("configs/experiment-021-kpkp-review.json"),
        Path("benchmarks/branch-law-foundation-v1.json"),
        Path("schemas/exact-state-v1.json"),
        Path("schemas/branch-record-v1.json"),
    ):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
