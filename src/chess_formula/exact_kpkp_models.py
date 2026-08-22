from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from threadpoolctl import threadpool_limits


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _round(value: float, places: int) -> float:
    rounded = round(float(value), places)
    return 0.0 if rounded == 0 else rounded


@dataclass(frozen=True)
class FittedCandidate:
    artifact: dict
    training_position_keys: frozenset[str]


def balanced_position_weights(labels: np.ndarray, position_keys: np.ndarray) -> np.ndarray:
    labels = np.asarray(labels, dtype=np.int8)
    position_keys = np.asarray(position_keys)
    weights = np.empty(len(labels), dtype=np.float64)
    for key in np.unique(position_keys):
        mask = position_keys == key
        weights[mask] = 1.0 / int(mask.sum())
    positive = float(weights[labels == 1].sum())
    negative = float(weights[labels == 0].sum())
    if positive <= 0 or negative <= 0:
        raise ValueError("Each training split must contain positive and negative branches")
    weights[labels == 1] *= negative / positive
    return weights


def fit_logistic_candidate(
    features: np.ndarray,
    labels: np.ndarray,
    position_keys: np.ndarray,
    *,
    c_value: float,
    seed: int,
    tolerance: float,
    max_iterations: int,
    decimal_places: int,
    maximum_nonzero: int,
) -> FittedCandidate:
    weights = balanced_position_weights(labels, position_keys)
    model = LogisticRegression(
        C=c_value,
        solver="saga",
        l1_ratio=1.0,
        fit_intercept=True,
        tol=tolerance,
        max_iter=max_iterations,
        random_state=seed,
    )
    with threadpool_limits(limits=1):
        model.fit(features, labels, sample_weight=weights)
    if int(model.n_iter_[0]) >= max_iterations:
        raise RuntimeError("Sparse logistic candidate did not converge")
    coefficients = {
        str(index): _round(value, decimal_places)
        for index, value in enumerate(model.coef_[0])
        if _round(value, decimal_places) != 0
    }
    if len(coefficients) > maximum_nonzero:
        raise RuntimeError(
            f"Sparse logistic candidate has {len(coefficients)} nonzero terms; "
            f"cap is {maximum_nonzero}"
        )
    artifact = {
        "family": "sparse_logistic",
        "schema": "compact-candidate-v1",
        "feature_count": int(features.shape[1]),
        "coefficients": coefficients,
        "intercept": _round(model.intercept_[0], decimal_places),
        "hyperparameters": {
            "C": float(c_value),
            "l1_ratio": 1.0,
            "solver": "saga",
            "tolerance": tolerance,
            "max_iterations": max_iterations,
            "seed": seed,
        },
    }
    return FittedCandidate(artifact, frozenset(map(str, np.unique(position_keys))))


def fit_tree_candidate(
    features: np.ndarray,
    labels: np.ndarray,
    position_keys: np.ndarray,
    *,
    max_depth: int,
    min_samples_leaf: int,
    seed: int,
    decimal_places: int,
    maximum_internal_nodes: int,
) -> FittedCandidate:
    weights = balanced_position_weights(labels, position_keys)
    model = DecisionTreeClassifier(
        criterion="gini",
        splitter="best",
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        random_state=seed,
    )
    with threadpool_limits(limits=1):
        model.fit(features, labels, sample_weight=weights)
    tree = model.tree_
    nodes = []
    internal_nodes = 0
    for node in range(tree.node_count):
        leaf = int(tree.children_left[node]) == int(tree.children_right[node])
        if leaf:
            total = float(tree.value[node][0].sum())
            probability = 0.0 if total == 0 else float(tree.value[node][0][1] / total)
            nodes.append({"leaf_probability": _round(probability, decimal_places)})
        else:
            internal_nodes += 1
            nodes.append(
                {
                    "feature": int(tree.feature[node]),
                    "threshold": _round(tree.threshold[node], decimal_places),
                    "left": int(tree.children_left[node]),
                    "right": int(tree.children_right[node]),
                }
            )
    if internal_nodes > maximum_internal_nodes:
        raise RuntimeError(
            f"Decision tree has {internal_nodes} internal nodes; cap is {maximum_internal_nodes}"
        )
    artifact = {
        "family": "decision_tree",
        "schema": "compact-candidate-v1",
        "feature_count": int(features.shape[1]),
        "nodes": nodes,
        "hyperparameters": {
            "criterion": "gini",
            "splitter": "best",
            "max_depth": max_depth,
            "min_samples_leaf": min_samples_leaf,
            "seed": seed,
        },
    }
    return FittedCandidate(artifact, frozenset(map(str, np.unique(position_keys))))


def _symbolic_expression(index: int, feature_count: int, seed: int) -> dict:
    digest = hashlib.sha256(f"symbolic:{seed}:{index}".encode()).digest()
    first = int.from_bytes(digest[1:5], "big") % feature_count
    second = int.from_bytes(digest[5:9], "big") % feature_count
    third = int.from_bytes(digest[9:13], "big") % feature_count
    unary = ("abs", "negate")[digest[13] % 2]
    binary = ("add", "subtract", "multiply", "minimum", "maximum")[digest[14] % 5]
    form = digest[0] % 4
    if form == 0:
        return {"op": "feature", "index": first}
    if form == 1:
        return {"op": unary, "arg": {"op": "feature", "index": first}}
    left = {"op": "feature", "index": first}
    right = {"op": "feature", "index": second}
    if form == 2:
        return {"op": binary, "left": left, "right": right}
    nested = {"op": unary, "arg": {"op": "feature", "index": third}}
    return {"op": binary, "left": left, "right": nested}


def evaluate_expression(expression: dict, features: np.ndarray) -> np.ndarray:
    operation = expression["op"]
    if operation == "feature":
        return features[:, int(expression["index"])]
    if operation == "abs":
        return np.abs(evaluate_expression(expression["arg"], features))
    if operation == "negate":
        return -evaluate_expression(expression["arg"], features)
    left = evaluate_expression(expression["left"], features)
    right = evaluate_expression(expression["right"], features)
    if operation == "add":
        return left + right
    if operation == "subtract":
        return left - right
    if operation == "multiply":
        return left * right
    if operation == "minimum":
        return np.minimum(left, right)
    if operation == "maximum":
        return np.maximum(left, right)
    raise ValueError(f"Unknown symbolic operation: {operation}")


def _rank_quality(
    scores: np.ndarray, labels: np.ndarray, position_keys: np.ndarray
) -> tuple[int, float]:
    failures = 0
    ranks = []
    for key in np.unique(position_keys):
        mask = position_keys == key
        position_scores = scores[mask]
        position_labels = labels[mask]
        positive_scores = position_scores[position_labels == 1]
        if len(positive_scores) == 0:
            raise ValueError(f"Position {key} has no WDL-optimal branch")
        best_positive = float(np.max(positive_scores))
        failures += int(best_positive < float(np.max(position_scores)))
        ranks.append(1 + int(np.sum(position_scores > best_positive)))
    return failures, float(np.mean(ranks))


def fit_symbolic_candidate(
    features: np.ndarray,
    labels: np.ndarray,
    position_keys: np.ndarray,
    *,
    seed: int,
    candidate_count: int,
    screen_positions: int,
    finalists: int,
) -> FittedCandidate:
    unique_positions = sorted(
        map(str, np.unique(position_keys)),
        key=lambda key: hashlib.sha256(f"symbolic-screen:{seed}:{key}".encode()).hexdigest(),
    )
    screened = set(unique_positions[:screen_positions])
    screen_mask = np.fromiter(
        (str(key) in screened for key in position_keys), dtype=bool, count=len(position_keys)
    )
    ranked = []
    for index in range(candidate_count):
        expression = _symbolic_expression(index, features.shape[1], seed)
        scores = evaluate_expression(expression, features[screen_mask])
        quality = _rank_quality(scores, labels[screen_mask], position_keys[screen_mask])
        serialized = canonical_json(expression)
        ranked.append((quality, len(serialized), serialized, index, expression))
    ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    full_ranked = []
    for _, _, serialized, index, expression in ranked[:finalists]:
        quality = _rank_quality(evaluate_expression(expression, features), labels, position_keys)
        full_ranked.append((quality, len(serialized), serialized, index, expression))
    _, _, _, expression_index, expression = min(full_ranked)
    artifact = {
        "family": "symbolic_score",
        "schema": "compact-candidate-v1",
        "feature_count": int(features.shape[1]),
        "expression": expression,
        "expression_index": expression_index,
        "search": {
            "seed": seed,
            "candidate_count": candidate_count,
            "screen_positions": screen_positions,
            "finalists": finalists,
            "enumeration": "SHA256-indexed symbolic-v1",
        },
    }
    return FittedCandidate(artifact, frozenset(map(str, np.unique(position_keys))))


def evaluate_candidate(artifact: dict, features: np.ndarray) -> np.ndarray:
    family = artifact["family"]
    if int(artifact["feature_count"]) != int(features.shape[1]):
        raise ValueError("Serialized candidate feature count mismatch")
    if family == "sparse_logistic":
        scores = np.full(len(features), float(artifact["intercept"]), dtype=np.float64)
        for index, coefficient in artifact["coefficients"].items():
            scores += features[:, int(index)] * float(coefficient)
        return 1.0 / (1.0 + np.exp(-np.clip(scores, -50, 50)))
    if family == "decision_tree":
        scores = np.empty(len(features), dtype=np.float64)
        for row_index, row in enumerate(features):
            node_index = 0
            while "leaf_probability" not in artifact["nodes"][node_index]:
                node = artifact["nodes"][node_index]
                node_index = (
                    int(node["left"])
                    if row[int(node["feature"])] <= float(node["threshold"])
                    else int(node["right"])
                )
            scores[row_index] = float(artifact["nodes"][node_index]["leaf_probability"])
        return scores
    if family == "symbolic_score":
        return evaluate_expression(artifact["expression"], features).astype(np.float64)
    raise ValueError(f"Unknown compact candidate family: {family}")


def normalized_scores(scores: np.ndarray, *, probability: bool) -> np.ndarray:
    scores = np.asarray(scores, dtype=np.float64)
    if probability:
        return scores
    minimum = float(np.min(scores))
    maximum = float(np.max(scores))
    if minimum == maximum:
        return np.ones_like(scores)
    return (scores - minimum) / (maximum - minimum)


def tune_delta_from_cross_fitted_scores(
    *,
    scores: np.ndarray,
    labels: np.ndarray,
    position_keys: np.ndarray,
    move_ids: np.ndarray,
    deltas: list[float],
    probability: bool,
    dtz_labels: np.ndarray | None = None,
    state_weights: np.ndarray | None = None,
) -> dict:
    """Tunes a margin only from predictions made without the scored positions."""
    candidates = []
    if state_weights is None:
        state_weights = np.ones(len(labels), dtype=np.float64)
    for delta in deltas:
        failures = 0
        retained = legal = dtz_kept = total_state_weight = 0.0
        for key in np.unique(position_keys):
            mask = position_keys == key
            local_scores = normalized_scores(scores[mask], probability=probability)
            local_labels = labels[mask]
            local_moves = move_ids[mask]
            best = float(np.max(local_scores))
            selected = local_scores >= best - delta
            top = min(
                range(len(local_moves)),
                key=lambda index: (-local_scores[index], str(local_moves[index])),
            )
            selected[top] = True
            failures += int(not np.any(local_labels[selected] == 1))
            weight = float(state_weights[mask][0])
            retained += weight * int(selected.sum())
            legal += weight * len(local_labels)
            total_state_weight += weight
            if dtz_labels is not None:
                dtz_kept += weight * int(np.any(dtz_labels[mask][selected] == 1))
        candidates.append(
            {
                "delta": float(delta),
                "wdl_failures": failures,
                "pooled_retained_fraction": retained / legal,
                "dtz_retention": (
                    dtz_kept / total_state_weight if dtz_labels is not None else None
                ),
            }
        )
    zero_error = [candidate for candidate in candidates if candidate["wdl_failures"] == 0]
    eligible = zero_error or candidates
    if zero_error:
        chosen = min(
            eligible,
            key=lambda candidate: (
                candidate["pooled_retained_fraction"],
                -(candidate["dtz_retention"] or 0.0),
                candidate["delta"],
            ),
        )
    else:
        chosen = min(
            eligible,
            key=lambda candidate: (
                candidate["wdl_failures"],
                candidate["pooled_retained_fraction"],
                candidate["delta"],
            ),
        )
    return {
        "status": "eligible" if zero_error else "failed_no_zero_error_setting",
        "chosen": chosen,
        "candidates": candidates,
    }


def cross_fitted_uncertainty_set(
    *,
    evaluation_position_key: str,
    move_ids: list[str],
    outer_full: FittedCandidate,
    inner_models: list[FittedCandidate],
    features: np.ndarray,
    delta: float,
    vote_minimum: int,
) -> set[int]:
    models = [outer_full, *inner_models]
    for model in models:
        if evaluation_position_key in model.training_position_keys:
            raise RuntimeError(
                f"Cross-fit leakage: {evaluation_position_key} appears in model training"
            )
    full_scores = evaluate_candidate(outer_full.artifact, features)
    normalized = normalized_scores(
        full_scores, probability=outer_full.artifact["family"] != "symbolic_score"
    )
    retained = {min(range(len(move_ids)), key=lambda index: (-full_scores[index], move_ids[index]))}
    best = float(np.max(normalized))
    retained.update(np.flatnonzero(normalized >= best - delta).tolist())
    votes = np.zeros(len(move_ids), dtype=np.int64)
    for model in inner_models:
        scores = evaluate_candidate(model.artifact, features)
        best_score = float(np.max(scores))
        votes += scores == best_score
    retained.update(np.flatnonzero(votes >= vote_minimum).tolist())
    return retained


def deployment_uncertainty_set(
    *,
    move_ids: list[str],
    full_development: FittedCandidate,
    outer_models: list[FittedCandidate],
    features: np.ndarray,
    delta: float,
    vote_minimum: int,
) -> set[int]:
    if len(outer_models) != 5:
        raise ValueError("Deployment ensemble requires exactly five outer-fold models")
    full_scores = evaluate_candidate(full_development.artifact, features)
    normalized = normalized_scores(
        full_scores,
        probability=full_development.artifact["family"] != "symbolic_score",
    )
    retained = {min(range(len(move_ids)), key=lambda index: (-full_scores[index], move_ids[index]))}
    best = float(np.max(normalized))
    retained.update(np.flatnonzero(normalized >= best - delta).tolist())
    votes = np.zeros(len(move_ids), dtype=np.int64)
    for model in outer_models:
        scores = evaluate_candidate(model.artifact, features)
        votes += scores == float(np.max(scores))
    retained.update(np.flatnonzero(votes >= vote_minimum).tolist())
    return retained


def artifact_cost(artifact: dict) -> dict[str, int]:
    family = artifact["family"]
    if family == "sparse_logistic":
        terms = len(artifact["coefficients"])
        parameters = terms + 1
        operations = terms * 2 + 3
    elif family == "decision_tree":
        internal = sum("feature" in node for node in artifact["nodes"])
        leaves = len(artifact["nodes"]) - internal
        parameters = internal * 2 + leaves
        operations = int(artifact["hyperparameters"]["max_depth"])
    elif family == "symbolic_score":
        serialized_expression = canonical_json(artifact["expression"])
        parameters = serialized_expression.count('"index"')
        operations = serialized_expression.count('"op"')
    else:
        raise ValueError(f"Unknown compact candidate family: {family}")
    return {
        "parameters": parameters,
        "serialized_bytes": len(canonical_json(artifact).encode()),
        "operations_per_move": operations,
    }


def ensemble_cost(
    artifacts: list[dict], *, shared_feature_schema: dict | None = None
) -> dict[str, int]:
    costs = [artifact_cost(artifact) for artifact in artifacts]
    serialized = {"models": artifacts}
    if shared_feature_schema is not None:
        serialized["feature_schema"] = shared_feature_schema
    union_operations = len(artifacts) + 2
    return {
        "models": len(artifacts),
        "parameters": sum(cost["parameters"] for cost in costs),
        "serialized_bytes": len(canonical_json(serialized).encode()),
        "operations_per_move": sum(cost["operations_per_move"] for cost in costs)
        + union_operations,
        "selector_union_operations_per_move": union_operations,
    }


def measure_deployment_latency(
    *,
    move_ids: list[str],
    full_development: FittedCandidate,
    outer_models: list[FittedCandidate],
    features: np.ndarray,
    delta: float,
    vote_minimum: int,
    repeats: int,
) -> dict[str, float | int]:
    if repeats <= 0:
        raise ValueError("Latency repeats must be positive")
    samples = []
    for _ in range(repeats):
        started = time.perf_counter_ns()
        deployment_uncertainty_set(
            move_ids=move_ids,
            full_development=full_development,
            outer_models=outer_models,
            features=features,
            delta=delta,
            vote_minimum=vote_minimum,
        )
        samples.append(time.perf_counter_ns() - started)
    return {
        "models": 1 + len(outer_models),
        "repeats": repeats,
        "median_nanoseconds_per_position": float(np.median(samples)),
        "mean_nanoseconds_per_position": float(np.mean(samples)),
    }


def family_hyperparameters(config: dict, family: str) -> list[dict]:
    settings = config["experiment_021_kpkp_review"]["candidate_algorithms"][family]
    if family == "sparse_logistic":
        return [{"C": float(value)} for value in settings["c_grid"]]
    if family == "decision_tree":
        return [
            {"max_depth": int(depth), "min_samples_leaf": int(leaf)}
            for depth in settings["max_depth_grid"]
            for leaf in settings["min_samples_leaf_grid"]
        ]
    if family == "symbolic_score":
        return [{}]
    raise ValueError(f"Unknown compact candidate family: {family}")


def fit_family_candidate(
    family: str,
    features: np.ndarray,
    labels: np.ndarray,
    position_keys: np.ndarray,
    hyperparameters: dict,
    config: dict,
) -> FittedCandidate:
    experiment = config["experiment_021_kpkp_review"]
    settings = experiment["candidate_algorithms"][family]
    seed = int(experiment["candidate_seed"])
    places = int(experiment["serialization"]["decimal_places"])
    if family == "sparse_logistic":
        return fit_logistic_candidate(
            features,
            labels,
            position_keys,
            c_value=float(hyperparameters["C"]),
            seed=seed,
            tolerance=float(settings["tolerance"]),
            max_iterations=int(settings["max_iterations"]),
            decimal_places=places,
            maximum_nonzero=int(settings["maximum_nonzero_coefficients"]),
        )
    if family == "decision_tree":
        return fit_tree_candidate(
            features,
            labels,
            position_keys,
            max_depth=int(hyperparameters["max_depth"]),
            min_samples_leaf=int(hyperparameters["min_samples_leaf"]),
            seed=seed,
            decimal_places=places,
            maximum_internal_nodes=int(settings["maximum_internal_nodes"]),
        )
    if family == "symbolic_score":
        return fit_symbolic_candidate(
            features,
            labels,
            position_keys,
            seed=seed,
            candidate_count=int(settings["enumerated_expressions"]),
            screen_positions=int(settings["screen_positions"]),
            finalists=int(settings["full_training_finalists"]),
        )
    raise ValueError(f"Unknown compact candidate family: {family}")


def _fit_mask(
    family: str,
    features: np.ndarray,
    labels: np.ndarray,
    position_keys: np.ndarray,
    mask: np.ndarray,
    hyperparameters: dict,
    config: dict,
) -> FittedCandidate:
    return fit_family_candidate(
        family,
        features[mask],
        labels[mask],
        position_keys[mask],
        hyperparameters,
        config,
    )


def cross_fitted_family_evaluation(
    *,
    family: str,
    features: np.ndarray,
    labels: np.ndarray,
    dtz_labels: np.ndarray,
    position_keys: np.ndarray,
    move_ids: np.ndarray,
    state_weights: np.ndarray,
    outer_assignments: dict[str, int],
    inner_assignments: dict[int, dict[str, int]],
    config: dict,
) -> dict:
    """Runs the frozen nested protocol without ever scoring a training position."""
    position_keys = np.asarray(position_keys).astype(str)
    move_ids = np.asarray(move_ids).astype(str)
    retained = np.zeros(len(labels), dtype=bool)
    outer_reports = []
    outer_models = []
    deltas = list(config["experiment_021_kpkp_review"]["uncertainty_set"]["delta_grid"])
    vote_minimum = int(config["experiment_021_kpkp_review"]["uncertainty_set"]["fold_vote_minimum"])
    for held_out in range(5):
        validation_positions = {key for key, fold in outer_assignments.items() if fold == held_out}
        validation_mask = np.fromiter(
            (key in validation_positions for key in position_keys),
            dtype=bool,
            count=len(position_keys),
        )
        outer_training_mask = ~validation_mask
        candidates = []
        rejected = []
        for hyperparameters in family_hyperparameters(config, family):
            inner_scores = np.full(len(labels), np.nan, dtype=np.float64)
            inner_artifacts = []
            try:
                for inner_fold in range(4):
                    inner_validation_positions = {
                        key
                        for key, fold in inner_assignments[held_out].items()
                        if fold == inner_fold
                    }
                    inner_validation_mask = np.fromiter(
                        (key in inner_validation_positions for key in position_keys),
                        dtype=bool,
                        count=len(position_keys),
                    )
                    inner_training_mask = outer_training_mask & ~inner_validation_mask
                    model = _fit_mask(
                        family,
                        features,
                        labels,
                        position_keys,
                        inner_training_mask,
                        hyperparameters,
                        config,
                    )
                    inner_scores[inner_validation_mask] = evaluate_candidate(
                        model.artifact, features[inner_validation_mask]
                    )
                    inner_artifacts.append(model.artifact)
            except (RuntimeError, ValueError) as exc:
                rejected.append({"hyperparameters": hyperparameters, "reason": str(exc)})
                continue
            if np.isnan(inner_scores[outer_training_mask]).any():
                raise RuntimeError(f"Incomplete inner cross-fit for outer fold {held_out}")
            try:
                outer_candidate_full = _fit_mask(
                    family,
                    features,
                    labels,
                    position_keys,
                    outer_training_mask,
                    hyperparameters,
                    config,
                )
            except (RuntimeError, ValueError) as exc:
                rejected.append({"hyperparameters": hyperparameters, "reason": str(exc)})
                continue
            delta_result = tune_delta_from_cross_fitted_scores(
                scores=inner_scores[outer_training_mask],
                labels=labels[outer_training_mask],
                dtz_labels=dtz_labels[outer_training_mask],
                position_keys=position_keys[outer_training_mask],
                move_ids=move_ids[outer_training_mask],
                state_weights=state_weights[outer_training_mask],
                deltas=deltas,
                probability=family != "symbolic_score",
            )
            chosen = delta_result["chosen"]
            cost = ensemble_cost(
                [outer_candidate_full.artifact, *inner_artifacts],
                shared_feature_schema=config["experiment_021_kpkp_review"]["feature_schema"],
            )
            if delta_result["status"] == "eligible":
                selection_key = (
                    0,
                    chosen["wdl_failures"],
                    chosen["pooled_retained_fraction"],
                    -(chosen["dtz_retention"] or 0.0),
                    cost["serialized_bytes"],
                    canonical_json(hyperparameters),
                )
            else:
                selection_key = (
                    1,
                    chosen["wdl_failures"],
                    chosen["pooled_retained_fraction"],
                    chosen["delta"],
                    cost["serialized_bytes"],
                    canonical_json(hyperparameters),
                )
            candidates.append(
                {
                    "hyperparameters": hyperparameters,
                    "delta_result": delta_result,
                    "inner_ensemble_cost": cost,
                    "selection_key": selection_key,
                }
            )
        if not candidates:
            raise RuntimeError(
                f"Every {family} setting was rejected in outer fold {held_out}: {rejected}"
            )
        selected = min(candidates, key=lambda candidate: candidate["selection_key"])
        hyperparameters = selected["hyperparameters"]
        outer_full = _fit_mask(
            family,
            features,
            labels,
            position_keys,
            outer_training_mask,
            hyperparameters,
            config,
        )
        inner_models = []
        for inner_fold in range(4):
            excluded = {
                key for key, fold in inner_assignments[held_out].items() if fold == inner_fold
            }
            training_mask = outer_training_mask & np.fromiter(
                (key not in excluded for key in position_keys),
                dtype=bool,
                count=len(position_keys),
            )
            inner_models.append(
                _fit_mask(
                    family,
                    features,
                    labels,
                    position_keys,
                    training_mask,
                    hyperparameters,
                    config,
                )
            )
        for key in sorted(validation_positions):
            mask = position_keys == key
            local_indices = np.flatnonzero(mask)
            selected_indices = cross_fitted_uncertainty_set(
                evaluation_position_key=key,
                move_ids=move_ids[mask].tolist(),
                outer_full=outer_full,
                inner_models=inner_models,
                features=features[mask],
                delta=float(selected["delta_result"]["chosen"]["delta"]),
                vote_minimum=vote_minimum,
            )
            retained[local_indices[list(selected_indices)]] = True
        outer_models.append(outer_full)
        outer_reports.append(
            {
                "outer_fold": held_out,
                "status": selected["delta_result"]["status"],
                "hyperparameters": hyperparameters,
                "delta": selected["delta_result"]["chosen"]["delta"],
                "ensemble_cost": ensemble_cost(
                    [outer_full.artifact, *(model.artifact for model in inner_models)],
                    shared_feature_schema=config["experiment_021_kpkp_review"]["feature_schema"],
                ),
                "rejected_settings": rejected,
            }
        )
    return {
        "family": family,
        "retained": retained,
        "outer_reports": outer_reports,
        "outer_models": outer_models,
        "eligible": all(report["status"] == "eligible" for report in outer_reports),
    }


def fit_deployment_ensemble(
    *,
    family: str,
    features: np.ndarray,
    labels: np.ndarray,
    position_keys: np.ndarray,
    outer_assignments: dict[str, int],
    hyperparameters: dict,
    config: dict,
) -> dict:
    """Allowed only after pooled outer evaluation has selected one setting."""
    position_keys = np.asarray(position_keys).astype(str)
    full_mask = np.ones(len(labels), dtype=bool)
    full = _fit_mask(
        family,
        features,
        labels,
        position_keys,
        full_mask,
        hyperparameters,
        config,
    )
    outer_models = []
    for held_out in range(5):
        training_positions = {key for key, fold in outer_assignments.items() if fold != held_out}
        training_mask = np.fromiter(
            (key in training_positions for key in position_keys),
            dtype=bool,
            count=len(position_keys),
        )
        outer_models.append(
            _fit_mask(
                family,
                features,
                labels,
                position_keys,
                training_mask,
                hyperparameters,
                config,
            )
        )
    artifacts = [full.artifact, *(model.artifact for model in outer_models)]
    serialized = {
        "feature_schema": config["experiment_021_kpkp_review"]["feature_schema"],
        "models": artifacts,
    }
    return {
        "full_development": full,
        "outer_models": outer_models,
        "cost": ensemble_cost(
            artifacts,
            shared_feature_schema=config["experiment_021_kpkp_review"]["feature_schema"],
        ),
        "serialized_ensemble": canonical_json(serialized),
    }


def deployment_setting_from_outer_reports(outer_reports: list[dict]) -> dict:
    if len(outer_reports) != 5:
        raise ValueError("Deployment setting requires exactly five outer reports")
    identifiers = [canonical_json(report["hyperparameters"]) for report in outer_reports]
    chosen_identifier = min(
        set(identifiers), key=lambda identifier: (-identifiers.count(identifier), identifier)
    )
    return {
        "hyperparameters": json.loads(chosen_identifier),
        "delta": max(float(report["delta"]) for report in outer_reports),
        "rule": "modal outer-selected hyperparameters with lexical tie; maximum outer delta",
    }


def exact_decision_metrics(
    *,
    retained: np.ndarray,
    wdl_optimal: np.ndarray,
    dtz_optimal: np.ndarray,
    position_keys: np.ndarray,
    state_weights: np.ndarray,
) -> dict[str, float | int]:
    weighted_retained = weighted_legal = weighted_context = 0.0
    total_weight = wdl_kept = dtz_kept = 0.0
    failures = 0
    for key in np.unique(position_keys):
        mask = position_keys == key
        weight = float(state_weights[mask][0])
        if not np.all(state_weights[mask] == weight):
            raise ValueError(f"State weight differs within position {key}")
        local_retained = retained[mask]
        legal = int(mask.sum())
        kept = int(local_retained.sum())
        preserves_wdl = bool(np.any(wdl_optimal[mask][local_retained]))
        preserves_dtz = bool(np.any(dtz_optimal[mask][local_retained]))
        failures += int(not preserves_wdl)
        wdl_kept += weight * int(preserves_wdl)
        dtz_kept += weight * int(preserves_dtz)
        weighted_retained += weight * kept
        weighted_legal += weight * legal
        weighted_context += weight * kept / legal
        total_weight += weight
    return {
        "wdl_failures": failures,
        "weighted_wdl_retention": wdl_kept / total_weight,
        "weighted_dtz_retention": dtz_kept / total_weight,
        "population_pooled_rho": weighted_retained / weighted_legal,
        "population_mean_context_rho": weighted_context / total_weight,
    }


def ordering_rho_perfect(
    *,
    scores: np.ndarray,
    wdl_optimal: np.ndarray,
    position_keys: np.ndarray,
    move_ids: np.ndarray,
    state_weights: np.ndarray,
) -> float:
    retained = weighted_legal = 0.0
    for key in np.unique(position_keys):
        mask = position_keys == key
        weight = float(state_weights[mask][0])
        local_scores = scores[mask]
        local_wdl = wdl_optimal[mask]
        local_moves = move_ids[mask]
        order = sorted(
            range(len(local_moves)),
            key=lambda index: (-local_scores[index], str(local_moves[index])),
        )
        optimal_ranks = [
            index for index, move_index in enumerate(order, 1) if local_wdl[move_index]
        ]
        if not optimal_ranks:
            raise ValueError(f"Position {key} has no WDL-optimal branch")
        prefix = optimal_ranks[0]
        retained += weight * prefix
        weighted_legal += weight * len(local_moves)
    return retained / weighted_legal


def select_best_deployable_baseline(reports: list[dict]) -> dict:
    allowed = {"forcing", "all-captures", "locked-3"}
    candidates = [report for report in reports if report["baseline"] in allowed]
    if {report["baseline"] for report in candidates} != allowed:
        raise ValueError("Baseline comparison requires forcing, all-captures, and locked-3")
    return min(
        candidates,
        key=lambda report: (
            report["rho_perfect"],
            -report["weighted_dtz_retention"],
            report["serialized_bytes"],
            report["operations"],
            report["baseline"],
        ),
    )
