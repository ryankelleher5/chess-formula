from __future__ import annotations

import json
import platform
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np

from .config import set_deterministic_seed, write_json
from .database import connect_database
from .features import feature_matrix


@dataclass
class LinearModel:
    name: str
    feature_names: list[str]
    coefficients: list[float]
    intercept: float
    ridge_alpha: float
    target_clip_cp: int
    engine_key: str
    experiment_id: str

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        return matrix @ np.asarray(self.coefficients) + self.intercept

    def formula(self) -> str:
        lines = [f"Evaluation_cp = {self.intercept:+.6f}"]
        lines.extend(
            f"  {coefficient:+.6f} * {name}"
            for name, coefficient in zip(self.feature_names, self.coefficients, strict=True)
        )
        return "\n".join(lines) + "\n"

    def save(self, path: str | Path) -> None:
        write_json(path, asdict(self))

    @classmethod
    def load(cls, path: str | Path) -> LinearModel:
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


def _git_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _next_experiment_id(results_dir: Path, name: str) -> str:
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    stem = f"{date}_{name.replace('-', '_')}"
    existing = [path for path in results_dir.glob(f"{stem}_*") if path.is_dir()]
    numbers = [
        int(path.name.rsplit("_", 1)[1])
        for path in existing
        if path.name.rsplit("_", 1)[1].isdigit()
    ]
    return f"{stem}_{max(numbers, default=0) + 1:03d}"


def resolve_engine_key(connection: duckdb.DuckDBPyConnection, engine_key: str | None) -> str:
    if engine_key:
        return engine_key
    row = connection.execute(
        "SELECT engine_key FROM engine_analysis ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("No Stockfish labels found. Run 'chess-formula label' first.")
    return row[0]


def fit_ridge(matrix: np.ndarray, target: np.ndarray, alpha: float) -> tuple[np.ndarray, float]:
    """Fit standardized ridge regression and return raw-unit coefficients."""
    if matrix.ndim != 2 or target.ndim != 1 or len(matrix) != len(target):
        raise ValueError("Ridge inputs must be aligned 2D features and a 1D target")
    if len(matrix) < 2:
        raise ValueError("At least two observations are required")
    means = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales[scales < 1e-12] = 1.0
    standardized = (matrix - means) / scales
    centered_target = target - target.mean()
    coefficients_standard = np.linalg.solve(
        standardized.T @ standardized + alpha * np.eye(standardized.shape[1]),
        standardized.T @ centered_target,
    )
    coefficients = coefficients_standard / scales
    intercept = float(target.mean() - means @ coefficients)
    return coefficients, intercept


def train_linear(
    database: str | Path,
    config: dict,
    *,
    model_path: str | Path = "models/baseline-linear.json",
    results_dir: str | Path = "results",
    engine_key: str | None = None,
) -> tuple[LinearModel, Path, dict]:
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    set_deterministic_seed(int(config["seed"]))
    connection = connect_database(database)
    resolved_key = resolve_engine_key(connection, engine_key)
    rows = connection.execute(
        "SELECT p.fen, a.eval_cp FROM positions p JOIN engine_analysis a USING(position_hash) "
        "WHERE p.split = 'train' AND a.engine_key = ? ORDER BY p.position_hash",
        [resolved_key],
    ).fetchall()
    if len(rows) < 2:
        raise RuntimeError("At least two labeled training positions are required")
    matrix, names = feature_matrix([row[0] for row in rows])
    clip = int(config["model"]["target_clip_cp"])
    target = np.clip(np.asarray([row[1] for row in rows], dtype=float), -clip, clip)
    alpha = float(config["model"]["ridge_alpha"])
    coefficients, intercept = fit_ridge(matrix, target, alpha)
    experiment_id = _next_experiment_id(Path(results_dir), config["model"]["name"])
    model = LinearModel(
        name=config["model"]["name"],
        feature_names=names,
        coefficients=coefficients.tolist(),
        intercept=intercept,
        ridge_alpha=alpha,
        target_clip_cp=clip,
        engine_key=resolved_key,
        experiment_id=experiment_id,
    )
    model.save(model_path)
    artifact = Path(results_dir) / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    runtime = time.perf_counter() - started
    metadata = {
        "experiment_id": experiment_id,
        "seed": config["seed"],
        "engine_key": resolved_key,
        "train_positions": len(rows),
        "runtime_seconds": runtime,
        "git_commit": _git_commit(),
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    write_json(artifact / "config.json", config)
    write_json(artifact / "training.json", metadata)
    write_json(
        artifact / "environment.json",
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "numpy": np.__version__,
            "duckdb": duckdb.__version__,
            "git_commit": metadata["git_commit"],
        },
    )
    (artifact / "formula.txt").write_text(model.formula(), encoding="utf-8")
    connection.execute(
        "INSERT OR REPLACE INTO experiments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            experiment_id,
            "baseline-linear",
            json.dumps(config, sort_keys=True),
            metadata["git_commit"],
            started_at,
            datetime.now(UTC),
            runtime,
            str(artifact),
        ],
    )
    connection.close()
    return model, artifact, metadata
