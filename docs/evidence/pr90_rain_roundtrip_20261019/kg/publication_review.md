# PR90 KG publication review — 2026-10-19

Read-only review of the publication-only additions in the PR90 Cloud-BAL worktree.

## Result

No publication blocker found. The two new publication paths are the only worktree changes: `docs/PR90_KG_MAINTENANCE_20261019.md` and `docs/evidence/pr90_rain_roundtrip_20261019/kg/`. `git diff --exit-code` passed for tracked files. The bundle contains 12 payload artifacts plus `SHA256SUMS`; all 12 listed payload hashes match.

## Identity and evidence bindings

- Applied receipt SHA-256 is `42ed1de1e363f9eb2a8a584b3ed52de3487ee95157d3b15717b0748f9e50040a`; it binds frozen source commit `60b02162e4f94a15db1b08cbe8a6ccd0ed9f0042`, base `3bc7bb8df6a100b60c6f8908ad93a7c3d981f360`, and 120 selected paths.
- `source_sync.json` SHA-256 `b1fbf6946632a5e28b89114dfaff24f4aecc077c218d691d7465d405f1fe6752` matches the receipt and repeats the same commit and 120 paths.
- The copied apply helper `update_kg.py` SHA-256 is `df56c62d707d7bc66594fb3105816e5c562eed93e47f2eae4bae5a4a25ed5387`, as pinned in the prior frozen review.
- `check_only.json` SHA-256 `9f49802071ab565e187f4358f9892b094576eda67668efcd7fff2733dbc63547` matches the previously reviewed preflight artifact; it is `ready: true` at the frozen commit. The bundled frozen and post-apply review copies hash to `c08c435ae7b0d96ca4ceb0fa2dd840983e4d25ace43411356523de074291ad2e` and `a139fa6c111268ab4086b7532637ffde4fccfe78f038a0256ea9a2ef9012a013` respectively.
- Receipt bindings resolve to the current candidate integration manifest SHA `f4eabb1c3a4b7ee891de4efb0c81e3c83aee22a77b06ce7d77ce314ad3131488` and focused validation SHA `44b67fec1c1570597582bf1d97fe301fcd901ae3ae0d6e20c3f61ab1157fa841`. The validation records 95 tests, zero failures/errors/skips, and pinned Intel O0/O2 standalone evidence.

## Graph counts and publication copies

The two distinct dated graph snapshots and the index report the same UTC timestamp, `2026-10-19T12:23:50+00:00`. Receipt backup graph hashes match the check-only baseline hashes. Recounting the graph payloads and comparing them with the preserved baseline gives:

- KLAPS50: 38,322 → 38,810 nodes (+488), 80,555 → 81,286 links (+731), 3,123 → 3,173 communities; 493 node IDs added and 5 removed.
- Cloud-BAL: 12,494 → 12,982 nodes (+488), 22,105 → 22,836 links (+731), 1,121 → 1,188 communities; 493 node IDs added and 5 removed.

Both snapshots have zero missing endpoints, exact duplicate links, or self-loops in the recount. The corpora overlap; the document correctly presents separate counts and does not sum them.

All five compressed derived wiki copies decompress to the current KLAPS50 root wiki content and match the recorded raw SHA-256 and byte counts. The index SHA matches the receipt. For the log, the saved pre-apply backup hash equals the published `before_sha256`; current `wiki/log.md` begins byte-for-byte with that backup, and the decompressed published append equals the entire post-backup suffix (4,034 bytes). This establishes append-only preservation for the checked log.

## Scientific scope and extraction limits

The publication accurately retains the applied receipt's state: paired 180-second runs are COMPLETE for both arms at 9/9 calls; paired 600-second runs are INCOMPLETE at 9/30 calls, return code 1, with the tenth-call host joint-candidate fatal recorded. The single executable hash is shared across both windows. `physical_approval` remains `FAIL_OPEN`, and the candidate science gates remain open. No text promotes the 600-second result or graph refresh to physical approval.

The receipt and report agree on Graphify 0.9.53, AST/Markdown-heading extraction without semantic refresh, and 16 unsupported/binary selected paths that are hash-bound only. The report also retains the partial Fortran cross-file CALL and generated-Fortran-in-Python extraction limitations and excludes external runtime arrays from the graph scope.

## Conclusion

The metadata-only publication is consistent with the applied receipt, the frozen preflight/review chain, graph snapshots, and maintained wiki copies. No blocker to committing these publication files was found. This review did not run graph refreshes, alter source, or change the worktree.
