# PR113 Graphify update

This records the bounded structural graph refresh for the hourly precipitation scorer in [PR #113](https://github.com/gonos2k/Cloud-BAL/pull/113). The source freeze is `f414d68bd6783f5a65d98950511e3385526769df`.

Graphify selected only `tools/plot_hourly_precip_scores.py` and `tests/test_hourly_precip_scores.py` for Python AST extraction. The 21 report/evidence paths, including the corrected map review and native accumulator bridge, were hash-bound only. No full graph artifacts are copied into this PR.

| Corpus | Before | After | Change |
|---|---:|---:|---:|
| KLAPS50 | 41,241 nodes / 85,679 edges / 3,368 communities | 41,284 / 85,788 / 3,345 | +43 nodes / +109 edges |
| Cloud-BAL | 15,413 nodes / 27,222 edges / 1,388 communities | 15,456 / 27,331 / 1,367 | +43 nodes / +109 edges |

Community counts changed during reclustering. Both graph integrity checks reported zero errors. Two separately named snapshots were added to each corpus (`2026-10-27-precip-hourly-scores-graphify-raw` and `2026-10-27-precip-hourly-scores`). Independent readback verified all 152 prior dated snapshots remained unchanged, for 156 total.

The independent review also verified the 21 published targets, non-target dirty status, 197 inherited immutable pins, 250 active ROOTGO pins, protected source content, and a clean source worktree. Graphify extracted code only; Fortran cross-file `CALL` extraction remains partial. Graph freshness does not establish runtime validation, scientific correctness, or forecast skill. Original RN1 files were unavailable; alternate RN1 files were rejected as a different version. See the main verification report for the evidence limits.

The [KG manifest](kg_update_manifest.json), [post-apply readback](postapply_readback.json), and [independent review](independent_postapply_review.json) contain the bound hashes and preservation checks.
