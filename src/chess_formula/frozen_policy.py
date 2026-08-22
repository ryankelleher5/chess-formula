from __future__ import annotations

import numpy as np

from .march import StaticFormula

LOCKED_3_FEATURES = ["material", "space", "tempo"]
LOCKED_3_COEFFICIENTS = [75.69811222753397, 13.073404650644708, 70.02438376205043]
LOCKED_3_INTERCEPT = 6.709046125656144

FULL_16_FEATURES = [
    "material",
    "mobility",
    "center_control",
    "development",
    "space",
    "king_safety",
    "passed_pawns",
    "isolated_pawns",
    "doubled_pawns",
    "connected_pawns",
    "bishop_pair",
    "rooks_open_files",
    "piece_activity",
    "threat_pressure",
    "tempo",
    "game_phase",
]
FULL_16_COEFFICIENTS = [
    67.03287026680752,
    -0.7496015569303175,
    4.840384918731822,
    5.050905130635666,
    3.2801761272114742,
    11.856036866764546,
    52.49416555153476,
    -27.462269328925366,
    2.492849138641097,
    7.552973996510137,
    41.24855629591493,
    1.9084238031449885,
    5.758741995164625,
    7.717770996628676,
    72.05024885706675,
    41.6419123319783,
]
FULL_16_INTERCEPT = -28.561553858306517

SEARCH_DEPTH_PLIES = 2
MAXIMUM_EXPANDED_CHILDREN_PER_ROOT = 128
FORCING_3_SEARCH_DEPTH_PLIES = 3
FORCING_3_MAXIMUM_EXPANDED_CHILDREN_PER_ROOT = 256
TERMINAL_CP = 2000.0

FORCING_POLICY_SPECS = {
    "forcing-1-64": (1, 64),
    "forcing-3-128": (3, 128),
    "forcing-3": (
        FORCING_3_SEARCH_DEPTH_PLIES,
        FORCING_3_MAXIMUM_EXPANDED_CHILDREN_PER_ROOT,
    ),
    "forcing-4-256": (4, 256),
}


def frozen_formula(policy: str) -> StaticFormula:
    if policy in {"locked-3", "searched-3", *FORCING_POLICY_SPECS}:
        return StaticFormula(
            LOCKED_3_FEATURES,
            np.asarray(LOCKED_3_COEFFICIENTS),
            LOCKED_3_INTERCEPT,
        )
    if policy == "full-16":
        return StaticFormula(
            FULL_16_FEATURES,
            np.asarray(FULL_16_COEFFICIENTS),
            FULL_16_INTERCEPT,
        )
    raise ValueError(f"Unknown frozen policy: {policy}")
