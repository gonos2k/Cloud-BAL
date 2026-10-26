# PR103 KG staged-report compatibility review — 2026-10-26

## Scope

Read-only review of the staged Graph Freshness transform, its three focused
CLI-style regressions, the revised private-output path, and maintained-tree
state after the preceding failed stage. No Graphify, CHECK_ONLY rerun, staging,
APPLY, or maintained-tree write was performed by this reviewer.

## Failure and fix

The preceding APPLY reached both staged Graphify updates, then stopped before
maintained publication because Graphify 0.9.53's cluster-only reports had no
`## Graph Freshness` section. The failed execution record reports
`STAGING_FAILED_NO_MAINTAINED_WRITES`; its staged report hashes and no-write
result are preserved in
`/var/tmp/pr103_kg_freshness_failure_review_20261026.json` (SHA-256
`95dfa433ca5e08d705c1aa199027f8b0b85f84b22b9c158aaf703206e20ca864`).

`update_graph_freshness` now appends the section when there are zero matches,
replaces it when there is one, and rejects duplicates. The append fixture
matches the actual staged Cloud-BAL report header and first sections exactly.
Tests also verify replacement leaves surrounding headings intact and duplicate
sections reject before stage publication. The recorded focused suite reports
18 passing KG-guard tests.

Reviewed hashes:

- `apply_kg.py`: `02e5df2d95e49512f606cb0634db50b2d07952480fab9fa5b9e29dab058c415d`
- `preflight_kg.py`: `78b87ee045177cdbd608867463b2555935c47cc6133060b06e621792aa77e5e3`
- `test_pr103_kg_guard.py`: `06d1f92dcb36d24e9145548244c74f6c7985939208d89b6b556700b5c523f400`

The preflight now selects a fresh private output directory at
`/var/tmp/pr103_kg_apply_v2_20261026`, leaving the failed private output at
`/var/tmp/pr103_kg_apply_20261026` intact. The new path is currently absent.
The previous plan fingerprint is invalidated by the source/preflight change;
generate and review a fresh CHECK_ONLY plan after commit before any APPLY.

## Preserved state and remaining guards

Against the previous hash-bound baseline, maintained graph artifacts,
Graphify metadata, and five derived wiki files remain unchanged. All 120
pre-existing dated folders and 472 members still match; all four planned
publication targets remain absent. The actual report normalization happens in
private staging. Its later wiki transforms retain explicit guards for the two
PR102 corpus rows, the Graph snapshot heading, one `date_modified` field, and
the append-only dated log entry. The publisher still verifies staged inventory
before publication and retains graph/wiki backups plus rollback verification.

One documentation follow-up remains: `guard_review_fix_20261026.md` still says
the publisher had not been run after the earlier API fix. That statement
predates the now-preserved failed staging attempt and should be amended or
clearly marked historical before PR publication.

## Outcome

**GO for the staged-report compatibility fix and focused regression.** No
maintained-state or rollback blocker was found. This does not approve a new
plan or APPLY. Physical approval remains `FAIL_OPEN`; observation skill remains
`NOT_EVALUATED`.
