# PR91 portable validation binding review

Independent read-only review of the portable `final_validation.json` metadata and its refresh helper.

- Canonical receipt SHA-256 at review: `093e746ec981b9b3d51b1f49ea1e52d4d58d8512d21631f08fabcdb31e5a40c9`.
- Refresh helper: `/var/tmp/pr91_refresh_kg_host_store_20261020.py`, SHA-256 `6aebfe3427b22b9929b441a73e48c66ab5ea5e013c4f54a3e3e6aa8def6d9fc6`.
- The receipt has 57 total source-hash pins: 24 explicitly unchanged dependency paths and 33 changed selected paths. The receipt set matches the helper allowlist; selected files match the worktree and current HEAD. Each unchanged dependency matches the base commit, current HEAD, and worktree.
- Five external source-hash origins are aliased to archived repository files with identical bytes and hashes. The original origins remain recorded.
- Six declared validation logs are nonempty and hash-bound. The helper requires each log to be a regular, non-symlink file under the candidate root, in the frozen selected set, with the declared SHA-256; it also checks committed bytes with `git show`.
- All 31 staged `.log`/`.out` evidence files reviewed (243,037 bytes total) match their staged index blobs byte-for-byte. The four `SHA256SUMS` entries among them match the corresponding files.
- Receipt result fields, including 63 tests, the pinned Intel profile, native-runtime status, and `physical_approval=false`, match the preserved pre-portability receipt. This metadata normalization does not change test results or runtime claims.

No concrete portability-binding blocker was found. The final-commit `git show` binding should be rerun after the staged receipt and log evidence are committed; this review does not claim that commit-bound check has already completed.
