from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .benchmark import benchmark_linear
from .config import load_config
from .ingest import ingest_pgn
from .model import train_linear
from .oracle import label_positions


def _database(args: argparse.Namespace, config: dict) -> str:
    return args.database or config["database"]


def _print(value: dict) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chess-formula",
        description="Reproducible experiments on compact chess evaluation functions.",
    )
    parser.add_argument("--config", help="JSON configuration override")
    parser.add_argument("--database", help="DuckDB path (overrides configuration)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Extract sampled positions from a PGN")
    ingest.add_argument("pgn", help="PGN, .gz, .bz2, or optional .zst file")

    label = subparsers.add_parser("label", help="Label all uncached positions with Stockfish")
    label.add_argument("--stockfish", required=True, help="Path to a Stockfish executable")
    label.add_argument(
        "--force", action="store_true", help="Explicitly recompute this engine/config cache"
    )

    train = subparsers.add_parser("train", help="Train a candidate evaluator")
    train.add_argument("model", choices=["baseline-linear"])
    train.add_argument("--engine-key")
    train.add_argument("--model-path", default="models/baseline-linear.json")

    benchmark = subparsers.add_parser(
        "benchmark", help="Evaluate a model on the frozen held-out split"
    )
    benchmark.add_argument("model", choices=["baseline-linear"])
    benchmark.add_argument("--model-path", default="models/baseline-linear.json")

    run = subparsers.add_parser(
        "run-baseline", help="Run ingestion, labeling, training, and benchmark"
    )
    run.add_argument("--pgn", required=True)
    run.add_argument("--stockfish", required=True)
    run.add_argument("--model-path", default="models/baseline-linear.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    database = _database(args, config)
    try:
        if args.command == "ingest":
            _print(ingest_pgn(args.pgn, database, config))
        elif args.command == "label":
            _print(label_positions(args.stockfish, database, config, force=args.force))
        elif args.command == "train":
            model, artifact, metadata = train_linear(
                database,
                config,
                model_path=args.model_path,
                engine_key=args.engine_key,
            )
            _print({**metadata, "artifact": str(artifact), "formula": model.formula()})
        elif args.command == "benchmark":
            metrics, artifact = benchmark_linear(database, config, model_path=args.model_path)
            _print({**metrics, "artifact": str(artifact)})
        elif args.command == "run-baseline":
            stockfish = args.stockfish
            if not Path(stockfish).exists():
                resolved = shutil.which(stockfish)
                if resolved:
                    stockfish = resolved
            ingest_stats = ingest_pgn(args.pgn, database, config)
            label_stats = label_positions(stockfish, database, config)
            model, artifact, training = train_linear(database, config, model_path=args.model_path)
            metrics, _ = benchmark_linear(database, config, model_path=args.model_path)
            _print(
                {
                    "ingest": ingest_stats,
                    "label": label_stats,
                    "training": training,
                    "benchmark": metrics,
                    "artifact": str(artifact),
                    "formula": model.formula(),
                }
            )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
