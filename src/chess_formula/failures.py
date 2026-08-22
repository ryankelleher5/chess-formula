# ruff: noqa: E501

from __future__ import annotations

import html
import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .config import set_deterministic_seed, write_json
from .confirmation import _labeled_rows
from .database import connect_database
from .features import feature_matrix
from .model import _git_commit, _next_experiment_id, fit_ridge, resolve_engine_key
from .stability import position_categories


def deterministic_kmeans(
    matrix: np.ndarray, clusters: int, *, max_iterations: int = 100
) -> tuple[np.ndarray, np.ndarray]:
    if matrix.ndim != 2 or not len(matrix):
        raise ValueError("K-means requires a non-empty 2D matrix")
    if not 1 <= clusters <= len(matrix):
        raise ValueError("clusters must be between 1 and the number of rows")
    centroids = [matrix[int(np.argmax(np.sum(matrix**2, axis=1)))].copy()]
    while len(centroids) < clusters:
        distances = np.min(
            np.stack([np.sum((matrix - centroid) ** 2, axis=1) for centroid in centroids]),
            axis=0,
        )
        centroids.append(matrix[int(np.argmax(distances))].copy())
    centroid_matrix = np.asarray(centroids)
    labels = np.full(len(matrix), -1, dtype=int)
    for _ in range(max_iterations):
        distances = np.stack(
            [np.sum((matrix - centroid) ** 2, axis=1) for centroid in centroid_matrix],
            axis=1,
        )
        new_labels = np.argmin(distances, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for cluster in range(clusters):
            members = matrix[labels == cluster]
            if len(members):
                centroid_matrix[cluster] = members.mean(axis=0)
    return labels, centroid_matrix


def failure_candidate_masks(
    target: np.ndarray,
    locked_prediction: np.ndarray,
    full_prediction: np.ndarray,
    *,
    error_threshold_cp: float,
    disagreement_threshold_cp: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    high_error = np.abs(locked_prediction - target) >= error_threshold_cp
    disagreement = np.abs(locked_prediction - full_prediction) >= disagreement_threshold_cp
    return high_error, disagreement, high_error | disagreement


def _phase_labels(categories: dict[str, np.ndarray]) -> list[str]:
    labels = []
    for index in range(len(categories["opening"])):
        labels.append(
            next(
                phase
                for phase in ("opening", "middlegame", "endgame")
                if categories[phase][index]
            )
        )
    return labels


def _cluster_summaries(
    candidates: list[dict], centroids: np.ndarray, omitted_names: list[str]
) -> list[dict]:
    summaries = []
    for cluster in sorted({candidate["cluster"] for candidate in candidates}):
        members = [candidate for candidate in candidates if candidate["cluster"] == cluster]
        centroid = centroids[cluster - 1]
        top_features = sorted(
            zip(omitted_names, centroid.tolist(), strict=True),
            key=lambda item: (-abs(item[1]), item[0]),
        )[:4]
        phase_counts = {
            phase: sum(member["phase"] == phase for member in members)
            for phase in ("opening", "middlegame", "endgame")
        }
        summaries.append(
            {
                "cluster": cluster,
                "positions": len(members),
                "games": len({member["game_id"] for member in members}),
                "high_error_positions": sum(member["high_error"] for member in members),
                "disagreement_positions": sum(member["high_disagreement"] for member in members),
                "locked_mae_cp": float(np.mean([member["locked_abs_error_cp"] for member in members])),
                "full_mae_cp": float(np.mean([member["full_abs_error_cp"] for member in members])),
                "mean_signed_locked_error_cp": float(
                    np.mean([member["locked_error_cp"] for member in members])
                ),
                "mean_abs_disagreement_cp": float(
                    np.mean([member["absolute_disagreement_cp"] for member in members])
                ),
                "full_better_fraction": float(
                    np.mean(
                        [
                            member["full_abs_error_cp"] < member["locked_abs_error_cp"]
                            for member in members
                        ]
                    )
                ),
                "forcing_fraction": float(np.mean([member["forcing_proxy"] for member in members])),
                "phase_counts": phase_counts,
                "top_omitted_feature_z": [
                    {"feature": name, "centroid_z": value} for name, value in top_features
                ],
                "representative_hashes": [
                    member["position_hash"]
                    for member in sorted(
                        members,
                        key=lambda item: (
                            -item["locked_abs_error_cp"],
                            item["position_hash"],
                        ),
                    )[:3]
                ],
            }
        )
    return summaries


def _save_projection(
    artifact: Path, standardized: np.ndarray, labels: np.ndarray, candidates: list[dict]
) -> None:
    centered = standardized - standardized.mean(axis=0)
    left, singular, _ = np.linalg.svd(centered, full_matrices=False)
    dimensions = min(2, left.shape[1])
    projected = left[:, :dimensions] * singular[:dimensions]
    if dimensions == 1:
        projected = np.column_stack([projected[:, 0], np.zeros(len(projected))])
    figure, axis = plt.subplots(figsize=(7, 5))
    scatter = axis.scatter(
        projected[:, 0],
        projected[:, 1],
        c=labels,
        s=[20 + candidate["locked_abs_error_cp"] / 15 for candidate in candidates],
        cmap="tab10",
        alpha=0.72,
    )
    axis.set(
        xlabel="Omitted-feature principal component 1",
        ylabel="Omitted-feature principal component 2",
        title="February failure candidates",
    )
    axis.grid(alpha=0.2)
    axis.legend(*scatter.legend_elements(), title="Cluster")
    figure.tight_layout()
    figure.savefig(artifact / "failure_clusters.png", dpi=150)
    plt.close(figure)


def _failure_report(result: dict) -> str:
    rows = []
    for summary in result["clusters"]:
        features = ", ".join(
            f"`{item['feature']}` ({item['centroid_z']:+.2f}z)"
            for item in summary["top_omitted_feature_z"]
        )
        phases = summary["phase_counts"]
        rows.append(
            f"| {summary['cluster']} | {summary['positions']} | {summary['games']} | "
            f"{summary['locked_mae_cp']:.1f} | {summary['full_mae_cp']:.1f} | "
            f"{summary['full_better_fraction']:.1%} | {summary['forcing_fraction']:.1%} | "
            f"{phases['opening']}/{phases['middlegame']}/{phases['endgame']} | {features} |"
        )
    representatives = []
    candidate_by_hash = {
        candidate["position_hash"]: candidate for candidate in result["candidates"]
    }
    for summary in result["clusters"]:
        for digest in summary["representative_hashes"]:
            candidate = candidate_by_hash[digest]
            representatives.append(
                f"| {summary['cluster']} | `{digest[:12]}` | {candidate['phase']} | "
                f"{candidate['stockfish_cp']:+.0f} | {candidate['locked_cp']:+.1f} | "
                f"{candidate['full_cp']:+.1f} | `{candidate['stockfish_best_move']}` | "
                f"`{candidate['fen']}` |"
            )
    criterion_rows = []
    for label, summary in result["criterion_summaries"].items():
        criterion_rows.append(
            f"| {label} | {summary['positions']} | {summary['games']} | "
            f"{summary['forcing_fraction']:.1%} | {summary['locked_mae_cp']:.1f} | "
            f"{summary['full_mae_cp']:.1f} | {summary['full_better_fraction']:.1%} |"
        )
    return f"""# Failure-Directed Discovery: {result['experiment_id']}

## Question

Which recurring, human-readable structures characterize the February positions
where Locked-3 fails badly or sharply disagrees with Full-16?

## Exploratory guardrail

February remains a hypothesis-generation corpus. No candidate feature, threshold,
cluster, or fitted weight in this report is a validated improvement. Any proposed
rule must be frozen before evaluation on March.

## Method

- Confirmation positions: {result['confirmation_positions']}
- Locked error threshold: ≥{result['error_threshold_cp']:.0f} cp
- Locked/full disagreement threshold: ≥{result['disagreement_threshold_cp']:.0f} cp
- Candidate positions / games: {result['candidate_positions']} / {result['candidate_games']}
- High-error positions: {result['high_error_positions']}
- High-disagreement positions: {result['high_disagreement_positions']}
- Candidates meeting both criteria: {result['both_criteria_positions']}
- Clustering: deterministic farthest-first k-means on standardized omitted features
- Clusters: {len(result['clusters'])}
- Git revision: {result['git_commit']}
- Runtime: {result['runtime_seconds']:.3f} seconds

| Candidate criterion | Positions | Games | Forcing | Locked MAE | Full MAE | Full better |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(criterion_rows)}

## Cluster summary

Phase counts are opening/middlegame/endgame. Centroid values use January training
means and scales; they describe association, not causal contribution.

| Cluster | Positions | Games | Locked MAE | Full MAE | Full better | Forcing | Phase counts | Top omitted-feature deviations |
|---|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(rows)}

## Representative positions

Open `failure_explorer.html` for board diagrams, filtering, sorting, and all
candidate measurements.

| Cluster | Hash | Phase | Stockfish | Locked-3 | Full-16 | Best move | FEN |
|---|---|---|---:|---:|---:|---|---|
{chr(10).join(representatives)}

## Interpretation boundary

Cluster descriptions are descriptive summaries of selected extreme cases. The
selection thresholds enrich for large errors, clusters need not be independent,
and related positions remain grouped only for counts—not for causal inference.
"""


def _explorer_html(result: dict) -> str:
    payload = json.dumps(
        {
            "experiment": result["experiment_id"],
            "clusters": result["clusters"],
            "candidates": result["candidates"],
        },
        separators=(",", ":"),
    ).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chess Formula Failure Explorer</title>
<style>
:root{{--ink:#18211b;--muted:#657168;--paper:#f4f1e8;--card:#fffdf7;--accent:#b7442a;--line:#d8d1c2}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 ui-sans-serif,system-ui,sans-serif}}
header{{padding:28px max(24px,5vw);background:#1d2b22;color:#f8f3e5}} h1{{margin:0 0 6px;font:700 30px/1.1 ui-serif,Georgia,serif}}
header p{{margin:0;color:#cbd5cb}} main{{padding:24px max(24px,5vw)}} .controls{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:20px}}
label{{display:grid;gap:4px;color:var(--muted);font-size:12px}} select,input{{min-width:170px;padding:9px 11px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}}
.summary{{margin:0 0 18px;color:var(--muted)}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(390px,1fr));gap:18px}}
.card{{display:grid;grid-template-columns:224px 1fr;gap:16px;padding:16px;background:var(--card);border:1px solid var(--line);border-radius:10px;box-shadow:0 3px 12px #2030250d}}
.board{{display:grid;grid-template-columns:repeat(8,28px);width:224px;height:224px;border:1px solid #6d746d}} .sq{{display:grid;place-items:center;font-size:23px;line-height:1}}
.light{{background:#e8ddc3}} .dark{{background:#76927c}} h2{{font-size:17px;margin:0 0 8px}} .metrics{{display:grid;grid-template-columns:1fr 1fr;gap:5px 10px;font-variant-numeric:tabular-nums}}
.metric strong{{display:block;font-size:16px}} .metric span,.fen{{color:var(--muted);font-size:11px}} .tags{{display:flex;gap:5px;flex-wrap:wrap;margin:9px 0}} .tag{{padding:3px 7px;border-radius:99px;background:#ebe6d9;font-size:11px}}
.danger{{background:#f4d7cd;color:#7c2817}} .fen{{overflow-wrap:anywhere}} @media(max-width:560px){{.card{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>Failure Explorer</h1><p>{html.escape(result['experiment_id'])} · February is exploratory only</p></header>
<main><div class="controls"><label>Cluster<select id="cluster"><option value="all">All clusters</option></select></label><label>Criterion<select id="criterion"><option value="all">All candidates</option><option value="error">≥300 cp error</option><option value="disagreement">≥150 cp disagreement</option><option value="both">Both</option></select></label><label>Phase<select id="phase"><option value="all">All phases</option><option>opening</option><option>middlegame</option><option>endgame</option></select></label><label>Sort<select id="sort"><option value="error">Largest error</option><option value="disagreement">Largest disagreement</option></select></label></div><p class="summary" id="summary"></p><div class="grid" id="cards"></div></main>
<script>const data={payload};
const glyph={{p:'♟',n:'♞',b:'♝',r:'♜',q:'♛',k:'♚',P:'♙',N:'♘',B:'♗',R:'♖',Q:'♕',K:'♔'}};
function board(fen){{const ranks=fen.split(' ')[0].split('/');let out='<div class="board">';ranks.forEach((rank,r)=>{{let f=0;for(const ch of rank){{if(/\\d/.test(ch)){{for(let i=0;i<+ch;i++,f++)out+=sq('',r,f)}}else{{out+=sq(glyph[ch],r,f);f++}}}}}});return out+'</div>'}}
function sq(piece,r,f){{return `<div class="sq ${{(r+f)%2?'dark':'light'}}">${{piece}}</div>`}}
function filters(c){{const cl=cluster.value,cr=criterion.value,ph=phase.value;if(cl!=='all'&&c.cluster!=+cl)return false;if(ph!=='all'&&c.phase!==ph)return false;if(cr==='error'&&!c.high_error)return false;if(cr==='disagreement'&&!c.high_disagreement)return false;if(cr==='both'&&!(c.high_error&&c.high_disagreement))return false;return true}}
function render(){{let rows=data.candidates.filter(filters);rows.sort((a,b)=>sort.value==='error'?b.locked_abs_error_cp-a.locked_abs_error_cp:b.absolute_disagreement_cp-a.absolute_disagreement_cp);summary.textContent=`${{rows.length}} of ${{data.candidates.length}} candidate positions`;cards.innerHTML=rows.map(c=>`<article class="card">${{board(c.fen)}}<div><h2>Cluster ${{c.cluster}} · ${{c.phase}}</h2><div class="metrics"><div class="metric"><span>Stockfish</span><strong>${{c.stockfish_cp.toFixed(0)}} cp</strong></div><div class="metric"><span>Locked-3</span><strong>${{c.locked_cp.toFixed(1)}} cp</strong></div><div class="metric"><span>Full-16</span><strong>${{c.full_cp.toFixed(1)}} cp</strong></div><div class="metric"><span>Locked error</span><strong>${{c.locked_abs_error_cp.toFixed(1)}} cp</strong></div></div><div class="tags"><span class="tag">${{c.side_to_move}} to move</span><span class="tag">${{c.forcing_proxy?'forcing':'quiet'}}</span>${{c.high_error?'<span class="tag danger">high error</span>':''}}${{c.high_disagreement?'<span class="tag danger">model disagreement</span>':''}}</div><div class="fen">${{c.fen}}</div></div></article>`).join('')}}
for(const c of data.clusters)cluster.insertAdjacentHTML('beforeend',`<option value="${{c.cluster}}">Cluster ${{c.cluster}} (${{c.positions}})</option>`);for(const el of document.querySelectorAll('select'))el.addEventListener('change',render);render();</script></body></html>"""


def run_failure_mining(
    training_database: str | Path,
    confirmation_database: str | Path,
    config: dict,
    *,
    results_dir: str | Path = "results",
    engine_key: str | None = None,
) -> tuple[dict, Path]:
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    seed = int(config["seed"])
    set_deterministic_seed(seed)
    training_connection = connect_database(training_database)
    confirmation_connection = connect_database(confirmation_database)
    training_key = resolve_engine_key(training_connection, engine_key)
    confirmation_key = resolve_engine_key(confirmation_connection, engine_key)
    if training_key != confirmation_key:
        raise ValueError("Training and confirmation engine configurations do not match")
    training_rows = _labeled_rows(training_connection, training_key)
    all_confirmation_rows = _labeled_rows(confirmation_connection, confirmation_key)
    training_hashes = {row[0] for row in training_rows}
    confirmation_rows = [row for row in all_confirmation_rows if row[0] not in training_hashes]
    analysis_metadata = dict(
        confirmation_connection.execute(
            "SELECT position_hash, struct_pack(best_move := best_move, mate := mate) "
            "FROM engine_analysis WHERE engine_key = ?",
            [confirmation_key],
        ).fetchall()
    )
    training_matrix, feature_names = feature_matrix([row[1] for row in training_rows])
    confirmation_fens = [row[1] for row in confirmation_rows]
    confirmation_matrix, _ = feature_matrix(confirmation_fens, feature_names)
    clip = int(config["model"]["target_clip_cp"])
    training_target = np.clip(np.asarray([row[2] for row in training_rows]), -clip, clip)
    target = np.clip(np.asarray([row[2] for row in confirmation_rows]), -clip, clip)
    settings = config["failure_mining"]
    locked_features = list(settings["locked_features"])
    if locked_features != ["material", "space", "tempo"]:
        raise ValueError("Failure mining lock does not match transferable-subset-v1")
    alpha = float(config["model"]["ridge_alpha"])

    def predict(names: list[str]) -> np.ndarray:
        indexes = [feature_names.index(name) for name in names]
        coefficients, intercept = fit_ridge(training_matrix[:, indexes], training_target, alpha)
        return confirmation_matrix[:, indexes] @ coefficients + intercept

    locked_prediction = predict(locked_features)
    full_prediction = predict(feature_names)
    high_error, high_disagreement, candidate_mask = failure_candidate_masks(
        target,
        locked_prediction,
        full_prediction,
        error_threshold_cp=float(settings["error_threshold_cp"]),
        disagreement_threshold_cp=float(settings["disagreement_threshold_cp"]),
    )
    if int(candidate_mask.sum()) < int(settings["clusters"]):
        raise RuntimeError("Too few failure candidates for the configured cluster count")
    omitted_names = [name for name in feature_names if name not in locked_features]
    omitted_indexes = [feature_names.index(name) for name in omitted_names]
    means = training_matrix[:, omitted_indexes].mean(axis=0)
    scales = training_matrix[:, omitted_indexes].std(axis=0)
    scales[scales < 1e-12] = 1.0
    standardized = (confirmation_matrix[candidate_mask][:, omitted_indexes] - means) / scales
    labels, centroids = deterministic_kmeans(standardized, int(settings["clusters"]))
    categories = position_categories(confirmation_fens, confirmation_matrix, feature_names)
    phases = _phase_labels(categories)
    candidate_indexes = np.flatnonzero(candidate_mask)
    candidates = []
    for candidate_index, position_index in enumerate(candidate_indexes.tolist()):
        digest, fen, score, game_id = confirmation_rows[position_index]
        metadata = analysis_metadata[digest]
        locked_error = float(locked_prediction[position_index] - target[position_index])
        full_error = float(full_prediction[position_index] - target[position_index])
        candidates.append(
            {
                "position_hash": digest,
                "game_id": game_id,
                "fen": fen,
                "side_to_move": "White" if fen.split()[1] == "w" else "Black",
                "phase": phases[position_index],
                "forcing_proxy": bool(categories["forcing-proxy"][position_index]),
                "stockfish_cp": float(target[position_index]),
                "stockfish_raw_cp": float(score),
                "stockfish_best_move": metadata["best_move"],
                "stockfish_mate": metadata["mate"],
                "locked_cp": float(locked_prediction[position_index]),
                "full_cp": float(full_prediction[position_index]),
                "locked_error_cp": locked_error,
                "locked_abs_error_cp": abs(locked_error),
                "full_abs_error_cp": abs(full_error),
                "absolute_disagreement_cp": float(
                    abs(locked_prediction[position_index] - full_prediction[position_index])
                ),
                "high_error": bool(high_error[position_index]),
                "high_disagreement": bool(high_disagreement[position_index]),
                "cluster": int(labels[candidate_index]) + 1,
                "features": {
                    name: float(confirmation_matrix[position_index, feature_names.index(name)])
                    for name in feature_names
                },
            }
        )
    clusters = _cluster_summaries(candidates, centroids, omitted_names)

    def summarize_criterion(selected: list[dict]) -> dict:
        return {
            "positions": len(selected),
            "games": len({candidate["game_id"] for candidate in selected}),
            "forcing_fraction": float(np.mean([candidate["forcing_proxy"] for candidate in selected])),
            "locked_mae_cp": float(np.mean([candidate["locked_abs_error_cp"] for candidate in selected])),
            "full_mae_cp": float(np.mean([candidate["full_abs_error_cp"] for candidate in selected])),
            "full_better_fraction": float(
                np.mean(
                    [
                        candidate["full_abs_error_cp"] < candidate["locked_abs_error_cp"]
                        for candidate in selected
                    ]
                )
            ),
        }

    criterion_summaries = {
        "high-error": summarize_criterion(
            [candidate for candidate in candidates if candidate["high_error"]]
        ),
        "high-disagreement": summarize_criterion(
            [candidate for candidate in candidates if candidate["high_disagreement"]]
        ),
        "both": summarize_criterion(
            [
                candidate
                for candidate in candidates
                if candidate["high_error"] and candidate["high_disagreement"]
            ]
        ),
    }
    experiment_name = settings.get("experiment_name", "failure-mining")
    experiment_id = _next_experiment_id(Path(results_dir), experiment_name)
    artifact = Path(results_dir) / experiment_id
    artifact.mkdir(parents=True, exist_ok=False)
    runtime = time.perf_counter() - started
    result = {
        "experiment_id": experiment_id,
        "benchmark_version": config["benchmark_version"],
        "git_commit": _git_commit(),
        "engine_key": training_key,
        "confirmation_positions": len(confirmation_rows),
        "error_threshold_cp": float(settings["error_threshold_cp"]),
        "disagreement_threshold_cp": float(settings["disagreement_threshold_cp"]),
        "candidate_positions": len(candidates),
        "candidate_games": len({candidate["game_id"] for candidate in candidates}),
        "high_error_positions": int(high_error.sum()),
        "high_disagreement_positions": int(high_disagreement.sum()),
        "both_criteria_positions": int((high_error & high_disagreement).sum()),
        "omitted_features": omitted_names,
        "clusters": clusters,
        "criterion_summaries": criterion_summaries,
        "candidates": candidates,
        "runtime_seconds": runtime,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    write_json(artifact / "config.json", config)
    write_json(artifact / "metrics.json", {key: value for key, value in result.items() if key != "candidates"})
    write_json(artifact / "candidates.json", candidates)
    write_json(
        artifact / "environment.json",
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "duckdb": duckdb.__version__,
            "git_commit": result["git_commit"],
        },
    )
    (artifact / "report.md").write_text(_failure_report(result), encoding="utf-8")
    (artifact / "failure_explorer.html").write_text(_explorer_html(result), encoding="utf-8")
    _save_projection(artifact, standardized, labels, candidates)
    confirmation_connection.execute(
        "INSERT OR REPLACE INTO experiments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [experiment_id, experiment_name, json.dumps(config, sort_keys=True), result["git_commit"], started_at, datetime.now(UTC), runtime, str(artifact)],
    )
    confirmation_connection.execute(
        "INSERT OR REPLACE INTO benchmark_results VALUES (?, ?, ?, current_timestamp)",
        [experiment_id, config["benchmark_version"], json.dumps({key: value for key, value in result.items() if key != "candidates"}, sort_keys=True)],
    )
    training_connection.close()
    confirmation_connection.close()
    return result, artifact
