# CP02 initial QR/QS trace Graphify update

This records the scoped Graphify update for frozen source commit `8d45862dd051d0ba76fc1e7fdb928505303d993e` (base `a777d395d7c6beed3546cad094f376301ffaf74a`). Graphify 0.9.53 ran with the pinned interpreter in isolated KLAPS50 and Cloud-BAL staging copies. The seven source files below were incrementally extracted; the other 21 changed files were hash-bound only.

## Graph deltas

| Corpus | Before (nodes / edges / communities) | After | Delta nodes / edges | Removed node IDs / edge keys |
|---|---:|---:|---:|---:|
| KLAPS50 | 41,360 / 85,962 / 3,375 | 41,378 / 85,987 / 3,381 | +18 / +25 | 0 / 0 |
| Cloud-BAL | 15,532 / 27,505 / 1,382 | 15,550 / 27,531 / 1,374 | +18 / +26 | 0 / 0 |

Graphify extracted 47 nodes and 148 edges per corpus from the selected paths. Final graph diffs added 18 node IDs in each corpus and removed none; edge-key diffs added 25 in KLAPS50 and 26 in Cloud-BAL, with no removals. Reclustering changed communities and hub-based labels (3,375→3,381 and 1,382→1,374); those are organizational changes.

The update preserved all 168 existing dated snapshots and added separate raw and named snapshots for each corpus, for 172 total. It updated each corpus graph/report, the two report mirrors, the Graph snapshot section of `wiki/index.md`, and appended `wiki/log.md`. Check-only passed for 21 publication targets; root GO applied them, and post-apply hash readback passed.

## Selected source paths

- `tools/precipitation_transitions.py` — `cfb62f678d0adad863338a0bbd4d13d1cdb60f296029dcf0a44f8f577e929406`
- `tests/test_precipitation_transitions.py` — `fa016d86d6a946f606484961941ac33a0337a85242a5163b76e14999fd4ba191`
- `docs/evidence/cp02_initial_species_20261027/extract_initial_species.py` — `030d97037ce42044926a09fbffc25007814aea0268592dd5db1c794dde22692e`
- `docs/evidence/cp02_initial_species_20261027/extract_shadow_species.py` — `b58e3ea4361489516aa9ba9fa340d1cc81f21c590f1afcd11fee6dca5d892491`
- `docs/evidence/cp02_initial_species_20261027/extract_metgrid_species.py` — `59abca4a597e45a65ff81384d3b33f4c0e59af6800b093246c72c10ee634ac5a`
- `docs/evidence/cp02_initial_species_20261027/trace_wps_species.py` — `aefa9fdc806e2217fc461df66759d4dfaa806be7922c739e07fc81acc8f8fcbd`
- `docs/evidence/cp02_initial_species_20261027/plot_initial_species.py` — `6e1d6350f5662fa7f6f5bff1b9de87e4b992ef1bf15aefd4b9b3aec7f3023581`

The remaining 21 changed paths, including docs, CSV/PNG outputs, and receipts, are listed with hashes in `manifest.json`; they were not extracted into the graph.

## Limits

This is a structural graph refresh, not runtime or scientific validation. The independent source review was limited to archived products and a post-selected 20-point sample; it did not identify the first internal QR/QS-changing operation or prove physical correctness or precipitation causality. No new forecast or Fortran compile was run.

`manifest.json` and `apply_readback.json` bind the source commit, team-review receipt, stage and plan fingerprints, exact apply decision, target hashes, and post-apply inventory.
