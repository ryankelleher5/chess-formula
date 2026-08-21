# Research Log

This file is append-only. Corrections should be added as dated notes rather than erasing earlier interpretations.

## 2026-08-20 — Experiment 001: first linear pipeline

### Hypothesis

A small, inspectable linear combination of human-readable features can preserve a measurable portion of shallow Stockfish judgment on positions from unseen games.

### Method

Ingest a six-game local PGN; sample every fourth ply after ply four; assign games deterministically to train/validation/test; deduplicate rule-relevant FEN state; label positions with a locally recorded Stockfish configuration; fit a ridge-linear model to 16 White-relative features; evaluate on the frozen `baseline-v1` test split.

### Result

Pending the first verified end-to-end run. The generated experiment report is the authoritative numerical record and this entry will be completed before the milestone commit.

### Interpretation

Pending. The sample is designed to validate the scientific apparatus, not support a strength claim.

### What failed

Pending.

### Next experiment

To be selected from the observed error distribution after the verified run.

