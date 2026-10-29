# CP02 thermodynamic response KG preflight

- Baseline captured 2026-10-29 against Graphify 0.9.53 and source commit `8fc72694412e39453dd35574ccfc96c8c6632d4c`.
- The maintained KLAPS50 and Cloud-BAL graphs were recorded separately in `baseline.json`; their graph, manifest, top-level report, exact dirty status, and wiki report/index/log hashes are bound there.
- All 194 prior directories whose first four name characters are digits were recursively hashed: 95 under KLAPS50 and 99 under Cloud-BAL.
- At this pre-final point, the source selection was frozen for staging only; the final freeze and successful publication are recorded below. The isolated stage helper refuses extraction without a GO file bound to the frozen selection lock; the publish helper refuses writes without a separate GO bound to stage receipt and validation.
- The stage selection now contains six frozen Python paths: both response tool/test pairs and both selected analysis plot scripts. Runtime and binary evidence scripts remain hash-only.
- Existing graph context was read directly from `graph.json`, without running a query command that could refresh data. Related Cloud-BAL nodes include `thermo_output_certificate.py`, its `certify_actual_saturation_output()` function and storage diagnostics, and `pressure_transition_reference.py` interval-arithmetic certificate helpers with liquid/ice boundary tests. This is structural context, not validation evidence.
- Extraction limitations to carry into the eventual report: only frozen Python paths should be extracted; all other changed files are hash-only; Fortran cross-file CALL extraction is partial; graph freshness does not validate runtime behavior, physical assumptions, or scientific approval.

## Initial preflight state (superseded by final stage below)

- Baseline verifier passed read-only against the maintained roots.
- Stage and publish helpers passed Python syntax compilation and `--help` checks.
- No extraction, staging, maintained graph/wiki write, or publication was performed.
- Graph deltas and final extraction counts are pending the frozen selection and explicit GO.

## Stage attempt and post-stage audit

- The six frozen paths were extracted in an isolated Graphify 0.9.53 stage; no maintained graph/wiki files were written. The stage receipt reports KLAPS50 +87 nodes/+215 edges and Cloud-BAL +87 nodes/+211 edges; all staged integrity counters were zero.
- The first stage attempt using system Python stopped before merge because that environment lacked `rapidfuzz`; it made no maintained writes. The successful retry used the pinned Graphify uv-tool interpreter.
- After successful staging, a source hash audit found one nonselected hash-only file changed: `docs/CP02_THERMO_RESPONSE_20261029.md` (expected `9f47bef71dfa1cbbb84d072dc82a50108191c18c482578406285d590eecf8d26`, current `2286aed2c183f760fe7ed67dee503748610ed81b9d6a9a0a2cf7b0edfdee2887`). Selected six file hashes still match.
- The stage is marked not publishable pending a renewed source freeze and GO; see `stage_postcheck_20261029.json`. The maintained 194-snapshot baseline verifier still passes.

## Final staged Graphify update and publication

- The final source freeze is `cp02-thermo-response-final-freeze-20261029`, source base `8fc72694412e39453dd35574ccfc96c8c6632d4c`. Six Python paths were structurally extracted: the two response tools, their two tests, and both analysis plot scripts. The finalized report `docs/CP02_THERMO_RESPONSE_20261029.md` is hash-bound at `2286aed2c183f760fe7ed67dee503748610ed81b9d6a9a0a2cf7b0edfdee2887`; 342 stable capture/result files were also hash-bound. Runtime/binary evidence Python scripts and all other nonselected evidence remain hash-only.
- Graphify 0.9.53 ran through the pinned uv-tool interpreter. The first system-Python attempt stopped before graph merge because it lacked `rapidfuzz`; the retry succeeded in a separate scratch tree. The earlier successful stage whose hash-only report later drifted remains recorded as a nonpublishable attempt.
- Final graph deltas: KLAPS50 +87 nodes / +215 edges / communities 3389→3408; Cloud-BAL +87 nodes / +211 edges / communities 1422→1412. All prior node IDs were preserved and every graph-integrity counter was zero.
- The final stage passed with the report and all six selected source hashes intact. Publish-time readback verified all 17 graph, dated-snapshot, and wiki files. The 194 prior dated snapshots remain unchanged (95 KLAPS50, 99 Cloud-BAL); one separately dated snapshot per corpus brings the maintained total to 196. Unrelated dirty status remains unchanged.
- A first publish attempt hit a helper `NameError` after beginning writes. Rollback restored the exact baseline; that attempt and backup are recorded in `publish_attempt01_rollback.json` and `/var/tmp/cp02_thermo_response_kg_20261029/publish-backup`. The corrected helper passed its retry and readback; its final rollback backup is `/var/tmp/cp02_thermo_response_kg_20261029/final-publish-backup`.
- Separate native evidence records three-arm scoped PASS with 25 core fields and 31,200 byte comparisons per arm matching, plus 52 inner write events. Those runtime observations are separate from the structural KG and do not prove physical causality or scientific correctness. Forecast completion remains open; no forecast completion is claimed. Fortran cross-file CALL extraction is partial.

## Final receipts

- `stage_receipt.json`: isolated stage; no maintained writes.
- `stage_validation.json`: `PASS_STAGED_ONLY`, zero integrity counters, final six-path/report freeze.
- `publish_receipt.json`: `PUBLISHED_AND_READBACK_PASS`.
- `postpublish_readback.json`: independent post-publication hash and snapshot readback, `PASS`.
- `publish_attempt01_rollback.json`: preserved history of the helper bug and verified rollback.
