# PR100 C2 KG publication

The approved check-only plan was applied successfully by root. The apply returned code 0; the receipt is referenced by path and SHA-256 in `kg_receipt_reference.json`. The full receipt and graph payloads are not copied here.

This publication is bound to root manifest v2 (`root_integration_manifest_v2.json`) and its independently reviewed v2 check-only plan (`check_only_v2_review.txt`). The exact canonical plan SHA-256 is `fd7ce8f6dcf84e9b3366364a87ea743d0ae5c6369322dd84e54e23528909dde0`; the reviewed plan file SHA-256 is `26831d9947f568ac9a7b1f77f437e180e3aee4b56e278c113e1516b303944804`.

The graph-source freeze is `870dd5c9dac9aa1fae9f836c051cffd5699c6f85`. The earlier first runtime/diagnostic commit is `fa7f163add7c017398d118c54d541101096de6da`; the PR100 approval base is `950fd7b41af5a10ab6dd36a17098e86dd8306197`, and graph selection compares against `6ac1ddb6a50c9e4f909e47243bbd656e09fc85a3`. This preserves separate runtime/diagnostic and graph-source lineage.

The applied snapshots use ID `2026-10-22-pr100-c2-native-closure`. KLAPS50 is 40,276 nodes, 83,885 edges, and 3,283 communities (delta +338/+559/+24). Cloud-BAL is 14,448 nodes, 25,431 edges, and 1,289 communities (delta +338/+558/+20). Extraction covered 366 lineage paths: 60 selected sources and 306 hash-only paths.

The four gates retain different candidates and scopes:

| Gate | Candidate and scope |
|---|---|
| native_20s | Separate projected U/V P20 capture on C1, 20 seconds |
| off640 | C2 original OFF input, 640 seconds / 32 calls |
| water_compact_fulltile | C1 three-arm T1 source-owned replay account, retained nonzero remainder |
| bulk_candidate_640_three_arm | Original three C2 inputs, 640 seconds / 96 RK rows each |

All four root-manifest diagnostic/runtime gates are recorded `COMPLETE`. The manifest keeps physical approval at `FAIL_OPEN` and observation skill at `NOT_EVALUATED`; gate completion does not mean physical or scientific approval. The independent post-apply review is **GO** (`postapply_review.txt`, SHA-256 `98f58f269193c7327a109893c1b7ee95af18cbdc46d7265d3fa948e1975a00bb`). It confirms graph integrity, both dated snapshots, all 110 prior snapshot directories, the 627-entry maintained-source inventory, 197 pins, protected wiki/profile content, and the five authorized derived wiki edits. Existing failure/retry history remains in `initial_attempt_preservation.json`, `initial_attempt_rollback_review.txt`, and `initial_apply_rolled_back.log`.

This bounded publication includes the root manifest and exact-plan review, plus a receipt path/hash reference. It excludes full graphs, the full receipt, profile content, rollback archives, and the private plan. Graph freshness supports navigation only and does not establish runtime or scientific validation.

Extraction limitations: cross-file Fortran CALL relationships are partial, and Fortran embedded in Python strings is not extracted as standalone procedures. The archived C1 core and noncompilable PR99 transform-anchor fixture remain hash-only. These restrictions preserve source provenance without interpreting fixture text as runtime code.

The bounded publication draft was independently reviewed before the final post-review status/link update; its exact draft hashes remain in `publication_draft_review.txt`. This later metadata-only evidence commit does not change the graph-source freeze or any runtime result.
