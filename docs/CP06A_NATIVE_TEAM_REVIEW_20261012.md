# CP06-A and native baseline team review — 2026-10-12

Reviewed the frozen producer and native diagnostic changes; the final
`cloud_bal_balance_operator.f90` SHA256 is
`878a499c9ec35d081e38ec0be291036706d88364cfc7d8592fd49f19c422bbf7`.
The independent source review found no code blocker. The stationary-omega
recurrence matches the maintained finite-volume face signs and interpolation;
the free center value minimizes change with represented dry-air mass weights.
It keeps the supplied vertical boundaries fixed, rejects incompatible columns,
changes omega only on complete controlled columns, and returns the original
state on failure. Its stored-float residual check includes both center-side face
contributions. The actual runner writes an artifact only after a successful
diagnostic and identifies that artifact as diagnostic-only.

The focused analytical test passed at O0 and O2, covering a nonzero spatial
solution, support and state preservation, and rejection with full-state rollback.
The four existing balance, partial-face, pipeline, and prebalance programs also
passed at O0 and O2 (eight runs); no full `run_unit_tests.sh` run is claimed.
See [focused producer evidence](evidence/cp06a-stationary-20261012/README.md)
and [existing regression receipt](evidence/cp06a-regression-20261012/receipt.json).

On the pinned 2026-08-16 13 UTC processed inputs, both O0 and O2 actual runs
rejected the fixed-boundary compatibility condition in the predeclared 8×8
region: 1,280 cells, with a 134,682.1284 kg/s mismatch through the first failing
column. No cells changed, the stored residual was not assessed after fail-fast,
and no candidate artifact was written. The input omega boundaries are copies
of analyzed LW3 omega, not independent observations. This result does not
establish a CP06-A candidate or physical acceptance.

The native evidence contains two eligible paired comparisons (four startup
processes) within ten recorded WRF starts. With the executable and `-fpe0`
fixed, the FTZ/DAZ-only pair traps at the same Noah `DIVPS`; GDB operands and
disassembly identify unused upper-lane `0/0` while the scalar result lanes are
finite. Rebuilding both Noah objects together under strict O0 plus `-no-vec`
moves both arms through Noah, then they trap at KDM6 `radar_init` on `1/xam_g`
with `xam_g=0`. That combined diagnostic does not isolate `-no-vec` as the
cause. No model source or physics was changed, and neither pair reaches time
integration. See [native policy receipt](evidence/native-controlled-20261012/receipt.json),
[execution counts](evidence/native-controlled-20261012/execution_counts.json),
and [scalar Noah diagnostic](evidence/native-controlled-20261012/scalar_noah/README.md).

**Review disposition:** code review clear; scientific and native gates remain
open. The present evidence supports an analytical producer test and two
negative actual/native diagnostics. It does not support observed omega
authority, joint H/B/R estimation, native acceptance, time response, or
promotion. The detailed stage gates remain in the [execution checklist](FAST_COMPLETION_CHECKLIST_20261012.md).
