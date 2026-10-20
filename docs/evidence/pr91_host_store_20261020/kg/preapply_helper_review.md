# PR91 final KG helper review

Review result: **ready for the guarded apply; no blocker found**. Scope is the frozen external helper and its check-only output, not the apply result or a repeat of the 63-test/model validation.

- Frozen helper `/var/tmp/pr91_refresh_kg_host_store_20261020.py`: SHA-256 `a2b4de3e7941e3d0cf2cf8d60ee3956338fe2471df960c1f93c04bcf554ea9cf`.
- Check-only `/var/tmp/pr91_kg_check_only_final_20261020.json`: SHA-256 `33861eefe12df75935c875e4647369865418767335a73d93b8e97940be1c3c98`; `ready=true`, `CHECK_ONLY_NO_WRITES`.
- Frozen source commit `d34c6db9279275efe41af449dc9bda95975ea493`, base `3a896be3d381909f0cc61d1c0896b329b98d5aea`; exact PR91 integration manifest SHA `647afbc1c1199149d4a07051d18e9fb315d6bd9583ad4febd1846e9a51a78ac8`.

The check-only selection matches the frozen plan: 451 changed paths are hash-bound, 23 pass structural extraction, and 428 evidence files are hash-only. Both corpora remain separate and begin from the independently pinned 2026-10-19 graph snapshot. The maintained-source inventory is 627 entries with digest `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`, matching PR90. The check-only reports `verified_pre_post_equal=false` because it is read-only; the apply path takes and checks the post-refresh snapshot.

Static apply-path review found explicit pre-apply backups and hash verification for active graph files, dated graph files, prior dated snapshots, and allowed derived wiki pages. On failure it restores the backed-up files and checks protected content, maintained sources, candidate checkout, and immutable prior receipts. The Cloud-BAL private profile is checked against its pre-update corpus; protected wiki schema/content files are hashed and rechecked. `wiki/index.md` is now updated only within the `Graph snapshot` section, with UTF-8 byte prefix/suffix checks and a post-write readback. The prior `date_modified` rewrite is absent. Snapshot destinations are distinct (`2026-10-20-host-store`) for KLAPS50 and Cloud-BAL.

The integration binding reports the 240-second window COMPLETE in both arms and the 600-second window INCOMPLETE in both arms, each on the same bound executable. The helper carries explicit `FAIL_OPEN` physical approval and the remaining observation-fit, matched-response, mass/wind, water/energy, number-budget, source-footprint, and C14 source-event cause gates. Extraction limitations are stated: overlapping corpus counts are reported separately; Markdown headings and selected-source AST only; cross-file Fortran calls partial; generated/compressed sources hash-bound; graph freshness is not runtime or science validation.

No output directory exists yet (`output_exists=false`). No graph/wiki writes were performed as part of this review. The apply review remains a separate required step.
