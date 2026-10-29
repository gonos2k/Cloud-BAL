# CP02 zero-candidate KG preflight

Graphify 0.9.53 queried the maintained KLAPS50 graph for source-write capture and validation relationships. It identifies `cp02_source_write.py` and its analyzer and validators, corresponding tests, and prior capture runtime helpers. Graph queries guide navigation; source, executable, captures and tests are authoritative.

A fresh read-only baseline verifies 41,991 nodes / 87,284 edges for KLAPS50 and 16,163 / 28,819 for Cloud-BAL; it hashes both graph layers, derived wiki files, exact dirty statuses, and all 202 prior separately dated snapshots (99 KLAPS50 and 103 Cloud-BAL). Baseline verification passed. Isolated selected-path staging awaits frozen source scope and final validation/open items; publication requires separate independent review and root GO.

Only selected Python files will receive structural extraction; documents and non-Python evidence are hash-bound without semantic extraction. Fortran cross-file CALL extraction is partial. Graph freshness does not establish runtime behavior, physical assumptions or scientific validation.

## Isolated staged update

The reviewed seven Python paths were structurally extracted and 35 stable report, binary, helper, analysis and final compressed capture files were hash-bound; mutable reviews, validation and KG receipts were excluded. The selected-only manifest update used `scan_corpus=None`; no corpus scan or pruning occurred. KLAPS50 changed 41,991 / 87,284 / 3,417 to 42,038 / 87,364 / 3,421; Cloud-BAL changed 16,163 / 28,819 / 1,435 to 16,210 / 28,898 / 1,439 (nodes / edges / communities). All prior node IDs and untouched manifest rows were preserved, integrity counters are zero, all 202 dated snapshots and maintained baseline files and statuses remain unchanged. Final validation and open items are in the staged wiki log. `stage_receipt.json` and `stage_validation.json` bind the stage; independent review and root GO precede publication.

## Publication and readback

Guarded publication installed separate `2026-10-29-cp02-zero-candidate` snapshots for the two maintained corpora. Readback verified all 13 destination targets, including each snapshot's three files; all 202 prior dated snapshots remain unchanged, yielding 100 KLAPS50 and 104 Cloud-BAL dated snapshots. All seven selected and 35 explicit hash-only source bindings match. Unrelated dirty status is unchanged, which does not prove byte identity of unrelated files. The published wiki log matches the reviewed staged hash and includes final validation and open items; no post-publication append was made. `publish_receipt.json` and `postpublish_readback.json` record these checks. Independent publication review remains separate.
