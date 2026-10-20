# PR92 KG post-apply independent review

Read-only review completed 2026-10-20. No source changes made.

## Pins and preservation

- Actual apply receipt: `Cloud-BAL/scratch/pr92_source_store_20261020/kg/kg_receipt.json`, SHA-256 `0cee86c3128b49b1317c4107537c3fd92470e819e409fc7d7ec332fbfd790030`; status `PASS`; Graphify `0.9.53`.
- Candidate checkout is clean at `5f645af5798a8d05ad6cbd429af7273bb530d2a4`. GitHub PR 92 is open, head `fix/pr92-source-graupel-store` at that SHA, base `main`.
- Receipt confirms the maintained-source inventory remains 627 entries with unchanged digest `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`. All 197 prior immutable receipt pins independently match. The old `2026-10-19` and `2026-10-20` dated snapshots remain present with their original file membership; the new `2026-10-20-source-store` snapshots are separate under KLAPS50 and Cloud-BAL.
- The Cloud-BAL private profile remains 134 nodes and 133 source links; I independently counted both the pre-apply backup graph and the current graph. Receipt records it unchanged. Protected wiki material is pinned across 13 entries. The five derived wiki outputs are the only listed wiki outputs: three reports, the replaced Graph snapshot section in `wiki/index.md`, and an appended `wiki/log.md` entry. Direct diff inspection confirms the index edits are confined to that section and the log change is append-only.

## Graph and runtime results

- The frozen graph-source scope is exactly 23 paths. The apply receipt selected 261 changed/evidence paths overall; only the frozen 23 are graph sources.
- KLAPS50: 39,132 nodes / 81,807 edges / 3,225 communities; delta +172 nodes / +277 edges (173 added IDs, 1 removed). Cloud-BAL: 13,304 / 23,357 / 1,193; same node/edge delta. Both graphs and their dated snapshots match receipt hashes. Integrity reports zero unverified nodes, malformed/dangling/self-loop/duplicate edges, and post-build errors.
- The validated evidence remains scoped: both C18 arms are `INCOMPLETE` at step 23, rc 128. The declared ice-only policy passes on 138 completed states per arm with zero active outliers and zero strict state failures; the separate generic exact-source audit, including rain, remains `FAIL`. Scientific gates remain `OPEN`, physical approval `FAIL_OPEN`.

## Extraction limits and conclusion

This is a selected-source AST/Markdown-heading refresh with no semantic refresh. Cross-file Fortran `CALL` edges are partial; generated Fortran embedded in Python strings and archived/compressed evidence are hash-bound, not separately AST-extracted. KLAPS50 and Cloud-BAL snapshots are separate. Graph freshness is navigation evidence and does not establish runtime or scientific acceptance.

No post-apply blocker found. The applied structural refresh matches the frozen receipt and preservation bounds; runtime/scientific status remains exactly as recorded above.
