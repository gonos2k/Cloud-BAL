# CP06-A stationary omega producer evidence

This directory records final pinned-Intel checks for the stationary, finite-volume dry-air-mass-flux omega diagnostic. The actual-input receipt is for processed LW3 background and the 2026-08-16 13 UTC case, on grid 235×283×22, with predeclared control support i=100:107 and j=130:137.

The actual O0 and O2 processes exited successfully and reported producer status -10, reason 12: fixed-boundary incompatibility. The mismatch through the first fail-fast column was 1.3468212844014587e5 kg/s. The stored continuity residual was not assessed after that rejection; no omega cells changed, full-state rollback was verified, and no candidate artifact was written. This is a negative actual-data result, not a candidate acceptance.

The focused O0/O2 tests passed for an analytical finite-volume fixture, including nonzero spatial omega, support identity, and fixed-boundary rejection. They do not establish observational authority or CP06-A acceptance.

`actual/input_hashes.sha256` records hashes only; no raw input payload is included. Source and executable hashes, process statuses, stdout, compile/link logs, and toolchain receipts are retained alongside the two run receipts.
