from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .benchmark import benchmark_linear
from .branch_law import (
    audit_exact_census,
    prepare_branch_tablebases,
    run_branch_law_foundation,
)
from .branch_separable_oracle import (
    audit_branch_separable_source,
    run_branch_separable_oracle,
)
from .budget_curve import run_fixed_budget_curve
from .config import load_config
from .confirmation import run_transfer_confirmation
from .corpus import generate_corpus
from .failures import run_failure_mining
from .human_corpus import prepare_human_corpus
from .ingest import ingest_pgn
from .loss_audit import run_uci_loss_audit
from .march import run_march_validation
from .model import train_linear
from .move_policy import run_move_policy_validation
from .oracle import label_positions
from .oracle_convergence import (
    audit_oracle_convergence_source,
    run_oracle_convergence,
)
from .ordinary_branch import (
    audit_ordinary_branch_source,
    run_ordinary_branch_foundation,
)
from .robustness import run_depth_robustness
from .search_frontier import run_search_frontier
from .selection import run_nested_selection
from .stability import run_stability
from .uci_confirmation import run_forcing_3_confirmation
from .uci_match import run_uci_pilot
from .uncertainty_adjudication import (
    audit_uncertainty_adjudication_source,
    run_uncertainty_adjudication,
)


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
    depth = subparsers.add_parser(
        "validate-depth",
        help="Test the frozen searched formula against a deeper oracle",
    )
    depth.add_argument("--development-database", action="append")
    depth.add_argument("--prior-database", action="append")
    moves = subparsers.add_parser(
        "validate-moves",
        help="Evaluate deterministic legal move policies against a frozen oracle",
    )
    moves.add_argument("--stockfish", required=True)
    moves.add_argument("--development-database", action="append")
    moves.add_argument("--prior-database", action="append")
    pilot = subparsers.add_parser(
        "run-uci-pilot",
        help="Run the frozen color-balanced UCI playing-strength pilot",
    )
    pilot.add_argument("--stockfish", required=True)
    audit = subparsers.add_parser(
        "audit-uci-losses",
        help="Audit the first major errors in lost UCI pilot games",
    )
    audit.add_argument("--stockfish", required=True)
    frontier = subparsers.add_parser(
        "run-search-frontier",
        help="Compare preregistered loss-derived search extensions",
    )
    frontier.add_argument("--stockfish", required=True)
    confirmation = subparsers.add_parser(
        "confirm-forcing-3",
        help="Run the frozen untouched Forcing-3 UCI confirmation",
    )
    confirmation.add_argument("--stockfish", required=True)
    curve = subparsers.add_parser(
        "run-budget-curve",
        help="Run the preregistered fixed-budget search-efficiency curve",
    )
    curve.add_argument("--stockfish", required=True)
    tablebases = subparsers.add_parser(
        "prepare-branch-tablebases",
        help="Download and verify frozen three-piece Syzygy files without probing outcomes",
    )
    tablebases.add_argument("--directory", help="Override configured tablebase directory")
    subparsers.add_parser(
        "audit-branch-census",
        help="Audit the exact legal-state census without probing tablebase outcomes",
    )
    foundation = subparsers.add_parser(
        "run-branch-foundation",
        help="Run the frozen development-only exact branch-budget foundation",
    )
    foundation.add_argument("--tablebase-dir", help="Override configured tablebase directory")
    subparsers.add_parser(
        "audit-ordinary-branch-source",
        help="Audit the frozen ordinary branch source without probing outcomes",
    )
    ordinary = subparsers.add_parser(
        "run-ordinary-branch-foundation",
        help="Run the frozen development-only ordinary opponent-reply foundation",
    )
    ordinary.add_argument("--stockfish", required=True)
    subparsers.add_parser(
        "audit-oracle-convergence-source",
        help="Audit the frozen Experiment 017 development contexts without probing outcomes",
    )
    convergence = subparsers.add_parser(
        "run-oracle-convergence",
        help="Run the frozen ordinary branch-oracle convergence calibration",
    )
    convergence.add_argument("--stockfish", required=True)
    subparsers.add_parser(
        "audit-branch-separable-source",
        help="Audit Experiment 018 contexts and legal moves without probing outcomes",
    )
    separable = subparsers.add_parser(
        "run-branch-separable-oracle",
        help="Run the frozen independent per-legal-move oracle calibration",
    )
    separable.add_argument("--stockfish", required=True)
    subparsers.add_parser(
        "audit-uncertainty-adjudication-source",
        help="Audit the frozen Experiment 019 union and sources without new outcomes",
    )
    adjudication = subparsers.add_parser(
        "run-uncertainty-adjudication",
        help="Run the frozen 640k independent conservative-union audit",
    )
    adjudication.add_argument("--stockfish", required=True)
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
            result, artifact = run_nested_selection(database, config, engine_key=args.engine_key)
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
                args.development_database or config["march_validation"]["development_databases"]
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
        elif args.command == "validate-depth":
            if "depth_robustness" not in config:
                raise ValueError("The active configuration has no depth_robustness section")
            settings = config["depth_robustness"]
            result, artifact = run_depth_robustness(
                args.development_database or settings["development_databases"],
                args.prior_database or settings["prior_databases"],
                database,
                config,
            )
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "positions": result["confirmation_positions"],
                    "excluded_overlaps": result["prior_domain_positions_excluded"],
                    "models": {
                        label: model["metrics"] for label, model in result["models"].items()
                    },
                    "paired_mae_deltas": result["paired_mae_deltas"],
                    "decision": result["decision"],
                }
            )
        elif args.command == "validate-moves":
            if "move_policy" not in config:
                raise ValueError("The active configuration has no move_policy section")
            settings = config["move_policy"]
            result, artifact = run_move_policy_validation(
                args.development_database or settings["development_databases"],
                args.prior_database or settings["prior_databases"],
                database,
                args.stockfish,
                config,
            )
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "positions": result["confirmation_positions"],
                    "excluded_overlaps": result["prior_domain_positions_excluded"],
                    "models": {
                        label: model["metrics"] for label, model in result["models"].items()
                    },
                    "paired_regret_deltas": result["paired_regret_deltas"],
                    "decision": result["decision"],
                }
            )
        elif args.command == "run-uci-pilot":
            if "uci_pilot" not in config:
                raise ValueError("The active configuration has no uci_pilot section")
            result, artifact = run_uci_pilot(args.stockfish, config)
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "games": result["games"],
                    "matches": result["matches"],
                    "decision": result["decision"],
                }
            )
        elif args.command == "audit-uci-losses":
            if "uci_loss_audit" not in config:
                raise ValueError("The active configuration has no uci_loss_audit section")
            result, artifact = run_uci_loss_audit(args.stockfish, config)
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "explorer": str(artifact / "loss_explorer.html"),
                    "lost_games": result["lost_games"],
                    "candidate_turns": result["candidate_turns"],
                    "first_error_reply_classes": result["first_error_reply_classes"],
                    "first_error_best_move_kinds": result["first_error_best_move_kinds"],
                }
            )
        elif args.command == "run-search-frontier":
            if "search_frontier" not in config:
                raise ValueError("The active configuration has no search_frontier section")
            result, artifact = run_search_frontier(args.stockfish, config)
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "positions": result["positions"],
                    "models": {
                        label: {
                            "mean_regret_cp": model["metrics"]["mean_regret_cp"],
                            "mean_total_states": model["complexity"]["mean_total_states"],
                        }
                        for label, model in result["models"].items()
                    },
                    "decision": result["decision"],
                }
            )
        elif args.command == "confirm-forcing-3":
            if "uci_confirmation" not in config:
                raise ValueError("The active configuration has no uci_confirmation section")
            result, artifact = run_forcing_3_confirmation(args.stockfish, config)
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "games": result["games"],
                    "matches": result["matches"],
                    "decision": result["decision"],
                }
            )
        elif args.command == "run-budget-curve":
            if "budget_curve" not in config:
                raise ValueError("The active configuration has no budget_curve section")
            result, artifact = run_fixed_budget_curve(args.stockfish, config)
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "development_positions": result["development_positions"],
                    "models": result["models"],
                    "game_matches": result["game_matches"],
                    "decision": result["decision"],
                }
            )
        elif args.command == "prepare-branch-tablebases":
            if "branch_law_foundation" not in config:
                raise ValueError("The active configuration has no branch_law_foundation section")
            _print(prepare_branch_tablebases(config, directory=args.directory))
        elif args.command == "audit-branch-census":
            if "branch_law_foundation" not in config:
                raise ValueError("The active configuration has no branch_law_foundation section")
            _print(audit_exact_census(config))
        elif args.command == "run-branch-foundation":
            if "branch_law_foundation" not in config:
                raise ValueError("The active configuration has no branch_law_foundation section")
            result, artifact = run_branch_law_foundation(
                config,
                tablebase_directory=args.tablebase_dir,
            )
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "development_positions": result["development_positions"],
                    "development_branches": result["development_branches"],
                    "selection_outcomes_probed": result["selection_outcomes_probed"],
                    "confirmation_outcomes_probed": result["confirmation_outcomes_probed"],
                    "domains": result["domains"],
                }
            )
        elif args.command == "audit-ordinary-branch-source":
            _print(audit_ordinary_branch_source(config))
        elif args.command == "run-ordinary-branch-foundation":
            result, artifact = run_ordinary_branch_foundation(
                args.stockfish,
                config,
            )
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "source_positions": result["source_audit"]["positions"],
                    "root_candidates": result["source_audit"]["candidate_contexts"],
                    "opponent_replies": result["source_audit"][
                        "opponent_reply_records"
                    ],
                    "selection_outcomes_probed": result[
                        "selection_outcomes_probed"
                    ],
                    "confirmation_outcomes_probed": result[
                        "confirmation_outcomes_probed"
                    ],
                    "curves": result["curves"],
                }
            )
        elif args.command == "audit-oracle-convergence-source":
            _print(audit_oracle_convergence_source(config))
        elif args.command == "run-oracle-convergence":
            result, artifact = run_oracle_convergence(args.stockfish, config)
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "contexts": result["source_audit"]["contexts"],
                    "oracle": result["oracle"],
                    "decision": result["convergence"]["decision"],
                    "cross_cost_rule": result["convergence"]["cross_cost_rule"],
                }
            )
        elif args.command == "audit-branch-separable-source":
            _print(audit_branch_separable_source(config))
        elif args.command == "run-branch-separable-oracle":
            result, artifact = run_branch_separable_oracle(args.stockfish, config)
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "contexts": result["source_audit"]["contexts"],
                    "legal_branches_per_tier": result["source_audit"][
                        "legal_branches"
                    ],
                    "oracle": result["oracle"],
                    "decision": result["measurement"]["decision"],
                }
            )
        elif args.command == "audit-uncertainty-adjudication-source":
            _print(audit_uncertainty_adjudication_source(config))
        elif args.command == "run-uncertainty-adjudication":
            result, artifact = run_uncertainty_adjudication(args.stockfish, config)
            _print(
                {
                    "experiment_id": result["experiment_id"],
                    "artifact": str(artifact),
                    "contexts": result["source_audit"]["contexts"],
                    "legal_branches": result["source_audit"]["legal_branches"],
                    "frozen_union_branches": result["source_audit"][
                        "retained_branches"
                    ],
                    "oracle": result["oracle"],
                    "decision": result["measurement"]["decision"],
                }
            )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
