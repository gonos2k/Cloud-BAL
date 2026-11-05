# Grouped forecast KG proposal

## Scope

Refresh two maintained code graphs from one review-frozen grouped-forecast source set: KLAPS50 and Cloud-BAL. Preserve the 244 existing dated snapshots (120 KLAPS50 and 124 Cloud-BAL) and add the separate `2026-11-05-grouped-forecast` snapshots only after stage review and root publication authorization. Do not rewrite any prior dated snapshot.

## Extraction boundary

The independent source/evidence review selects a small set of changed maintained Python sources for structural extraction. A Fortran source is eligible only if the review explicitly names it and its source-to-target scope is bounded. Hash-pin every other new or changed source/evidence file without extracting it. Freeze exact source hashes and source HEAD before staging. Use the pinned Graphify 0.9.53 environment and the isolated Lustre stage under `scratch/b1_grouped_forecast_20261105/kg_stage/`.

The stage helper updates only selected manifest keys and merges only selected-path extractions. Review must verify every pre-existing manifest entry remains unchanged outside that exact set, all prior graph node IDs are retained, no selected prior node is removed without explicit review, and graph integrity counts are reported. Preserve raw extraction JSON and its hashes. Do not prune or broadly rescan either corpus.

## Readback and publication

Independent validation must bind the baseline, source selection, raw extractions, stage receipt, graph deltas, all 13 maintained graph/wiki targets, and the Cloud-BAL worktree copy inputs. Compare all 244 prior snapshot inventories byte-for-byte. Check that wiki graph-report rows, dated snapshot links and log append are the only allowed derived-index changes. Verify staged Cloud-BAL graph/report/manifest and the new dated snapshot are the exact inputs copied to the source worktree after publication. The publisher is root-only and must preserve unrelated dirty paths and roll back atomically on failure.

## Evidence limits

Graphify structural relationships and freshness do not establish successful compilation, runtime behavior, conservation, or scientific validity. Fortran cross-file `CALL` edges are partial, and edges to absent import targets may be omitted. Report graph deltas separately for KLAPS50 and Cloud-BAL and record any extraction limitations. Keep this stamp distinct from all earlier KG snapshots.
