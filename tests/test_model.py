from __future__ import annotations

import numpy as np

from chess_formula.benchmark import _dataset_summary, calculate_metrics
from chess_formula.database import connect_database
from chess_formula.model import LinearModel


def test_model_serialization_and_formula(tmp_path) -> None:
    model = LinearModel(
        name="baseline-linear",
        feature_names=["material", "tempo"],
        coefficients=[100.0, 10.0],
        intercept=2.0,
        ridge_alpha=1.0,
        target_clip_cp=2000,
        engine_key="abc",
        experiment_id="test-001",
    )
    path = tmp_path / "model.json"
    model.save(path)
    loaded = LinearModel.load(path)
    np.testing.assert_allclose(loaded.predict(np.array([[1.0, -1.0]])), [92.0])
    assert "+100.000000 * material" in loaded.formula()


def test_benchmark_metrics() -> None:
    metrics = calculate_metrics(np.array([-100.0, 0.0, 100.0]), np.array([-50.0, 0.0, 150.0]))
    assert metrics["evaluation_mae_cp"] == 100.0 / 3.0
    assert metrics["sign_accuracy"] == 1.0
    assert metrics["catastrophic_error_rate_500cp"] == 0.0


def test_dataset_summary_handles_database_without_labels(tmp_path) -> None:
    connection = connect_database(tmp_path / "empty.duckdb")
    summary = _dataset_summary(connection, "missing-engine")
    assert summary["games"] == 0
    assert summary["stockfish"]["labels"] == 0
    assert summary["stockfish"]["parameters"] is None
