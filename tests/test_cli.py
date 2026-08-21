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


def test_cli_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "run-baseline" in capsys.readouterr().out


def test_cli_missing_file_returns_error(capsys) -> None:
    assert main(["ingest", "does-not-exist.pgn"]) == 2
    assert "does-not-exist.pgn" in capsys.readouterr().err
