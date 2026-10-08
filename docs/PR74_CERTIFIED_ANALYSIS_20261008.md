# PR74 certified small-analysis solver fixes

PR74 addresses two numerical defects in the manufactured small-analysis solver:

1. Active state bounds are imposed by eliminating fixed coordinates from each
   enumerated face. The returned active state is assigned from its declared
   bound after the free coordinates are solved, so a lower-bound result does not
   fail a strict comparison because of a value such as `0.2999999999999999`.
2. Background and observation covariances are normalized by their own marginal
   standard deviations before Cholesky factorization. Precision actions and
   objective terms are derived through Cholesky factor solves, improving unit
   rescaling behavior while keeping the supported state dimension at eight.

Every accepted result includes KKT diagnostics. Primal equality and bound
checks use original state units. Stationarity, dual-sign, and complementarity
checks and bound multipliers use normalized control coordinates; covariance
scales are reported. Fixed-width bounds are reported as `side: fixed`, with an
unrestricted multiplier.
Dependent consistent equalities retain an original independent row basis;
inconsistent dependencies are classified as infeasible. An outward-rounded
equality range check classifies box-infeasible constraints.
Cases that lack a certified face without such a feasibility certificate report
numerical failure. Nonfinite intermediate process increments and adjusted
equality targets also report numerical failure.

## Validation

- `python3 -m unittest tests/test_pr73_joint_analysis.py -v`: 16 tests pass,
  including the scalar `B=R=H=1`, `y=-0.7`, `[0.3, 1.3]` lower-bound case and
  its KKT diagnostics, an equality coincident with an active bound, and the
  decimal box-edge sum case.
- `python3 -m py_compile tools/pr73_joint_analysis.py`: passes.
- `python3 -m unittest tests.test_pr74_independent_oracle -v`: 4 independent
  oracle tests pass, including 396 scalar target/bound combinations and
  six-variable covariance-coordinate transformations.
- The pinned Intel endpoint writer O0/O2 integration is being run by the parent
  agent and is not claimed by this receipt.

This is a manufactured algorithm fixture. It does not establish scientific
validity or operational pipeline lineage. The maintained Cloud-BAL Graphify
snapshot was not updated in this assigned solver-only work; graph freshness is
not evidence of numerical or physical validation.
