# ruff: noqa: E501

from __future__ import annotations

import html
import json
import platform
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.engine
import numpy as np

from .config import set_deterministic_seed, write_json
from .ingest import position_hash
from .march import forcing_moves
from .model import _git_commit, _next_experiment_id
from .oracle import _limit, configure_engine, normalize_score


def extract_candidate_loss_positions(games: list[dict], settings: dict) -> list[dict]:
    records = []
    for game in games:
        if game["opponent"] != settings["opponent"] or game["candidate_score"] != 0:
            continue
        candidate_color = chess.WHITE if game["candidate_color"] == "white" else chess.BLACK
        board = chess.Board()
        game_key = f"{game['opening_id']}:{game['candidate_color']}"
        for ply, move_uci in enumerate(game["moves_uci"]):
            if ply >= int(settings["opening_plies"]) and board.turn == candidate_color:
                fen = board.fen()
                records.append(
                    {
                        "game_key": game_key,
                        "opening_id": game["opening_id"],
                        "candidate_color": game["candidate_color"],
                        "ply": ply,
                        "position_hash": position_hash(fen),
                        "fen": fen,
                        "played_move": move_uci,
                    }
                )
            move = chess.Move.from_uci(move_uci)
            if move not in board.legal_moves:
                raise ValueError(f"Illegal recorded move {move_uci} in {game_key}")
            board.push(move)
    if not records:
        raise RuntimeError("No candidate positions found in lost games")
    return records


def move_kind(board: chess.Board, move: chess.Move) -> str:
    if move.promotion is not None:
        return "promotion"
    if board.gives_check(move):
        return "check"
    if board.is_capture(move):
        captured = board.piece_at(move.to_square)
        if captured is None and board.is_en_passant(move):
            return "pawn-capture"
        if captured is not None and captured.piece_type == chess.PAWN:
            return "pawn-capture"
        return "piece-capture"
    return "quiet"


def classify_refutation(board: chess.Board, played_pv: list[str]) -> dict:
    if not played_pv:
        return {"reply_class": "short-or-terminal-pv", "reply_move": None}
    root = chess.Move.from_uci(played_pv[0])
    if root not in board.legal_moves:
        raise ValueError("Forced oracle PV does not begin with a legal root move")
    board = board.copy(stack=False)
    board.push(root)
    if len(played_pv) < 2 or board.is_game_over(claim_draw=False):
        return {"reply_class": "short-or-terminal-pv", "reply_move": None}
    reply = chess.Move.from_uci(played_pv[1])
    reply_kind = move_kind(board, reply)
    reply_visible = reply in forcing_moves(board)
    if not reply_visible:
        if reply_kind == "pawn-capture":
            reply_class = "excluded-pawn-capture-reply"
        elif reply_kind == "quiet":
            reply_class = "excluded-quiet-reply"
        else:
            reply_class = "excluded-other-reply"
        return {
            "reply_class": reply_class,
            "reply_move": reply.uci(),
            "reply_kind": reply_kind,
            "reply_visible": False,
        }
    board.push(reply)
    if len(played_pv) < 3 or board.is_game_over(claim_draw=False):
        return {
            "reply_class": "short-or-terminal-pv",
            "reply_move": reply.uci(),
            "reply_kind": reply_kind,
            "reply_visible": True,
        }
    continuation = chess.Move.from_uci(played_pv[2])
    continuation_visible = continuation in forcing_moves(board)
    return {
        "reply_class": "beyond-two-ply" if continuation_visible else "quiet-second-ply",
        "reply_move": reply.uci(),
        "reply_kind": reply_kind,
        "reply_visible": True,
        "continuation_move": continuation.uci(),
        "continuation_kind": move_kind(board, continuation),
        "continuation_visible": continuation_visible,
    }


def select_first_error(
    rows: list[dict], *, major_regret_cp: float, persistent_disadvantage_cp: float
) -> dict:
    ordered = sorted(rows, key=lambda row: row["ply"])
    for index, row in enumerate(ordered):
        next_pre = (
            ordered[index + 1]["pre_move_candidate_cp"]
            if index + 1 < len(ordered)
            else None
        )
        if (
            row["regret_cp"] >= major_regret_cp
            and row["post_move_candidate_cp"] <= -persistent_disadvantage_cp
            and next_pre is not None
            and next_pre <= -persistent_disadvantage_cp
        ):
            return {**row, "selection_reason": "first-persistent-major-error"}
    for row in ordered:
        if row["regret_cp"] >= major_regret_cp:
            return {**row, "selection_reason": "first-major-error"}
    return {**max(ordered, key=lambda row: row["regret_cp"]), "selection_reason": "maximum-regret"}


def _load_cache(path: Path) -> dict:
    if not path.exists():
        return {"engine_key": None, "entries": {}}
    cache = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cache.get("entries"), dict):
        raise RuntimeError("Loss-audit cache is malformed")
    return cache


def label_loss_positions(
    records: list[dict], stockfish_path: str | Path, config: dict
) -> tuple[dict[str, dict], dict]:
    path = Path(stockfish_path)
    if not path.exists():
        raise FileNotFoundError(path)
    settings = config["uci_loss_audit"]
    labeling = config["labeling"]
    cache_path = Path(settings["analysis_cache"])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = _load_cache(cache_path)
    engine = chess.engine.SimpleEngine.popen_uci(str(path))
    started = time.perf_counter()
    new_labels = 0
    try:
        engine_key, engine_version, key_data = configure_engine(engine, path, labeling)
        if cache["engine_key"] not in {None, engine_key}:
            raise RuntimeError("Loss-audit cache engine configuration differs")
        cache.update(
            {
                "engine_key": engine_key,
                "engine_version": engine_version,
                "configuration": key_data,
            }
        )
        unique = {
            f"{record['position_hash']}:{record['played_move']}": record for record in records
        }
        for index, (key, record) in enumerate(sorted(unique.items())):
            if key in cache["entries"]:
                continue
            board = chess.Board(record["fen"])
            played = chess.Move.from_uci(record["played_move"])
            if played not in board.legal_moves:
                raise ValueError(f"Illegal candidate move {played.uci()} for {record['game_key']}")
            limit = _limit(labeling["limit_type"], float(labeling["limit_value"]))
            root_info = engine.analyse(board, limit)
            forced_info = engine.analyse(board, limit, root_moves=[played])
            root_cp, root_mate = normalize_score(
                root_info["score"], int(labeling["mate_score_cp"])
            )
            played_cp, played_mate = normalize_score(
                forced_info["score"], int(labeling["mate_score_cp"])
            )
            cache["entries"][key] = {
                "best_move": root_info["pv"][0].uci(),
                "best_cp": root_cp,
                "best_mate": root_mate,
                "best_pv": [move.uci() for move in root_info.get("pv", [])],
                "played_cp": played_cp,
                "played_mate": played_mate,
                "played_pv": [move.uci() for move in forced_info.get("pv", [])],
                "root_depth": root_info.get("depth"),
                "forced_depth": forced_info.get("depth"),
            }
            new_labels += 1
            if new_labels % 25 == 0 or index + 1 == len(unique):
                write_json(cache_path, cache)
    finally:
        engine.quit()
    write_json(cache_path, cache)
    return cache["entries"], {
        "engine_key": cache["engine_key"],
        "engine_version": cache["engine_version"],
        "unique_position_moves": len(
            {f"{record['position_hash']}:{record['played_move']}" for record in records}
        ),
        "new_labels": new_labels,
        "cached_labels": len(unique) - new_labels,
        "runtime_seconds": time.perf_counter() - started,
    }


def _report(result: dict) -> str:
    reply_rows = [
        f"| {label} | {count} | {count / result['lost_games']:.1%} |"
        for label, count in result["first_error_reply_classes"].items()
    ]
    move_rows = [
        f"| {label} | {count} | {count / result['lost_games']:.1%} |"
        for label, count in result["first_error_best_move_kinds"].items()
    ]
    return f"""# UCI Loss Audit: {result['experiment_id']}

## Development-only guardrail

The {result['lost_games']} Stockfish-100 losses are exploratory failure material.
No search extension discovered here is a confirmed improvement.

## Method

- Candidate turns analyzed: {result['candidate_turns']}
- Unique position/move oracle records: {result['labeling']['unique_position_moves']}
- Oracle: {result['labeling']['engine_version']}, depth 12
- Major-error threshold: {result['major_regret_cp']} cp
- Persistent disadvantage threshold: {result['persistent_disadvantage_cp']} cp
- New / cached oracle records: {result['labeling']['new_labels']} / {result['labeling']['cached_labels']}
- Git revision: {result['git_commit']}
- Runtime: {result['runtime_seconds']:.3f} seconds

## First-error reply taxonomy

| Class | Games | Fraction |
|---|---:|---:|
{chr(10).join(reply_rows)}

## Stockfish best root-move type at first error

| Type | Games | Fraction |
|---|---:|---:|
{chr(10).join(move_rows)}

## Aggregate error

- Mean candidate-turn regret: {result['all_turns']['mean_regret_cp']:.2f} cp
- Candidate turns with ≥150 cp regret: {result['all_turns']['major_error_turns']}
- Oracle noise inversions before zero-clipping: {result['all_turns']['oracle_noise_inversions']}
- Mean selected first-error regret: {result['first_errors']['mean_regret_cp']:.2f} cp
- Median selected first-error ply: {result['first_errors']['median_ply']:.1f}

Open `loss_explorer.html` for boards, played/best moves, oracle lines, filters,
and the operational first-error reason for every lost game.
"""


def _explorer_html(result: dict) -> str:
    payload = json.dumps(result["selected_errors"], separators=(",", ":")).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UCI Loss Explorer</title><style>
:root{{--ink:#172019;--muted:#667067;--paper:#f2efe5;--card:#fffdf7;--accent:#9e3f29;--line:#d5cebf}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 system-ui,sans-serif}}header{{padding:28px 5vw;background:#1b2920;color:#f8f3e7}}h1{{margin:0 0 6px;font:700 30px Georgia,serif}}header p{{margin:0;color:#cbd4cc}}main{{padding:22px 5vw}}.controls{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}}label{{display:grid;gap:4px;color:var(--muted);font-size:12px}}select{{min-width:190px;padding:9px;border:1px solid var(--line);border-radius:6px;background:var(--card)}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));gap:16px}}.card{{display:grid;grid-template-columns:224px 1fr;gap:15px;padding:15px;background:var(--card);border:1px solid var(--line);border-radius:10px}}.board{{display:grid;grid-template-columns:repeat(8,28px);width:224px;height:224px;border:1px solid #687168}}.sq{{display:grid;place-items:center;font-size:23px}}.light{{background:#eadfc5}}.dark{{background:#78917d}}h2{{font-size:17px;margin:0 0 7px}}.big{{font-size:22px;font-weight:750;color:var(--accent)}}.meta,.fen,.pv{{font-size:11px;color:var(--muted);overflow-wrap:anywhere}}.tag{{display:inline-block;margin:5px 4px 5px 0;padding:3px 7px;border-radius:99px;background:#e9e3d5;font-size:11px}}@media(max-width:560px){{.card{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>Stockfish Loss Explorer</h1><p>{html.escape(result['experiment_id'])} · exploratory development audit</p></header><main><div class="controls"><label>Reply class<select id="reply"><option value="all">All</option></select></label><label>Candidate color<select id="color"><option value="all">Both</option><option>white</option><option>black</option></select></label><label>Sort<select id="sort"><option value="ply">Earliest error</option><option value="regret">Largest regret</option></select></label></div><p id="summary"></p><div class="grid" id="cards"></div></main><script>
const rows={payload};const glyph={{p:'♟',n:'♞',b:'♝',r:'♜',q:'♛',k:'♚',P:'♙',N:'♘',B:'♗',R:'♖',Q:'♕',K:'♔'}};function sq(p,r,f){{return `<div class="sq ${{(r+f)%2?'dark':'light'}}">${{p}}</div>`}}function board(fen){{let o='<div class="board">';fen.split(' ')[0].split('/').forEach((rank,r)=>{{let f=0;for(const c of rank){{if(/\\d/.test(c)){{for(let i=0;i<+c;i++,f++)o+=sq('',r,f)}}else{{o+=sq(glyph[c],r,f);f++}}}}}});return o+'</div>'}}const classes=[...new Set(rows.map(x=>x.reply_class))].sort();classes.forEach(x=>reply.insertAdjacentHTML('beforeend',`<option>${{x}}</option>`));function render(){{let r=rows.filter(x=>(reply.value==='all'||x.reply_class===reply.value)&&(color.value==='all'||x.candidate_color===color.value));r.sort((a,b)=>sort.value==='ply'?a.ply-b.ply:b.regret_cp-a.regret_cp);summary.textContent=`${{r.length}} of ${{rows.length}} lost games`;cards.innerHTML=r.map(x=>`<article class="card">${{board(x.fen)}}<div><h2>${{x.opening_id}} · ${{x.candidate_color}} · ply ${{x.ply}}</h2><div class="big">${{x.regret_cp.toFixed(0)}} cp regret</div><span class="tag">${{x.reply_class}}</span><span class="tag">${{x.selection_reason}}</span><p>Played <b>${{x.played_move}}</b> · best <b>${{x.best_move}}</b> · reply <b>${{x.reply_move||'terminal'}}</b></p><div class="pv">PV: ${{x.played_pv.join(' ')}}</div><div class="fen">${{x.fen}}</div></div></article>`).join('')}}reply.onchange=color.onchange=sort.onchange=render;render();</script></body></html>"""


def run_uci_loss_audit(
    stockfish_path: str | Path,
    config: dict,
    *,
    results_dir: str | Path = "results",
) -> tuple[dict, Path]:
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    seed = int(config["seed"])
    set_deterministic_seed(seed)
    settings = config["uci_loss_audit"]
    games = json.loads(Path(settings["games_json"]).read_text(encoding="utf-8"))
    records = extract_candidate_loss_positions(games, settings)
    labels, labeling_audit = label_loss_positions(records, stockfish_path, config)
    clip = float(settings["score_clip_cp"])
    enriched = []
    for record in records:
        key = f"{record['position_hash']}:{record['played_move']}"
        label = labels[key]
        board = chess.Board(record["fen"])
        best_cp = float(np.clip(label["best_cp"], -clip, clip))
        played_cp = float(np.clip(label["played_cp"], -clip, clip))
        candidate_white = record["candidate_color"] == "white"
        raw_regret = best_cp - played_cp if candidate_white else played_cp - best_cp
        best_move = chess.Move.from_uci(label["best_move"])
        classification = classify_refutation(board, label["played_pv"])
        enriched.append(
            {
                **record,
                **classification,
                "best_move": label["best_move"],
                "best_move_kind": move_kind(board, best_move),
                "best_cp": best_cp,
                "played_cp": played_cp,
                "regret_cp": max(0.0, float(raw_regret)),
                "oracle_noise_inversion": bool(raw_regret < 0),
                "pre_move_candidate_cp": best_cp if candidate_white else -best_cp,
                "post_move_candidate_cp": played_cp if candidate_white else -played_cp,
                "played_pv": label["played_pv"],
                "best_pv": label["best_pv"],
            }
        )
    by_game: dict[str, list[dict]] = {}
    for row in enriched:
        by_game.setdefault(row["game_key"], []).append(row)
    selected = [
        select_first_error(
            rows,
            major_regret_cp=float(settings["major_regret_cp"]),
            persistent_disadvantage_cp=float(settings["persistent_disadvantage_cp"]),
        )
        for rows in by_game.values()
    ]
    selected.sort(key=lambda row: (row["opening_id"], row["candidate_color"]))
    experiment_name = settings.get("experiment_name", "uci-loss-audit")
    experiment_id = _next_experiment_id(Path(results_dir), experiment_name)
    artifact = Path(results_dir) / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    runtime = time.perf_counter() - started
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "git_commit": _git_commit(),
        "lost_games": len(by_game),
        "candidate_turns": len(enriched),
        "major_regret_cp": float(settings["major_regret_cp"]),
        "persistent_disadvantage_cp": float(settings["persistent_disadvantage_cp"]),
        "labeling": labeling_audit,
        "first_error_reply_classes": dict(
            sorted(Counter(row["reply_class"] for row in selected).items())
        ),
        "first_error_best_move_kinds": dict(
            sorted(Counter(row["best_move_kind"] for row in selected).items())
        ),
        "selection_reasons": dict(
            sorted(Counter(row["selection_reason"] for row in selected).items())
        ),
        "all_turns": {
            "mean_regret_cp": float(np.mean([row["regret_cp"] for row in enriched])),
            "median_regret_cp": float(np.median([row["regret_cp"] for row in enriched])),
            "major_error_turns": sum(
                row["regret_cp"] >= float(settings["major_regret_cp"])
                for row in enriched
            ),
            "oracle_noise_inversions": sum(
                row["oracle_noise_inversion"] for row in enriched
            ),
        },
        "first_errors": {
            "mean_regret_cp": float(np.mean([row["regret_cp"] for row in selected])),
            "median_regret_cp": float(np.median([row["regret_cp"] for row in selected])),
            "median_ply": float(np.median([row["ply"] for row in selected])),
        },
        "selected_errors": selected,
        "runtime_seconds": runtime,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    write_json(artifact / "config.json", config)
    write_json(artifact / "metrics.json", result)
    write_json(artifact / "all_candidate_turns.json", enriched)
    write_json(
        artifact / "environment.json",
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "python_chess": chess.__version__,
            "git_commit": result["git_commit"],
        },
    )
    (artifact / "report.md").write_text(_report(result), encoding="utf-8")
    (artifact / "loss_explorer.html").write_text(_explorer_html(result), encoding="utf-8")
    return result, artifact
