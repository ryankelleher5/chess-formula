from __future__ import annotations

import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

DEFAULT_CONFIG = Path("configs/default.json")


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    default_path = DEFAULT_CONFIG
    if not default_path.exists():
        default_path = Path(__file__).resolve().parents[2] / "configs" / "default.json"
    with default_path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    if path is not None and Path(path).resolve() != default_path.resolve():
        with Path(path).open(encoding="utf-8") as handle:
            config = _merge(config, json.load(handle))
    return config


def set_deterministic_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def write_json(path: str | Path, value: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
