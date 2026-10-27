# T39 closed replay graph update

This evidence-only note records the structural Graphify refresh for PR #114 at source freeze `6514cfe7a92549243c19e526ac9897e8d5ac2e63`. The source base and graph-selection base were both `60319cf552fdbb08e2787d72a531b860c929243d`.

Graphify selected three bounded Python replay paths: the first-group replay tool and test, plus the callback-producer replay helper. The three report/status documents and 24 other evidence paths were hash-bound only. The first-group replay and fatal callback replay findings remain distinct. Native O0/O2 results are scoped to the captured first-group operands and separate callback producer helper; no forecast-physics fix was made. Physical validation and the one-hour status remain OPEN, and 14UTC remains NOT_EVALUATED.

| Corpus | Before | After | Change |
|---|---:|---:|---:|
| KLAPS50 | 41,289 nodes / 85,806 edges / 3,376 communities | 41,322 / 85,876 / 3,373 | +33 nodes / +70 edges |
| Cloud-BAL | 15,461 nodes / 27,349 edges / 1,357 communities | 15,494 / 27,419 / 1,358 | +33 nodes / +70 edges |

Graphify added 33 node IDs and removed none in each corpus. Both integrity checks reported zero errors. The separate `2026-10-27-t39-closed-replay` raw and named snapshots were added to each corpus. Independent readback verified the earlier 160 dated snapshots were preserved, for 164 total.

The independent review also verified all 21 published targets, protected content, the 197 inherited immutable pins, the 250 active ROOTGO pins, unchanged non-target dirty status, and the clean source worktree. Graph freshness does not establish runtime or scientific validation. The compact [KG manifest](kg_manifest.json) binds source, stage, preflight, apply, root GO, and independent readback hashes; the [copied independent review](independent_postapply_review.json) contains the preservation checks.
