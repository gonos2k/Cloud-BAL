# PR96 guarded Graphify/KG helper

`update_kg.py` is adapted from the PR95 guarded updater. It pins the clean source base `50d11d631a59d461c37da2e8bc9666c6bcc9c380`, the PR95 KG receipt and recursively resolved PR95 → PR94 → PR92 protected-content helper chain, the current graph hashes, and the 197 inherited immutable pins. It creates separately dated KLAPS50 and Cloud-BAL snapshots and preserves existing dated snapshot directories through the inherited rollback guard.

The extraction allowlist currently covers `docs/PR96_*`, `tools/pr96_*`, `tests/*pr96*`, and the inherited exact PR95 call-budget source/test paths. `docs/evidence/**` is hash-bound only. Add any final PR96 source paths to the allowlist only after the root agent freezes the final changed-path list.

The helper requires a clean final commit and an actual open GitHub PR #96 matching that commit before either `--check-only` or `--apply` can proceed. No check or apply has been run in this local copy. The result publication records incomplete 3600-second runs; graph freshness is provenance only and does not change physical approval (`FAIL_OPEN`).
