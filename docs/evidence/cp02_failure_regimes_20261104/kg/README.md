# Failure-regimes graph preparation

The preserved read-only `baseline.json` records 117 KLAPS50 and 121 Cloud-BAL dated snapshots (238 total), active graph trios, five wiki pages, both Git HEADs, and exact porcelain status bytes. The new snapshot label is `2026-11-04-failure-regimes`. The stage and publisher backups are created on Lustre under `scratch/b1_failure_regimes_20261104/kg_stage/`; the Graphify 0.9.53 interpreter remains in its existing `/var/tmp` environment.

Baseline graph statistics: KLAPS50 43,817 nodes / 90,883 edges / 3,548 communities; Cloud-BAL 17,989 nodes / 32,369 edges / 1,599 communities. Report deltas from these separately after staging. `wiki/hot.md` was last modified on 2026-10-06 and was not refreshed by this graph preparation.

After final code, tests, evidence, and independent team review, write `review/independent_kg_review.json` with `status: PASS_SOURCE_AND_EVIDENCE_REVIEW`, final unique Python `selected_source_paths` and `selected_source_sha256`, complete finalized `hash_only_sha256`, `validation_summary`, and `science_open_items`. The last field must describe actual study limitations/open questions, not the transient pending KG stage. Exclude transient and self-referential outgoing KG receipts and final aggregate manifest. Include only finalized files, with preserved historical versions hash-only.

Run from the Cloud-BAL source worktree:

```
/var/tmp/snow-image-cdn-graphify-venv/bin/python -B docs/evidence/cp02_failure_regimes_20261104/kg/prepare_kg.py freeze
/var/tmp/snow-image-cdn-graphify-venv/bin/python -B docs/evidence/cp02_failure_regimes_20261104/kg/prepare_kg.py stage --stage
```

These do not write maintained roots. The selected-path Graphify AST merge is an adapted incremental kg-update; it does not scan or prune the corpus. A separately reviewed stage validation and stage review must bind the receipts and all 13 maintained targets before root authorizes publication:

```
/var/tmp/snow-image-cdn-graphify-venv/bin/python -B docs/evidence/cp02_failure_regimes_20261104/kg/publish_kg.py --publish
```

The publisher uses backup, rollback and readback for the two graph trios, two dated directories, and five wiki files; it also mirrors the Cloud-BAL graph to the source worktree. All 238 prior snapshots must remain intact, giving 118 and 122 dated snapshots. Exact baseline porcelain bytes allow an independent postpublication comparison of unrelated dirty entries.

Graphify covers only selected Python source structure. Hash-only files receive no semantic extraction; Fortran cross-file call extraction is partial. Graph freshness does not establish runtime behavior, physical correctness, conservation, or scientific validation.
