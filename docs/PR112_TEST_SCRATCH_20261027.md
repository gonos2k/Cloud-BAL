# PR112 — relative scratch paths and off-corner regression

Baseline: PR111 merge `5c8f19e2db87a930767f6c6b8417c23d2a70ad56`.

The LAPSPREP native runner now resolves its scratch root with `pwd -P` after
creating it. Relative paths therefore retain their meaning when compilation and
linking change into the fresh build directory. Default and absolute scratch
paths continue to use the same path; builds remain outside the source tree in
the validation below.

Three existing malformed-array fixtures now place their single invalid value at
Fortran cell `(2,1)`, outside the southwest/northeast corner pair of the 2×2 grid:
latitude missing, latitude nonfinite and terrain missing. The southwest latitude
200 case stays unchanged. No new physical bounds or production algorithms are
introduced.

## Validation

The maintained runner is exercised with `CLOUD_BAL_TEST_SCRATCH_ROOT=../pr112-native`
from the checkout, using the pinned Intel profile and retained external scratch.
It completed with exit status 0. Both O0/O2 builds passed the existing caller
regression, all 12 static-value negatives per build (including the three
off-corner cases), and four positive WPS checks of 23 geometry records each.
The retained scratch path is absolute. NetCDF readback independently confirms
exactly one malformed value per off-corner fixture at `(record,z,y,x)=(0,0,0,1)`.

[Evidence](evidence/pr112_scratch_20261027/validation.json) pins the 28 build/test
sources: only the runner and fixture differ from PR111; 26 pins remain unchanged.
The standalone reader suite and full portable tier were not rerun for this
test-only change.

This is a test-runner change. PR111 static-grid validation remains in effect;
forecast/T39, whole-host budgets and observation skill retain their existing open
states. No model run or scientific approval is added.
