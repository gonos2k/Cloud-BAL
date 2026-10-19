# PR90 post-apply KG review (read-only)

**Verdict:** no post-apply KG integrity blocker found. The guarded apply is bound to the frozen candidate and its artifacts match the receipt. This review does not approve the physical candidate; runtime and scientific gates remain open as recorded below.

## Identity and source binding

- Receipt: `Cloud-BAL/scratch/pr90_rain_roundtrip_20261019/kg_receipt.json`, SHA-256 `42ed1de1e363f9eb2a8a584b3ed52de3487ee95157d3b15717b0748f9e50040a`.
- Apply helper: `/var/tmp/pr90_refresh_kg_rain_roundtrip_20261019.py`, SHA-256 `df56c62d707d7bc66594fb3105816e5c562eed93e47f2eae4bae5a4a25ed5387`.
- Candidate checkout `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr90_rain_roundtrip_20261019/Cloud-BAL` is at `60b02162e4f94a15db1b08cbe8a6ccd0ed9f0042`; `git status --porcelain` is empty.
- The frozen base is `3bc7bb8df6a100b60c6f8908ad93a7c3d981f360`. The selected-path list has 120 entries and its `source_sync.json` SHA matches the receipt (`b1fbf6946632a5e28b89114dfaff24f4aecc077c218d691d7465d405f1fe6752`). The separately bound integration manifest is `f4eabb1c3a4b7ee891de4efb0c81e3c83aee22a77b06ce7d77ce314ad3131488`; focused validation is `44b67fec1c1570597582bf1d97fe301fcd901ae3ae0d6e20c3f61ab1157fa841` and records 95 tests.

## Graphs, snapshots, and preservation

- The current graph hashes and both dated `2026-10-19-rain-roundtrip` snapshots match receipt values. KLAPS50 and Cloud-BAL snapshots are separate.
- Cloud-BAL: 12,982 nodes / 22,836 edges / 1,188 communities; delta +488 nodes / +731 edges, 493 added IDs / 5 removed IDs. KLAPS50: 38,810 / 81,286 / 3,173; same overlay delta. Both integrity summaries report zero duplicate, dangling, missing, or self-loop edges.
- Independently recomputed maintained-source inventory is 627 entries with digest `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`, equal to the receipt's before digest. The two private-profile preservation entries match the receipt (Cloud-BAL 134 nodes / 133 incident links; KLAPS50 zero).
- All five derived wiki hashes match. The 13 protected wiki file/directory digests match. All 17 rollback artifact hashes, ten automatic-snapshot backup hashes, and all 189 `prior_immutable_receipts` hashes match. The helper also pins the prior PR89 receipt chain at 181 entries; its stated PR89 receipt hash matches the expected `80df43e8df44698c597119db5bb70466e7bc265ee77e2f76c0cfc5bcaa5589c3`.
- In total, 246 independent artifact/hash checks passed. No graph, source, or wiki files were written during this review.

## Scope and limitations retained

The receipt explicitly limits extraction to Graphify AST and Markdown headings, with no semantic/LLM refresh; unsupported/binary selected files are hash-only. Cross-file Fortran `CALL` extraction is partial, generated Fortran inside Python strings and compressed sources is not parsed as Fortran, and external sources/runtime artifacts are outside the selected repository paths. Separate corpus counts overlap and are not additive evidence of unique project content.

Physical approval remains `FAIL_OPEN`. The bound native status is 180 seconds COMPLETE for both arms and 600 seconds INCOMPLETE for both arms (nine of 30 steps, timestep 10 fatal). The receipt leaves candidate scientific gates open, including observation fit/support, final joint-absence and number budgets, mass-wind compatibility, water/energy closure, and large AUT/G deferral rationale. Graph freshness establishes neither runtime success beyond the recorded windows nor scientific acceptance.
