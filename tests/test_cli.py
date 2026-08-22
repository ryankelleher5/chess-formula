from __future__ import annotations

import pytest

from chess_formula.cli import build_parser, main


def test_cli_parses_required_commands() -> None:
    args = build_parser().parse_args(["ingest", "sample.pgn"])
    assert args.command == "ingest"
    assert args.pgn == "sample.pgn"

    stability = build_parser().parse_args(["stability", "baseline-linear"])
    assert stability.command == "stability"

    corpus = build_parser().parse_args(["generate-corpus", "--output", "generated.pgn"])
    assert corpus.output == "generated.pgn"

    human = build_parser().parse_args(["prepare-human-corpus"])
    assert human.command == "prepare-human-corpus"

    selection = build_parser().parse_args(["select-features"])
    assert selection.command == "select-features"

    confirmation = build_parser().parse_args(["confirm-subset"])
    assert confirmation.command == "confirm-subset"

    failures = build_parser().parse_args(["mine-failures"])
    assert failures.command == "mine-failures"

    march = build_parser().parse_args(["validate-march"])
    assert march.command == "validate-march"

    depth = build_parser().parse_args(["validate-depth"])
    assert depth.command == "validate-depth"

    moves = build_parser().parse_args(["validate-moves", "--stockfish", "stockfish"])
    assert moves.command == "validate-moves"

    pilot = build_parser().parse_args(["run-uci-pilot", "--stockfish", "stockfish"])
    assert pilot.command == "run-uci-pilot"

    audit = build_parser().parse_args(["audit-uci-losses", "--stockfish", "stockfish"])
    assert audit.command == "audit-uci-losses"

    frontier = build_parser().parse_args(["run-search-frontier", "--stockfish", "stockfish"])
    assert frontier.command == "run-search-frontier"

    confirmation = build_parser().parse_args(["confirm-forcing-3", "--stockfish", "stockfish"])
    assert confirmation.command == "confirm-forcing-3"

    curve = build_parser().parse_args(["run-budget-curve", "--stockfish", "stockfish"])
    assert curve.command == "run-budget-curve"

    tablebases = build_parser().parse_args(["prepare-branch-tablebases"])
    assert tablebases.command == "prepare-branch-tablebases"

    census = build_parser().parse_args(["audit-branch-census"])
    assert census.command == "audit-branch-census"

    foundation = build_parser().parse_args(["run-branch-foundation"])
    assert foundation.command == "run-branch-foundation"

    ordinary_audit = build_parser().parse_args(["audit-ordinary-branch-source"])
    assert ordinary_audit.command == "audit-ordinary-branch-source"

    ordinary = build_parser().parse_args(
        ["run-ordinary-branch-foundation", "--stockfish", "stockfish"]
    )
    assert ordinary.command == "run-ordinary-branch-foundation"
    convergence_audit = build_parser().parse_args(["audit-oracle-convergence-source"])
    assert convergence_audit.command == "audit-oracle-convergence-source"
    convergence = build_parser().parse_args(
        ["run-oracle-convergence", "--stockfish", "stockfish"]
    )
    assert convergence.command == "run-oracle-convergence"
    separable_audit = build_parser().parse_args(["audit-branch-separable-source"])
    assert separable_audit.command == "audit-branch-separable-source"
    separable = build_parser().parse_args(
        ["run-branch-separable-oracle", "--stockfish", "stockfish"]
    )
    assert separable.command == "run-branch-separable-oracle"
    adjudication_audit = build_parser().parse_args(
        ["audit-uncertainty-adjudication-source"]
    )
    assert adjudication_audit.command == "audit-uncertainty-adjudication-source"
    adjudication = build_parser().parse_args(
        ["run-uncertainty-adjudication", "--stockfish", "stockfish"]
    )
    assert adjudication.command == "run-uncertainty-adjudication"
    temporal_audit = build_parser().parse_args(["audit-temporal-allocation-source"])
    assert temporal_audit.command == "audit-temporal-allocation-source"
    temporal = build_parser().parse_args(
        ["run-temporal-allocation-adjudication", "--stockfish", "stockfish"]
    )
    assert temporal.command == "run-temporal-allocation-adjudication"
    kpkp = build_parser().parse_args(["audit-kpkp-review-source"])
    assert kpkp.command == "audit-kpkp-review-source"


def test_cli_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "run-baseline" in capsys.readouterr().out


def test_cli_missing_file_returns_error(capsys) -> None:
    assert main(["ingest", "does-not-exist.pgn"]) == 2
    assert "does-not-exist.pgn" in capsys.readouterr().err
