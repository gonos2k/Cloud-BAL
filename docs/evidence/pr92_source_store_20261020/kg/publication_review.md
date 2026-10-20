# PR92 compact KG publication review

Read-only review completed 2026-10-20 against `Cloud-BAL/docs/evidence/pr92_source_store_20261020/kg`.

## Verified

- The bundle has 18 files total. All 17 entries in `SHA256SUMS` verify. The checksum manifest does not list itself; the other 17 files, including `package.json`, are covered. `package.json.files` lists the 16 payload files besides itself and the checksum manifest.
- Package and receipt agree on PR #92 (`https://github.com/gonos2k/Cloud-BAL/pull/92`), frozen source commit `5f645af5798a8d05ad6cbd429af7273bb530d2a4`, base `71b8c1d5dae181c163d04eabac9cf8f80134f417`, and snapshot `2026-10-20-source-store`. The worktree HEAD is the frozen source commit; the only pending working-tree item is the untracked KG evidence bundle, so the pending delta is evidence-only.
- KLAPS50 and Cloud-BAL reports are separately dated 2026-10-20. Receipt/package counts agree: KLAPS50 39,132 nodes / 81,807 edges / 3,225 communities (delta +172 nodes, +277 edges, +33 communities); Cloud-BAL 13,304 / 23,357 / 1,193 (delta +172 / +277 / +8). The wiki index records both snapshots. Reports and receipt state the selected-source AST/Markdown scope, partial cross-file Fortran CALL extraction, and navigation-only freshness limitation.
- No full graph file is included; `graph_payload_included` is false. Private profile contents are absent. The receipt says the Cloud-BAL profile source remains unchanged, and its profile node/link counts are reported as preservation metadata only. A bounded keyword scan found no credentials or profile contents in the uncompressed payloads.
- Runtime/science wording is accurate: both C18 arms are INCOMPLETE, rc 128, 23 completed steps / 460 seconds, with the T24 freezing failure and unresolved upstream cause. README now explicitly says the separate declared QI/NI inactive/active ice policy passes over completed states while generic exact-source FAIL remains preserved. Physical approval remains FAIL_OPEN and the four broader scientific gates remain open.
- The rollback record is included: first environment attempt aborted and rolled back; rollback check-only is recorded as `CHECK_ONLY_NO_WRITES` against the frozen source with the retained Python/Graphify environment details. The review does not present that failed attempt as a successful apply.

## Checksum count note

The task requested verification of 18 checksums; the published manifest contains 17 entries because it correctly excludes its own self-referential hash. This covers all 17 other files in the 18-file bundle. No checksum mismatch was found.

## Conclusion

No publication blocker found in the bundle content or bindings. Preserve the distinction between structural KG maintenance, incomplete native runs, and open physical/scientific approval when publishing.
