# PR90 focused-validation receipt audit

Audit date: 2026-10-19
Worktree: `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr90_rain_roundtrip_20261019/Cloud-BAL`
Mode: read-only metadata/evidence audit; no tests rerun and no repository/evidence files changed.

## Receipt identity and scope

- Receipt: `docs/evidence/pr90_rain_roundtrip_20261019/review/focused_validation.json`
- SHA-256: `44b67fec1c1570597582bf1d97fe301fcd901ae3ae0d6e20c3f61ab1157fa841` (matches requested pin).
- Declared status `PASS`; declared `test_count` 95; `physical_approval` is `false`.
- Scope explicitly limits this evidence to pinned Intel source-form/component and metadata regressions. It states selected native runtimes and scientific approval are separate.

## Pytest manifest and result

The receipt's command is `python -m pytest -q`, followed by exactly the 20 paths in its `test_files`, then `--junitxml=/var/tmp/pr90_final_focused_tests_20261019.xml`. The command's 20 test arguments match the manifest list exactly, and its `test_file_sha256` keys match the same list. All 20 current test-file hashes match their receipt pins.

- Receipt JUnit artifact: `docs/evidence/pr90_rain_roundtrip_20261019/review/focused_tests.xml`
- JUnit SHA-256: `a457d176ca82070e1f308a59400609e57a62bf74be01ae5565c1c77fc4620b44` (matches receipt).
- JUnit reports 95 cases, 0 failures, 0 errors, 0 skips; the count agrees with the receipt. Its test cases do not carry `file` attributes, so the exact per-file association is evidenced by the receipt command/list and test-file digest map rather than JUnit attributes.
- Receipt log: `docs/evidence/pr90_rain_roundtrip_20261019/review/focused_tests.log`
- Log SHA-256: `cec8e3b53d79799f1f12a83adcf85e24a722f311135e17154d76c06e07cea047` (matches receipt). Log ends with `95 passed in 21.90s`.

## Source and compiler pins

- All 21 entries in `source_hashes` match the current worktree files byte-for-byte, including the transformed source/tests and `src/common/cloud_bal_joint_transport.f90`.
- `tests/intel_toolchain.sh` current SHA-256 is `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`, matching the receipt's compiler-profile pin.
- Standalone source `tests/test_joint_qnb_transport.f90` current SHA-256 is `1a1368f6af6e287ad571f7b8c9f482653bcf4789adb04371345a861c189aead8`, matching the recorded digest. Its log SHA-256 is `cbd3bdfc3f4a3673f5cc5b4945c5b85783737e46ec9a2c2f3014a27c08d5303b`, matching the receipt. The original log reports pinned `tests/intel_toolchain.sh`, fresh scratch builds, and PASS/return code 0 for both O0 (`/var/tmp/pr90_joint_original_O0_lmogi9h1`) and O2 (`/var/tmp/pr90_joint_original_O2_x89qdhif`).

## Interpretation boundary

This is a consistent, hash-bound record of the focused 95-test run and the separately logged O0/O2 standalone test. It does not establish full native-run completion, whole-physics behavior, or scientific approval. The concurrent C7 native run was reported as still running; it is separate evidence and must not be represented as validated by this focused receipt.
