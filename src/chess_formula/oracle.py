from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import chess
import chess.engine

from .database import connect_database


def normalize_score(
    score: chess.engine.PovScore, mate_score_cp: int = 100000
) -> tuple[int, int | None]:
    """Return (centipawns, mate distance), always from White's perspective."""
    white_score = score.pov(chess.WHITE)
    mate = white_score.mate()
    centipawns = white_score.score(mate_score=mate_score_cp)
    if centipawns is None:
        raise ValueError("Engine score could not be normalized")
    return int(centipawns), mate


def _limit(limit_type: str, value: float) -> chess.engine.Limit:
    if limit_type == "depth":
        return chess.engine.Limit(depth=int(value))
    if limit_type == "nodes":
        return chess.engine.Limit(nodes=int(value))
    if limit_type == "time":
        return chess.engine.Limit(time=float(value))
    raise ValueError(f"Unsupported analysis limit: {limit_type}")


def label_positions(
    stockfish_path: str | Path,
    database: str | Path,
    config: dict,
    *,
    force: bool = False,
) -> dict:
    path = Path(stockfish_path)
    if not path.exists():
        raise FileNotFoundError(path)
    labeling = config["labeling"]
    engine = chess.engine.SimpleEngine.popen_uci(str(path))
    try:
        engine_name = engine.id.get("name", path.name)
        engine_author = engine.id.get("author", "unknown")
        engine_version = f"{engine_name} ({engine_author})"
        engine_parameters = {
            "Threads": int(labeling["threads"]),
            "Hash": int(labeling["hash_mb"]),
        }
        configurable = {
            name: value for name, value in engine_parameters.items() if name in engine.options
        }
        if configurable:
            engine.configure(configurable)
        if "UCI_ShowWDL" in engine.options:
            engine.configure({"UCI_ShowWDL": True})
        key_data = {
            "engine": engine_version,
            "limit_type": labeling["limit_type"],
            "limit_value": labeling["limit_value"],
            "multipv": labeling["multipv"],
            "mate_score_cp": labeling["mate_score_cp"],
            "parameters": engine_parameters,
        }
        engine_key = hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()[:20]
        connection = connect_database(database)
        if force:
            connection.execute("DELETE FROM engine_analysis WHERE engine_key = ?", [engine_key])
        rows = connection.execute(
            "SELECT position_hash, fen FROM positions WHERE position_hash NOT IN "
            "(SELECT position_hash FROM engine_analysis WHERE engine_key = ?) "
            "ORDER BY position_hash",
            [engine_key],
        ).fetchall()
        started = time.perf_counter()
        for digest, fen in rows:
            board = chess.Board(fen)
            analysis_started = time.perf_counter()
            infos = engine.analyse(
                board,
                _limit(labeling["limit_type"], float(labeling["limit_value"])),
                multipv=int(labeling["multipv"]),
            )
            if isinstance(infos, dict):
                infos = [infos]
            elapsed_ms = (time.perf_counter() - analysis_started) * 1000
            primary = infos[0]
            eval_cp, mate = normalize_score(primary["score"], int(labeling["mate_score_cp"]))
            top_moves = []
            for info in infos:
                pv = info.get("pv", [])
                score_cp, score_mate = normalize_score(
                    info["score"], int(labeling["mate_score_cp"])
                )
                top_moves.append(
                    {
                        "move": pv[0].uci() if pv else None,
                        "eval_cp": score_cp,
                        "mate": score_mate,
                    }
                )
            wdl = primary.get("wdl")
            wdl_json = None
            if wdl is not None:
                white_wdl = wdl.pov(chess.WHITE)
                wdl_json = json.dumps(
                    {"wins": white_wdl.wins, "draws": white_wdl.draws, "losses": white_wdl.losses}
                )
            connection.execute(
                "INSERT INTO engine_analysis VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)",
                [
                    digest,
                    engine_key,
                    engine_version,
                    labeling["limit_type"],
                    float(labeling["limit_value"]),
                    int(labeling["multipv"]),
                    eval_cp,
                    mate,
                    top_moves[0]["move"],
                    json.dumps(top_moves),
                    wdl_json,
                    primary.get("depth"),
                    primary.get("seldepth"),
                    primary.get("nodes"),
                    elapsed_ms,
                    json.dumps(engine_parameters, sort_keys=True),
                ],
            )
        total = connection.execute(
            "SELECT count(*) FROM engine_analysis WHERE engine_key = ?", [engine_key]
        ).fetchone()[0]
        connection.close()
        return {
            "engine_key": engine_key,
            "engine_version": engine_version,
            "new_labels": len(rows),
            "total_labels": total,
            "runtime_seconds": time.perf_counter() - started,
            "configuration": key_data,
        }
    finally:
        engine.quit()
