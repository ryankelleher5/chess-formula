from __future__ import annotations

from pathlib import Path

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    game_id VARCHAR PRIMARY KEY,
    source VARCHAR NOT NULL,
    headers_json VARCHAR NOT NULL,
    result VARCHAR,
    ply_count INTEGER NOT NULL,
    split VARCHAR NOT NULL,
    ingested_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS positions (
    position_hash VARCHAR PRIMARY KEY,
    fen VARCHAR NOT NULL,
    board_fen VARCHAR NOT NULL,
    side_to_move VARCHAR NOT NULL,
    legal_move_count INTEGER NOT NULL,
    castling_rights VARCHAR NOT NULL,
    ep_square VARCHAR,
    halfmove_clock INTEGER NOT NULL,
    fullmove_number INTEGER NOT NULL,
    split VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS position_occurrences (
    game_id VARCHAR NOT NULL,
    ply INTEGER NOT NULL,
    position_hash VARCHAR NOT NULL,
    played_move VARCHAR NOT NULL,
    game_result VARCHAR,
    PRIMARY KEY (game_id, ply)
);

CREATE TABLE IF NOT EXISTS engine_analysis (
    position_hash VARCHAR NOT NULL,
    engine_key VARCHAR NOT NULL,
    engine_version VARCHAR NOT NULL,
    limit_type VARCHAR NOT NULL,
    limit_value DOUBLE NOT NULL,
    multipv INTEGER NOT NULL,
    eval_cp INTEGER NOT NULL,
    mate INTEGER,
    best_move VARCHAR,
    top_moves_json VARCHAR NOT NULL,
    wdl_json VARCHAR,
    depth INTEGER,
    seldepth INTEGER,
    nodes BIGINT,
    elapsed_ms DOUBLE NOT NULL,
    parameters_json VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (position_hash, engine_key)
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id VARCHAR PRIMARY KEY,
    experiment_type VARCHAR NOT NULL,
    config_json VARCHAR NOT NULL,
    git_commit VARCHAR,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    runtime_seconds DOUBLE,
    artifact_path VARCHAR
);

CREATE TABLE IF NOT EXISTS benchmark_results (
    experiment_id VARCHAR NOT NULL,
    benchmark_version VARCHAR NOT NULL,
    metrics_json VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (experiment_id, benchmark_version)
);
"""


def connect_database(path: str | Path) -> duckdb.DuckDBPyConnection:
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database_path))
    connection.execute(SCHEMA)
    return connection
