# PR102 guarded KG update

This directory carries the PR102 check-only wrapper and focused safeguards. It inherits the pinned PR98 Graphify helper and the reviewed PR101 KG receipt. The source approval base is `1e2c45eb30135582f925bc8c833d96b131af1df9`; the separate graph-selection base is `2345bc1d83eae9094225a2ddfe8879740c4d8273`.

Preflight binds the 627-entry maintained-source inventory, 197 immutable pins, protected content, current separate KLAPS50 and Cloud-BAL graphs, and PR101's 116-folder published inventory. That inventory contains 112 inherited folders plus two automatic raw-date folders and two separately named final PR101 snapshots. Each of the four additions remains individually hash-bound. The automatic raw-date snapshot date is captured from the local date in the check-only plan; crossing midnight changes the plan hash and invalidates the prior GO. The named PR102 snapshot keeps the project-start date. PR101 evidence is hash-only; graph selection is limited to PR101 lineage, PR102 source/docs/tests, and the approved changed PR86 runner/test.

Four runtime gate records (`candidate`, `consumer`, `nativecapture`, `C2_640`) must each state `OPEN` or `COMPLETE`, with evidence hash, candidate/revision, and scope. If a run is incomplete, retain its receipt and describe that outcome under an `OPEN` gate. Keep physical approval `FAIL_OPEN` and observation skill `NOT_EVALUATED` until separately approved.

After source freeze and confirmation that the actual Cloud-BAL PR is open against `main`, run the pinned Graphify interpreter in `--check-only` mode using `apply_kg.py`. Review the exact plan hash and both corpus selections. Applying later requires that hash and a root GO JSON containing `decision: GO`, the same `plan_sha256`, the same `source_commit`, `automatic_snapshot_date`, and `reviewed_by`. This preparation did not run preflight, Graphify, check-only, or apply.

The wrapper records separate dated snapshots, report/wiki hashes, and extraction limits. Fortran cross-file CALL extraction remains partial; graph freshness is navigation evidence and does not establish runtime or scientific validation.
