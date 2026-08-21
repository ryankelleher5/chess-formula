from __future__ import annotations

import numpy as np

from chess_formula.failures import deterministic_kmeans, failure_candidate_masks


def test_failure_candidate_masks_use_frozen_thresholds() -> None:
    target = np.asarray([0.0, 0.0, 0.0, 0.0])
    locked = np.asarray([299.9, 300.0, 20.0, -500.0])
    full = np.asarray([200.0, 160.0, 170.0, -490.0])
    error, disagreement, candidate = failure_candidate_masks(
        target,
        locked,
        full,
        error_threshold_cp=300.0,
        disagreement_threshold_cp=150.0,
    )
    np.testing.assert_array_equal(error, [False, True, False, True])
    np.testing.assert_array_equal(disagreement, [False, False, True, False])
    np.testing.assert_array_equal(candidate, [False, True, True, True])


def test_deterministic_kmeans_separates_simple_groups() -> None:
    matrix = np.asarray([[-5.0, -5.0], [-4.9, -5.1], [5.0, 5.0], [5.2, 4.8]])
    first_labels, first_centroids = deterministic_kmeans(matrix, 2)
    second_labels, second_centroids = deterministic_kmeans(matrix, 2)
    np.testing.assert_array_equal(first_labels, second_labels)
    np.testing.assert_allclose(first_centroids, second_centroids)
    assert first_labels[0] == first_labels[1]
    assert first_labels[2] == first_labels[3]
    assert first_labels[0] != first_labels[2]
