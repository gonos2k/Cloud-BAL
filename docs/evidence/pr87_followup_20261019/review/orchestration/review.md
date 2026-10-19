# PR87 graupel-only failure probe review

Reviewed 2026-10-19 against the frozen orchestration candidate.

## Bound inputs

- `tools/pr87_graupel_cone_mixture.py` SHA-256: `784520d8796f67e4f3c1aa057b20b3b47e124a1b64406b27d94887cf9073d279`
- `tests/test_pr87_graupel_cone_mixture.py` SHA-256: `30e589a6781b81c0dc56fe01ccd97c8e9366fc75335abe9fde40300281a61056`
- Frozen base `module_em_pr85.F` SHA-256: `5eb415ca23119460ae3dd766d9acea0f4c99b96ad576100efb95c3bb4d402a6c`

## Review and validation

The inserted probe follows `find_failed_baseline_pairs()` and precedes the existing gate `IF (.NOT.ANY(failed_pairs(3:4)))`. It runs only when the G flag is set, certifies only pair 4, and clears only `failed_pairs(4)` after the full G scan succeeds. It uses local copies of candidate Q/N arrays and local storage ledgers; source inspection confirms it does not write shared candidate state, storage ledgers, `feasible`, `theta`, or rejected totals. The existing all-pair evaluation and source-first gates remain intact, so an uncertified G failure or any rain-pair failure still blocks cloud/ice source-first handling.

The focused tests cover a combined cloud/G failure with successful G-only certification, an unmatched G source that retains the G failure flag, unchanged candidate, ledger, feasibility, and theta state, and rejection by the subsequent all-pair attempt when cloud remains invalid. The probe's feasibility/theta snapshots are checked immediately on both successful and rejected probes.

Validation: `pytest -q tests/test_pr87_graupel_cone_mixture.py` — **6 passed**. A separate transformed-source assertion verified probe ordering, the unchanged rain/G gate, pair-4-only certification, and that the probe body contains no writes to the shared candidate or feasibility state.

## Review status

No orchestration blocker found. The test-only update directly asserts that both successful and rejected probes preserve global feasibility and theta, addressing the earlier coverage note.
