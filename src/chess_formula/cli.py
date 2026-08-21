from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .benchmark import benchmark_linear
from .config import load_config
from .confirmation import run_transfer_confirmation
from .corpus import generate_corpus
from .failures import run_failure_mining
from .human_corpus import prepare_human_corpus
from .ingest import ingest_pgn
from .march import run_march_validation
from .model import train_linear
from .oracle import label_positions
from .selection import run_nested_selection
from .stability import run_stability


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

    corpus = subparsers.add_parser(
        "generate-corpus", help="Generate a deterministic legal stability corpus"
    )
    corpus.add_argument("--output", required=True, help="Generated PGN path")
    corpus.add_argument("--stockfish", help="Optional Stockfish path for constrained self-play")
    corpus.add_argument("--games", type=int, help="Override configured game count")
    corpus.add_argument("--max-plies", type=int, help="Override configured maximum plies")

    stability = subparsers.add_parser(
        "stability", help="Run repeated game-grouped coefficient stability analysis"
    )
    stability.add_argument("model", choices=["baseline-linear"])
    stability.add_argument("--engine-key")

    subparsers.add_parser(
        "prepare-human-corpus",
        help="Download, verify, and select a licensed human PGN sample",
    )
    selection = subparsers.add_parser(
        "select-features",
        help="Run leakage-safe nested game-grouped feature selection",
    )
    selection.add_argument("--engine-key")
    confirmation = subparsers.add_parser(
        "confirm-subset",
        help="Evaluate a frozen January-trained subset on confirmation data",
    )
    confirmation.add_argument("--training-database")
    confirmation.add_argument("--engine-key")
    failures = subparsers.add_parser(
        "mine-failures",
        help="Cluster frozen confirmation failures and build a local explorer",
    )
    failures.add_argument("--training-database")
    failures.add_argument("--engine-key")
    march = subparsers.add_parser(
        "validate-march",
        help="Run the frozen pooled-development compact-rule validation",
    )
    march.add_argument("--development-database", action="append")
    march.add_argument("--engine-key")
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
        elif args.command == "generate-corpus":
            corpus = config.get("corpus", {})
            _print(
                generate_corpus(
                    args.output,
                    games=args.games or int(corpus.get("games", 36)),
                    max_plies=args.max_plies or int(corpus.get("max_plies", 72)),
                    seed=int(config["seed"]),
                    opening_random_plies=int(corpus.get("opening_random_plies", 6)),
                    stockfish_path=args.stockfish,
                    engine_nodes_per_move=int(corpus.get("engine_nodes_per_move", 100)),
                )
            )
        elif args.command == "stability":
            result, artifact = run_stability(database, config, engine_key=args.engine_key)
            compact = {
                label: summary["metrics"] for label, summary in result["feature_sets"].items()
            }
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "games": result["games"],
                    "positions": result["positions"],
                    "feature_sets": compact,
                }
            )
        elif args.command == "prepare-human-corpus":
            if "human_corpus" not in config:
                raise ValueError("The active configuration has no human_corpus section")
            _print(prepare_human_corpus(config))
        elif args.command == "select-features":
            if "feature_selection" not in config:
                raise ValueError("The active configuration has no feature_selection section")
            result, artifact = run_nested_selection(
                database, config, engine_key=args.engine_key
            )
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "consensus_lock": result["consensus_lock"],
                    "nested_performance": result["nested_performance"],
                }
            )
        elif args.command == "confirm-subset":
            if "confirmation" not in config:
                raise ValueError("The active configuration has no confirmation section")
            training_database = (
                args.training_database or config["confirmation"]["training_database"]
            )
            result, artifact = run_transfer_confirmation(
                training_database,
                database,
                config,
                engine_key=args.engine_key,
            )
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "positions": result["confirmation_positions"],
                    "excluded_overlaps": result["cross_month_positions_excluded"],
                    "models": {
                        label: model["metrics"] for label, model in result["models"].items()
                    },
                    "paired_mae_deltas": result["paired_mae_deltas"],
                }
            )
        elif args.command == "mine-failures":
            if "failure_mining" not in config:
                raise ValueError("The active configuration has no failure_mining section")
            training_database = (
                args.training_database or config["failure_mining"]["training_database"]
            )
            result, artifact = run_failure_mining(
                training_database,
                database,
                config,
                engine_key=args.engine_key,
            )
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "candidate_positions": result["candidate_positions"],
                    "candidate_games": result["candidate_games"],
                    "clusters": result["clusters"],
                    "explorer": str(artifact / "failure_explorer.html"),
                }
            )
        elif args.command == "validate-march":
            if "march_validation" not in config:
                raise ValueError("The active configuration has no march_validation section")
            development_databases = (
                args.development_database
                or config["march_validation"]["development_databases"]
            )
            result, artifact = run_march_validation(
                development_databases,
                database,
                config,
                engine_key=args.engine_key,
            )
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "positions": result["confirmation_positions"],
                    "excluded_overlaps": result["cross_domain_positions_excluded"],
                    "models": {
                        label: model["metrics"] for label, model in result["models"].items()
                    },
                    "paired_mae_deltas": result["paired_mae_deltas"],
                    "decisions": result["decisions"],
                }
            )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
