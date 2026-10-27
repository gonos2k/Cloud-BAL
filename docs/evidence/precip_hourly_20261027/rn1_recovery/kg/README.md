# RN1 recovery graph update

This evidence-only note records the structural Graphify refresh for the RN1 recovery changes in [PR #113](https://github.com/gonos2k/Cloud-BAL/pull/113). The source freeze is `ddb63a0445823b97fd04dcd07a6b7b3c54ffbddc`; graph selection was based on the prior PR113 code graph at `f414d68bd6783f5a65d98950511e3385526769df`.

Graphify selected only the scorer and its focused test for Python AST extraction. The updated verification report and 40 evidence paths were hash-bound only. The six canonical RN1 source files were recovered and hash-matched, and all 108 raw score rows were replayed. Spatial coverage and observation independence remain open; this graph update does not establish runtime validation, scientific correctness, or forecast skill.

| Corpus | Before | After | Change |
|---|---:|---:|---:|
| KLAPS50 | 41,284 nodes / 85,788 edges / 3,345 communities | 41,289 / 85,806 / 3,376 | +5 nodes / +18 edges |
| Cloud-BAL | 15,456 nodes / 27,331 edges / 1,367 communities | 15,461 / 27,349 / 1,357 | +5 nodes / +18 edges |

Graphify added nine node IDs and removed four for each corpus. Community counts shifted during reclustering. Integrity diagnostics reported zero errors. The separately dated `2026-10-27-precip-rn1-recovery` raw and named snapshots were added to each corpus; independent readback verified the prior 156 dated snapshots were preserved, for 160 total.

Independent review verified all 21 publication targets, exact preservation of non-target dirty status, protected content, 197 inherited immutable pins, and the 250 active ROOTGO pins. See [kg_manifest.json](kg_manifest.json) and the copied [independent post-apply review](independent_postapply_review.json) for the bound evidence hashes and checks.
