from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from chess_formula.config import load_config
from chess_formula.exact_kpkp_models import (
    FittedCandidate,
    cross_fitted_family_evaluation,
    cross_fitted_uncertainty_set,
    deployment_setting_from_outer_reports,
    deployment_uncertainty_set,
    ensemble_cost,
    evaluate_candidate,
    exact_decision_metrics,
    fit_deployment_ensemble,
    fit_logistic_candidate,
    fit_symbolic_candidate,
    fit_tree_candidate,
    measure_deployment_latency,
    ordering_rho_perfect,
    select_best_deployable_baseline,
    tune_delta_from_cross_fitted_scores,
)


def _training_data() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    features = np.asarray([[0, 0], [1, 0], [0, 1], [1, 1], [0.1, 0], [0.9, 1]], dtype=float)
    labels = np.asarray([0, 1, 0, 1, 0, 1], dtype=np.int8)
    positions = np.asarray(["a", "a", "b", "b", "c", "c"])
    return features, labels, positions


def test_pinned_candidate_families_fit_and_score_serialized_artifacts() -> None:
    features, labels, positions = _training_data()
    logistic = fit_logistic_candidate(
        features,
        labels,
        positions,
        c_value=1,
        seed=7,
        tolerance=1e-4,
        max_iterations=5000,
        decimal_places=6,
        maximum_nonzero=8,
    )
    tree = fit_tree_candidate(
        features,
        labels,
        positions,
        max_depth=2,
        min_samples_leaf=1,
        seed=7,
        decimal_places=6,
        maximum_internal_nodes=3,
    )
    symbolic = fit_symbolic_candidate(
        features,
        labels,
        positions,
        seed=7,
        candidate_count=32,
        screen_positions=2,
        finalists=4,
    )
    for candidate in (logistic, tree, symbolic):
        scores = evaluate_candidate(candidate.artifact, features)
        assert scores.shape == (6,)
        assert np.isfinite(scores).all()


def test_cross_fitted_selector_rejects_evaluation_training_overlap() -> None:
    artifact = {
        "family": "symbolic_score",
        "schema": "compact-candidate-v1",
        "feature_count": 1,
        "expression": {"op": "feature", "index": 0},
        "expression_index": 0,
        "search": {},
    }
    safe = FittedCandidate(artifact, frozenset({"train"}))
    leaked = FittedCandidate(artifact, frozenset({"held-out"}))
    retained = cross_fitted_uncertainty_set(
        evaluation_position_key="held-out",
        move_ids=["a1a2", "a1b1"],
        outer_full=safe,
        inner_models=[safe, safe, safe, safe],
        features=np.asarray([[0.1], [0.9]]),
        delta=0,
        vote_minimum=2,
    )
    assert retained == {1}
    with pytest.raises(RuntimeError, match="Cross-fit leakage"):
        cross_fitted_uncertainty_set(
            evaluation_position_key="held-out",
            move_ids=["a1a2", "a1b1"],
            outer_full=leaked,
            inner_models=[safe, safe, safe, safe],
            features=np.asarray([[0.1], [0.9]]),
            delta=0,
            vote_minimum=2,
        )


def test_deployment_ensemble_and_cost_count_every_fit() -> None:
    artifact = {
        "family": "symbolic_score",
        "schema": "compact-candidate-v1",
        "feature_count": 1,
        "expression": {"op": "feature", "index": 0},
        "expression_index": 0,
        "search": {},
    }
    model = FittedCandidate(artifact, frozenset({"development"}))
    retained = deployment_uncertainty_set(
        move_ids=["a1a2", "a1b1"],
        full_development=model,
        outer_models=[model] * 5,
        features=np.asarray([[0.1], [0.9]]),
        delta=0,
        vote_minimum=2,
    )
    assert retained == {1}
    cost = ensemble_cost([artifact] * 6)
    assert cost["models"] == 6
    assert cost["parameters"] == 6
    assert cost["operations_per_move"] == 14
    latency = measure_deployment_latency(
        move_ids=["a1a2", "a1b1"],
        full_development=model,
        outer_models=[model] * 5,
        features=np.asarray([[0.1], [0.9]]),
        delta=0,
        vote_minimum=2,
        repeats=2,
    )
    assert latency["models"] == 6


def test_delta_tuning_fails_closed_without_zero_error_setting() -> None:
    result = tune_delta_from_cross_fitted_scores(
        scores=np.asarray([0.9, 0.1, 0.9, 0.1]),
        labels=np.asarray([0, 1, 0, 1]),
        position_keys=np.asarray(["a", "a", "b", "b"]),
        move_ids=np.asarray(["a1", "a2", "b1", "b2"]),
        deltas=[0, 0.1],
        probability=True,
    )
    assert result["status"] == "failed_no_zero_error_setting"


def test_nested_tree_pipeline_and_six_fit_deployment_are_executable() -> None:
    config = deepcopy(load_config("configs/experiment-021-kpkp-review.json"))
    experiment = config["experiment_021_kpkp_review"]
    experiment["candidate_algorithms"]["decision_tree"]["max_depth_grid"] = [2]
    experiment["candidate_algorithms"]["decision_tree"]["min_samples_leaf_grid"] = [1]
    experiment["uncertainty_set"]["delta_grid"] = [0, 1]
    features = []
    labels = []
    positions = []
    moves = []
    for position in range(5):
        features.extend(([0.0, position / 5], [1.0, position / 5]))
        labels.extend((0, 1))
        positions.extend((f"p{position}", f"p{position}"))
        moves.extend(("a1a2", "a1b1"))
    features_array = np.asarray(features)
    labels_array = np.asarray(labels, dtype=np.int8)
    positions_array = np.asarray(positions)
    outer = {f"p{position}": position for position in range(5)}
    inner = {
        held_out: {
            f"p{position}": index
            for index, position in enumerate(
                position for position in range(5) if position != held_out
            )
        }
        for held_out in range(5)
    }
    result = cross_fitted_family_evaluation(
        family="decision_tree",
        features=features_array,
        labels=labels_array,
        dtz_labels=labels_array.copy(),
        position_keys=positions_array,
        move_ids=np.asarray(moves),
        state_weights=np.ones(len(labels_array)),
        outer_assignments=outer,
        inner_assignments=inner,
        config=config,
    )
    assert len(result["outer_reports"]) == 5
    assert result["retained"].shape == labels_array.shape
    setting = deployment_setting_from_outer_reports(result["outer_reports"])
    deployed = fit_deployment_ensemble(
        family="decision_tree",
        features=features_array,
        labels=labels_array,
        position_keys=positions_array,
        outer_assignments=outer,
        hyperparameters=setting["hyperparameters"],
        config=config,
    )
    assert deployed["cost"]["models"] == 6


def test_exact_metrics_and_baseline_ties_use_frozen_denominators() -> None:
    positions = np.asarray(["a", "a", "b", "b", "b"])
    weights = np.asarray([9, 9, 1, 1, 1], dtype=float)
    wdl = np.asarray([False, True, True, False, False])
    dtz = np.asarray([False, True, False, True, False])
    retained = np.asarray([False, True, True, False, False])
    metrics = exact_decision_metrics(
        retained=retained,
        wdl_optimal=wdl,
        dtz_optimal=dtz,
        position_keys=positions,
        state_weights=weights,
    )
    assert metrics["wdl_failures"] == 0
    assert metrics["weighted_dtz_retention"] == 0.9
    rho = ordering_rho_perfect(
        scores=np.asarray([0.1, 0.9, 0.8, 0.7, 0.6]),
        wdl_optimal=wdl,
        position_keys=positions,
        move_ids=np.asarray(["a1", "a2", "b1", "b2", "b3"]),
        state_weights=weights,
    )
    assert rho == 10 / 21
    best = select_best_deployable_baseline(
        [
            {
                "baseline": "forcing",
                "rho_perfect": 0.2,
                "weighted_dtz_retention": 0.8,
                "serialized_bytes": 2,
                "operations": 2,
            },
            {
                "baseline": "all-captures",
                "rho_perfect": 0.2,
                "weighted_dtz_retention": 0.9,
                "serialized_bytes": 3,
                "operations": 3,
            },
            {
                "baseline": "locked-3",
                "rho_perfect": 0.3,
                "weighted_dtz_retention": 1.0,
                "serialized_bytes": 1,
                "operations": 1,
            },
            {
                "baseline": "oracle",
                "rho_perfect": 0.0,
                "weighted_dtz_retention": 1.0,
                "serialized_bytes": 0,
                "operations": 0,
            },
        ]
    )
    assert best["baseline"] == "all-captures"
