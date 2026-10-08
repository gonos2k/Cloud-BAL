# PR71 checked substep-count contract

## Scope

The frozen selected source computes `numdt` and `numdt_i` as `max(nint(max(rate)*dtcld + .5), 1)`. In the ice path, `numdt_i` becomes `mstep_i`, which controls the ice sedimentation loop. The same unchecked conversion also exists for the warm-rain count, so this transform guards both count-producing expressions.

This change enforces only the representability conditions needed before a default-integer `NINT` and loop count. It does not set a maximum substep count, alter the rate, apply a physical CFL rule, or claim a physically valid timestep policy. Invalid values produce a diagnostic with `i`, `k`, rate, and `dtcld`, then `ERROR STOP`; this is a fatal rejection, not a rollback.

## Source basis

The transform accepts only the exact frozen base `composed_pr71_base.F` with SHA-256 `5de1884ab59e3de30a3e4ef1d8317405f1ba0591cf7ed9aa6fbca574d5233f41`. Its additive patch is recorded in `docs/evidence/pr71_step_count_contract_20261008_v2.patch`; the transformed source hash is `6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716`.

In the selected source, `slope_kdm6` forms mass and number terminal velocities, and `kdm6_velocity_rates` divides each by `delz` to produce the rates consumed by these expressions. The source therefore supports the rate construction as terminal-velocity divided by layer thickness (units of inverse time, given the model's length units). This source inspection does not establish the host dry-carrier identity, nor does it identify whether an observed extreme ice rate came from its numerator, denominator, or input state. That cause remains unresolved without the exact offending-point terminal velocities and `delz` from the native run.

Captured logs from the v2 partial native observation reported an ice mass-rate maximum of `3.585e8 s^-1`, an ice number-rate maximum of `7.736e9 s^-1`, and `dtcld=20 s`; these values exceed the default signed 32-bit count domain after multiplication. The run ended before a complete native receipt was produced, so these are partial-run observations, not a complete-run validation result. They demonstrate the conversion hazard, but do not establish a physical upper velocity or a replacement timestep policy.

## Guard behavior

`checked_substep_count` initializes `count=0` and `valid=.false.`. It rejects non-finite rate or timestep, non-positive timestep, a multiplication that would overflow binary64, and any computed `NINT` argument outside the default-integer range after rounding. Both thresholds are evaluated in binary64: the argument must be strictly below `REAL(HUGE(count),8) + 0.5d0` and strictly above `REAL(-HUGE(count)-1,8) - 0.5d0`. This handles the signed 32-bit range without converting its endpoints through default real. Ordinary finite negative rates remain accepted and retain the legacy minimum-one result. For accepted values, the helper evaluates the original `NINT(rate*dtcld + .5)` expression and retains the original minimum-one rule.

## Validation

`tests/run_pr71_step_count_contract.sh` generates the candidate from the frozen base, audits both guarded sites, extracts the exact helper into a small Fortran harness, and compiles/runs it at O0 and O2 with the pinned Intel profile from `tests/intel_toolchain.sh`. Both runs passed; the harness first asserts `BIT_SIZE(count)=32` and `HUGE(count)=2147483647`, the pinned profile assumption used by its boundary cases. The harness covers values below and at the highest representable count, values above and at the lower `NINT` threshold, values at and above the upper threshold, zero and ordinary positive/negative rates, NaN/infinite rates, invalid timesteps, and binary64 multiplication overflow. Full-module and native validation must use the emitted candidate source; the helper harness alone does not validate the full KDM6 integration.

The machine-readable receipt in `docs/evidence/pr71_step_count_contract_20261008_v3.json` records source, patch, tool, harness, compiler-profile, and O0/O2 log hashes.
