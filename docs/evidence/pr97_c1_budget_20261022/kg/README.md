# PR97 guarded KG publication

`update_kg.py` prepares separate dated KLAPS50 and Cloud-BAL snapshots for the frozen PR97 source commit. It extracts changed `docs/PR97_*`, `tools/pr97_*`, and `tests/*pr97*` paths, plus only the reviewed PR96 terminology edits in `docs/PR96_LOCAL_CLOSURE_20261021.md` and `docs/PR96_COLUMN_LIQUID_ROUNDING_20261021.md`. The focused third-pair comparison also extracts `tools/pr94_hydro_response.py` and `tests/test_pr94_hydro_response.py` so its array-norm calculation is represented. All other changed paths, including interpretation JSON, are recorded by SHA-256 only.

The helper pins the maintained PR96 receipt at `Cloud-BAL/scratch/pr96_local_closure_20261021/kg/kg_receipt.json` (SHA-256 `df34488a4350e4b1e4aea4d32a3f8aeec4c6f51113d94803f7692a21345f743c`) and the PR96 recursive helper at `scratch/pr96_local_closure_20261021/Cloud-BAL/docs/evidence/pr96_local_closure_20261021/kg/update_kg.py` in its own worktree. Its `load_previous_helpers()` result is unpacked as `(pr94_helper, protected_helper, nested_chain)`, preserving the recursive protected-content API.

## Root-side commands after freeze and review

Run from the PR97 worktree using the pinned Graphify Python interpreter. Replace the placeholders with the reviewed frozen commit and actual open PR URL:

```sh
cd /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr97_c1_budget_20261022/Cloud-BAL
/home/korea_keun/.local/share/uv/tools/graphifyy/bin/python3 docs/evidence/pr97_c1_budget_20261022/kg/update_kg.py --commit <FROZEN_COMMIT> --pr-url https://github.com/gonos2k/Cloud-BAL/pull/<NUMBER> --check-only
```

Review the emitted selection and hash-only inventory. After the source freeze, review, and required runtime/results gates are satisfied, publish with the same arguments and `--apply` instead of `--check-only`. `--apply` updates only dated graph snapshots and their derived wiki mirrors/back-pointers/audit entry. Receipt-bound graphs and backups stay in the maintained `Cloud-BAL/scratch/pr97_c1_budget_20261022/kg/` directory and must not be included in the public evidence bundle. The helper restores protected content and private profiles on failure.

Current scientific state recorded by the helper: the three C1 600-second runs (30 calls each) are COMPLETE/CLOSED; independent package review is GO while the source audit queue remains REVIEW_REQUIRED; physical approval remains FAIL_OPEN. Graph freshness does not establish runtime or scientific validation. Fortran cross-file `CALL` extraction remains partial.
