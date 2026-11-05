# Grouped forecast graph preparation

The read-only `baseline.json` binds 120 KLAPS50 and 124 Cloud-BAL dated snapshots (244 total), both active graph trios, five wiki mirrors, exact Git porcelain status bytes, Git HEADs, and the maintained `AGENTS.md` hash. Its SHA-256 is `6f2c341aface4c1ac2167cc3df3004dc0e95dff26dc74286c46329eabc91feb0`. The planned separate snapshot is `2026-11-05-grouped-forecast`. Stage files, temporary files, and publisher backups use Lustre under `scratch/b1_grouped_forecast_20261105/kg_stage/`; the existing Graphify 0.9.53 environment is on `/var/tmp`.

Current baseline graph statistics are KLAPS50 44,381 nodes / 92,054 edges / 3,624 communities and Cloud-BAL 18,553 nodes / 33,501 edges / 1,634 communities. `wiki/hot.md` and `wiki/overview.md` are stale from 2026-10-06; graph reports and audit log are newer. This graph preparation does not change those content pages or establish runtime or scientific validity.

The baseline was captured with `python -B docs/evidence/cp02_grouped_forecast_20261105/kg/prepare_kg.py capture-baseline`; verify it read-only with the helper before freeze. After final source, evidence, validation and independent team review, write `review/independent_kg_review.json` with `status: PASS_SOURCE_AND_EVIDENCE_REVIEW`, unique reviewed Python `selected_source_paths`, matching `selected_source_sha256`, finalized `hash_only_sha256`, `validation_summary`, and `science_open_items`. Describe actual scientific limitations and remaining questions, not transient graph workflow status. Exclude caches, locks, outgoing KG receipts and self-referential final aggregate manifest.

After root signals the final source and review, run from the Cloud-BAL worktree:

```
/var/tmp/snow-image-cdn-graphify-venv/bin/python -B docs/evidence/cp02_grouped_forecast_20261105/kg/prepare_kg.py freeze
/var/tmp/snow-image-cdn-graphify-venv/bin/python -B docs/evidence/cp02_grouped_forecast_20261105/kg/prepare_kg.py stage --stage
```

The selected-path AST extraction and merge is an adapted incremental kg-update; it neither scans nor prunes the corpus. Raw pre-merge extractions are retained with SHA-256 for independent review. No edge suppression is configured. Investigate any staged integrity failure and preserve its attempt before considering any narrowly evidenced correction. External-import edges may be absent if their target nodes are absent, and Fortran cross-file CALL extraction is partial.

A separate independent stage validation and review must bind receipts and all 13 maintained targets. **Root alone runs the publisher**, after review and its authorization. The publisher backs up, rolls back on failure, and verifies both graph trios, two dated directories and five wiki mirrors, and mirrors Cloud-BAL to the active worktree. The prior 244 snapshots must remain intact, yielding 121 and 125 snapshots (246 total); saved porcelain supports independent comparison of unrelated dirty status entries.
