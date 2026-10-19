# PR87 graupel mixture fallback review

Date: 2026-10-19
Scope: read-only independent review of the pinned V42 source transform and host tests, plus the authorized NaN finite-check and residual-ledger regression.

## Provenance and validation

- Transform tool SHA-256: `7c79af80cafc12b1a11da378a9cf03bc6ffe9b460047aad3ba23bb2b38881ca4`
- Focused test SHA-256: `a05f695b353acdd7da7bf91df78806aff0e10b690f69e03fa0e5ad87a524a408`
- Pinned original `module_em_pr85.F` SHA-256: `5eb415ca23119460ae3dd766d9acea0f4c99b96ad576100efb95c3bb4d402a6c`
- Command: `pytest -q tests/test_pr87_graupel_cone_mixture.py`
- Result: 5 passed. The tests compile and run the extracted helpers and transaction fixture with the pinned Intel profile at O0 and O2 in fresh `/var/tmp` directories.
- Captured output: `focused-tests.log`.

## Review findings

The primary joint update retains strict graupel mass-pair validation. The fallback is attempted only after that candidate is infeasible. It reconstructs the full local candidate transactionally, requires a zero physical graupel source for the repaired pair, bitwise binds the saved base pair and advection rates to the source operands, and certifies each positive-weight donor against the strict cone. Failed certification leaves candidate fields and storage ledgers unchanged; accepted repair requires theta equal to one. The test fixture covers a later invalid source after an earlier repair, NaN mixture base weight rejection, and the successful repair's adjustment count and storage residual.

The base-weight finite test now returns before the separate negative-weight comparison, avoiding a NaN comparison under invalid-operation traps. Other examined finite checks either return before any sign comparison or combine only finite predicates.

The fallback preserves the existing face proposals but computes the seven-term mixture with a different floating-point association (REAL64 weights and selective wider accumulation). Its stored-minus-canonical candidate delta is explicitly booked as numerical storage adjustment. This does not establish exact shared-face conservation of stored fields, and the review does not constitute scientific approval or native-run validation.
