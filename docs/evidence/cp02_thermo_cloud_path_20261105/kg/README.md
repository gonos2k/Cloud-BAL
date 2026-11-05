# Thermodynamic cloud-path graph preparation

The read-only `baseline.json` records 118 KLAPS50 and 122 Cloud-BAL dated snapshots (240 total), both active graph trios, five wiki pages, exact Git porcelain status bytes, Git HEADs, and the maintained `AGENTS.md` hash. The planned snapshot is `2026-11-05-thermo-cloud-path`. Stages, temporary files, and publisher backups use Lustre under `scratch/b1_thermo_cloud_path_20261105/kg_stage/`; the existing Graphify 0.9.53 environment is on `/var/tmp`.

Baseline graph statistics are KLAPS50 43,908 nodes / 91,049 edges / 3,558 communities, and Cloud-BAL 18,080 nodes / 32,531 edges / 1,599 communities. The project's `wiki/hot.md` and overview are stale from 2026-10-06; graph reports and audit log are newer. Do not infer freshness for those content pages from a graph update.

After final source, tests, actual run evidence, and independent team review, write `review/independent_kg_review.json` with `status: PASS_SOURCE_AND_EVIDENCE_REVIEW`, unique final Python `selected_source_paths`, matching `selected_source_sha256`, finalized `hash_only_sha256`, `validation_summary`, and `science_open_items`. The last field must describe actual study limitations/open questions rather than pending graph workflow. Exclude caches, locks, outgoing KG receipts and self-referential final aggregate manifest.

From the Cloud-BAL worktree, after the independent review and root source freeze:

```
/var/tmp/snow-image-cdn-graphify-venv/bin/python -B docs/evidence/cp02_thermo_cloud_path_20261105/kg/prepare_kg.py freeze
/var/tmp/snow-image-cdn-graphify-venv/bin/python -B docs/evidence/cp02_thermo_cloud_path_20261105/kg/prepare_kg.py stage --stage
```

The selected-path AST extraction and graph merge is an adapted incremental kg-update that neither scans nor prunes the full corpus. Raw pre-merge extractions are retained with SHA-256 for independent review. No edge suppression is configured. A staged integrity failure must be investigated before any narrowly scoped exception is considered; preserve the failed stage and demonstrate the exact source-level reason.

An independent stage validation and stage review must bind receipts and all 13 maintained targets before root authorizes:

```
/var/tmp/snow-image-cdn-graphify-venv/bin/python -B docs/evidence/cp02_thermo_cloud_path_20261105/kg/publish_kg.py --publish
```

The publisher performs backup, rollback and readback for two graph trios, two dated directories, and five wiki mirrors, and mirrors the Cloud-BAL graph to the worktree. All 240 previous snapshots must remain intact, yielding 119 and 123. Saved baseline porcelain allows independent comparison of unrelated dirty status entries after publication.

Only reviewed Python paths receive structural extraction; other finalized evidence is hash-bound without semantic extraction. Raw external-import edges can be absent from the merged graph when their target nodes are missing, and Fortran cross-file CALL extraction is partial. Graph freshness does not establish runtime behavior, physical correctness, conservation, or scientific validation.
