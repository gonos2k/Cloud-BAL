# PR74 solver rank-classification follow-up

This follow-up changes only how the small solver classifies near-dependent
equalities. A floating rank tolerance can treat a tiny but nonzero pivot as a
dependency. Such a case now reports `NUMERICAL_FAILURE` when rank remains
uncertain; it does not claim the constraints are infeasible.

Exact-rational dependency checks are limited to the original declared equality
rows and targets. They may classify an exact conflicting dependency as
infeasible or remove an exact consistent duplicate. Equalities after covariance
scaling or active-coordinate elimination use conservative numerical-failure
classification when dependency or consistency is ambiguous.

The regression uses `C=[[1,0],[1,1e-15]]` and `rhs=[1,2]`. This system has the
mathematical solution `[1,1e15]`; the configured rank cutoff cannot certify that
solution, so the expected result is numerical failure. The test also preserves
coverage for proven conflicting duplicates and consistent redundant rows.

Floating rank selection now occurs after state-unit covariance normalization.
A scalar equality `x=0.3` with state scale `1e15`, covariance `1e30`, operator
`1e-15`, and coefficient `1e-15` returns the covariant solution `3e14` with a
passing KKT certificate.

The decimal edge case from the prior PR74 validation now reports
`NUMERICAL_FAILURE` when face enumeration cannot certify a solution at the
represented bounds. The outward-rounded range check does not label that case
infeasible; the solver does not claim a successful boundary solution either.

## Validation

- `python3 -m unittest tests/test_pr73_joint_analysis.py -v`: 18 tests pass.
- `python3 -m unittest tests.test_pr74_independent_oracle -v`: 4 tests pass,
  including 396 scalar cases and six-variable covariance rescaling.
- `python3 -m py_compile tools/pr73_joint_analysis.py`: passes.
- Independent review of the final solver and test hashes passed, including the
  near-dependent, exact-conflict, and redundant-equality cases.
- The earlier pinned Intel O0/O2 endpoint validation is bound to solver SHA
  `02b2afda770760052813dc9f08cccc9fedc067ecea3966cd3e81b5cf024a360c`; it does
  not validate this rank-classification follow-up. This update adds no
  physical authority or operational claim.

The prior PR74 receipt remains unchanged. This follow-up's source and test
hashes, validation, and review result are recorded in the v2 receipt.

## Parent endpoint replay

Solver SHA `b4aadb54aa68361f883f31726c7a4b809cfcef29ff16f7eaed2daa612fc5197a`
was connected to the unchanged preserved pinned Intel O0/O2 endpoint binaries
in new scratch output directories. The generated physical control bytes match
the first batch exactly; writer/component-reader checks pass. This replay uses
the immediately preceding solver, before the unit-scaled equality fix in the
current solver SHA, and does not validate that final source. It is not a new
Fortran compile or a production pipeline/native acceptance. See
`evidence/pr74_rank_endpoint_replay_20261008/receipt.json`. The initial attempt
without the pinned runtime environment failed in the loader (libimf.so) before
execution; it is preserved separately and the successful retry sources the
pinned environment.

## Final normalized source replay

Final solver SHA `97ef288d5e32add28749bb2be36ee846e198ad38a3b048fac8797c614c8a5c12`
passes the full 53-test focused suite. Its generated controls remain byte-identical
to the first batch, and preserved pinned Intel O0/O2 endpoint binaries pass writer
and component readback in fresh scratch directories. See
`evidence/pr74_final_endpoint_replay_20261008/receipt.json`. No Fortran recompile,
canonical pipeline execution, or native physical acceptance is claimed.
