# B1 rain-number process KG preparation

This folder records a fresh read-only baseline for snapshot `2026-11-04-rain-number-process` and provides a bounded freeze/stage helper. It does not publish to either maintained root.

## Baseline

`baseline.json` captures the maintained graph artifacts, all files in every dated snapshot, the five wiki mirrors, maintained-root Git HEAD/status digests, and the source worktree HEAD/status digest. The actual dated inventory was 116 KLAPS50 + 120 Cloud-BAL = 236. The older B1 state-path baseline has 234 snapshots and is not valid for this update.

## Freeze and stage

Run these commands from the Cloud-BAL source worktree once the final source set and team review are available:

1. Put the independent review at `review/independent_kg_review.json`. It must contain `status: PASS_SOURCE_AND_EVIDENCE_REVIEW`, the final `selected_source_paths` (all Python files), matching `selected_source_sha256`, a complete `hash_only_sha256` map for the remaining new evidence, `validation_summary`, and `open_items`.
2. Freeze with the pinned interpreter: `/var/tmp/snow-image-cdn-graphify-venv/bin/python -B docs/evidence/cp02_rain_number_process_20261104/kg/prepare_kg.py freeze`.
3. Stage only after the parent confirms final source and review: `/var/tmp/snow-image-cdn-graphify-venv/bin/python -B docs/evidence/cp02_rain_number_process_20261104/kg/prepare_kg.py stage --stage`.

The helper checks the preserved 236-snapshot baseline before and after staging. It structurally extracts only the frozen Python sources, updates only those manifest rows, hashes the remaining evidence, stages the KLAPS50 and Cloud-BAL graph layers plus five wiki mirrors under `/var/tmp`, and writes a receipt. The selected-path Graphify API extraction and merge is an adapted incremental kg-update because the standard CLI would scan the full corpus; it does not scan or prune either corpus. After independent stage validation and review bind the frozen selection and receipt, root authorization is required to run `/var/tmp/snow-image-cdn-graphify-venv/bin/python -B docs/evidence/cp02_rain_number_process_20261104/kg/publish_kg.py --publish`. The publisher backs up and reads back 13 maintained targets, mirrors the Cloud-BAL stage to the active worktree, and rolls back on failure. Prior snapshots are checked before and after; expected totals are 117 KLAPS50 and 121 Cloud-BAL.

## Extraction limits

Graphify output describes source structure only. Native source, runtime captures, and other evidence remain hash-bound unless explicitly selected as one of the reviewed Python files. Fortran cross-file CALL extraction is partial. Graph freshness does not establish runtime behavior, physical correctness, conservation, or scientific validation.
