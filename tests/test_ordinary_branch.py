from __future__ import annotations

import hashlib
import json
from pathlib import Path

import chess

from chess_formula.human_corpus import sha256_file
from chess_formula.ingest import position_hash
from chess_formula.ordinary_branch import (
    _mover_regret,
    _select_move,
    audit_ordinary_branch_source,
    measure_ordinary_branch_curves,
    ordinary_baseline_ordering,
)


def test_select_move_and_regret_are_mover_oriented() -> None:
    scores = {"a": 100.0, "b": -25.0, "c": 40.0}
    assert _select_move(scores, chess.WHITE) == "a"
    assert _select_move(scores, chess.BLACK) == "b"
    assert _mover_regret(100.0, 40.0, chess.WHITE) == 60.0
    assert _mover_regret(-25.0, 40.0, chess.BLACK) == 65.0


def test_ordinary_baselines_return_complete_deterministic_orderings() -> None:
    board = chess.Board()
    scores = {move.uci(): float(index) for index, move in enumerate(board.legal_moves)}
    expected = set(scores)
    for baseline in ("random", "forcing", "all-captures", "locked-3", "oracle"):
        first = ordinary_baseline_ordering(board, scores, baseline, seed=9)
        second = ordinary_baseline_ordering(board, scores, baseline, seed=9)
        assert first == second
        assert set(first) == expected


def test_source_audit_fails_closed_and_counts_contexts(tmp_path: Path) -> None:
    board = chess.Board()
    source = tmp_path / "positions.json"
    rows = [
        {
            "position_hash": position_hash(board.fen()),
            "fen": board.fen(),
            "candidate_color": "white",
            "source_game_key": "game-1",
            "pair_key": "pair-1",
            "opening_id": "start",
            "opponent": "test",
            "ply": 0,
        }
    ]
    source.write_text(json.dumps(rows), encoding="utf-8")
    parents = []
    reply_count = 0
    for move in board.legal_moves:
        board.push(move)
        parents.append(f"parent:{position_hash(board.fen())}")
        reply_count += board.legal_moves.count()
        board.pop()
    root_key = f"root:{rows[0]['position_hash']}"
    stable_parent = sorted(
        parents,
        key=lambda key: hashlib.sha256(f"stability:{key}".encode()).digest(),
    )[0]
    config = {
        "ordinary_branch_foundation": {
            "source_positions": str(source),
            "source_positions_bytes": source.stat().st_size,
            "source_positions_sha256": sha256_file(source),
            "source_position_hash_digest": hashlib.sha256(
                rows[0]["position_hash"].encode()
            ).hexdigest(),
            "source_game_key_digest": hashlib.sha256(b"game-1").hexdigest(),
            "expected_positions": 1,
            "expected_source_games": 1,
            "expected_pair_groups": 1,
            "expected_candidate_contexts": 20,
            "expected_nonterminal_parent_contexts": 20,
            "expected_terminal_candidates": 0,
            "expected_opponent_reply_records": reply_count,
            "parent_key_digest": hashlib.sha256(
                "\n".join(sorted(parents)).encode()
            ).hexdigest(),
            "stability_audit": {
                "root_contexts": 1,
                "parent_contexts": 1,
                "root_sample_digest": hashlib.sha256(root_key.encode()).hexdigest(),
                "parent_sample_digest": hashlib.sha256(
                    stable_parent.encode()
                ).hexdigest(),
            },
        }
    }
    audit = audit_ordinary_branch_source(config)
    assert audit["candidate_contexts"] == 20
    assert audit["opponent_reply_records"] == reply_count
    assert audit["outcomes_probed"] == 0


def _synthetic_root() -> dict:
    board = chess.Board()
    moves = sorted(move.uci() for move in board.legal_moves)[:2]
    candidates = []
    for index, move in enumerate(moves):
        replies = [
            {
                "move_uci": "a7a6",
                "eval_cp": float(index * 50),
                "refutation": {"candidate_critical": {"over_25cp": index == 1}},
                "root_consequence": {"root_critical": {"over_25cp": index == 1}},
            },
            {
                "move_uci": "a7a5",
                "eval_cp": float(index * 50 + 20),
                "refutation": {"candidate_critical": {"over_25cp": False}},
                "root_consequence": {"root_critical": {"over_25cp": False}},
            },
        ]
        candidates.append(
            {
                "move_uci": move,
                "search_value": float(index * 50),
                "replies": replies,
                "parent_hash": f"parent-{index}",
                "parent_fen": "rnbqkbnr/1ppppppp/p7/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 2",
                "orderings": {
                    baseline: ["a7a6", "a7a5"]
                    for baseline in ("forcing", "all-captures", "locked-3", "oracle")
                },
                "natural_forcing": set(),
                "natural_captures": set(),
            }
        )
    return {
        "turn": chess.WHITE,
        "all_reply_choice": moves[1],
        "all_reply_absolute_regret_cp": 0.0,
        "direct_best_score": 50.0,
        "direct_scores": {moves[0]: 0.0, moves[1]: 50.0},
        "candidates": candidates,
    }


def test_oracle_curve_preserves_all_reply_choice_at_budget_one() -> None:
    config = {
        "seed": 1,
        "ordinary_branch_foundation": {
            "branch_budgets": [1, "all"],
            "baseline_orderings": ["oracle"],
            "random_repeats": 2,
            "decision_preservation_threshold_cp": 25,
        },
    }
    result = measure_ordinary_branch_curves([_synthetic_root()], config)
    assert result["oracle"]["rho_95"] == 0.5
    assert all(
        point["exact_all_reply_choice_agreement"] == 1.0
        for point in result["oracle"]["points"]
    )


def test_ordinary_branch_json_contracts_parse() -> None:
    for path in (
        Path("configs/ordinary-branch-foundation.json"),
        Path("configs/oracle-convergence.json"),
        Path("benchmarks/ordinary-branch-foundation-v1.json"),
        Path("benchmarks/oracle-convergence-v1.json"),
        Path("schemas/ordinary-root-record-v1.json"),
        Path("schemas/ordinary-branch-record-v1.json"),
    ):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
