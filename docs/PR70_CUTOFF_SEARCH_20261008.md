# PR70 KDM6 rain cutoff search (2026-10-08)

## Scope and source identity

This isolated Cloud-BAL research patch starts from the captured PR68 KDM6 source with SHA-256 `97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa`. The complete patch is [the PR70 process patch](evidence/pr70_coupled_process_cutoff_search_20261008.patch); it includes the PR69 coupled-process changes followed by this cutoff search and status routing. Its patched source hash is recorded in the [Intel validation receipt](evidence/pr70_coupled_process_cutoff_validation_20261008.json).

The original counterexample is retained verbatim in `tests/test_pr70_cutoff_search.f90`: rain mass starts at `2e-9`, process tendency is `-1.5e-9`, and `qcrmin=1e-9`. At alpha 1, stored rain is `0.5e-9` and fails the source cutoff. At alpha 0.5, stored rain is `1.25e-9` and is admissible. The new search returns a conservative valid float32 alpha below the continuous strict boundary: `0.66666657`, leaving `QR=1.0000001e-9`.

## Search behavior

The process state is affine in the common fraction. The helper finds breakpoints in `[0,1]` where any mass crosses zero or its active cutoff and where a number moment crosses zero. It classifies each open interval at its midpoint, intersects its nonnegative, PSD, and graupel-volume linear bounds, then checks interval endpoints and breakpoint points in the same default-real arithmetic used by the source. A bounded `nearest()` walk handles single-precision rounding at strict boundaries. It chooses a valid float32 alpha within the computed continuous admissible intervals. This is a conservative search: it does not prove the largest alpha accepted by the rounded endpoint predicate. A neighboring alpha outside a continuous boundary can round to the same valid stored state.

PR71 corrects the former maximum-representable-alpha wording following the independent PR70 review. The algorithm and physical tolerances are unchanged. Frozen PR70 receipts describe the source and wording at their original commit; they are retained as historical evidence.

The activity rules keep zero phases distinct from active phases: rain is either `QR=0` with `NR=0`, or `QR>qcrmin` with positive NR inside its PSD range. Cloud and ice are either exactly zero in both mass and number or above `qmin` with positive number and in-range PSD. Snow and graupel mass are either zero or above `qcrmin`. Graupel volume remains within the existing bulk-density bounds. The source state also requires Kelvin temperature to be strictly positive along the accepted process interval. The search partitions the `T=0` crossing, intersects the affine temperature constraint, and rechecks the stored temperature after the update. Exact `T=0` and negative values fail; no temperature floor or tolerance is applied. No physical source term was added.

A pending full-rain-evaporation cleanup has a narrow pre-transfer exception: at exact `QR=0`, it may carry positive NR to the existing source cleanup, which moves that number to `NCCN` before the stored-state check. Positive subcutoff QR is still rejected. The reusable stored-state predicate is called after cleanup without that exception and requires the stored exact-zero rain state to have `NR=0`.

## Status meaning

- `FEASIBLE` (`0`): a representable positive alpha passed the exact process-state check.
- `NO_FEASIBLE_STEP` (`1`): the interval search found no representable positive alpha that satisfies the stated source bounds. This describes this parameterized process step; it does not establish physical impossibility.
- `SEARCH_FAILURE` (`2`): inputs or intermediate arithmetic were invalid, or a bounded rounding search could not resolve a candidate. The caller reports unsupported mass-to-volume rates separately as `UNSUPPORTED_VOLUME_RATE`.
- `INVALID_STORED_STATE`: the post-update exact stored-state predicate failed. It is separate from process-step feasibility.

The stored-state check uses `kdm6_rain_process_state_valid` directly, including its `T>0` Kelvin predicate. It does not call the fraction search with zero increments, so a valid stored state is not misreported as a failed process step.

## Temperature finding

The prior PR69 validation checked only that candidate and stored temperatures were finite. A pinned-ifx minimal reproduction with zero Q/N/BG and zero process direction returned `FEASIBLE`, alpha 1, for `Tfixed=-1 K`. Since this is an absolute Kelvin state, `T<=0` cannot be accepted as a valid stored microphysics state. This is a newly identified scientific state constraint beyond the earlier finite-only check. PR70 adds the strict positivity test at both candidate and stored endpoints; it does not clamp or repair temperature. The before-fix helper, source, compiler invocation, logs, and their hash-bound receipt are preserved in [the finite-only reproduction evidence](evidence/pr70_temperature_finite_only_repro_20261008.json); the final validation receipt binds that receipt by SHA-256.

## Validation

`tests/run_pr70_coupled_process.sh` applies the hash-pinned patch in a fresh `/var/tmp` directory and uses the pinned Intel `ifx` profile from `tests/intel_toolchain.sh`. O0 and O2 both passed the direct cutoff/state tests and a source-extracted cold update and stored-endpoint harness. The receipt binds the captured source, patch, patched source, compiler, flags, generated source, executables, argv, and logs.

Covered cases include the preserved strict-cutoff counterexample and float32 endpoint, activity creation after exact zero, a disconnected active interval plus exact-zero endpoint, `qcrmin` equality, zero-mass rain with orphan number, pending cleanup before and after transfer, distinct `NO_FEASIBLE_STEP` / `SEARCH_FAILURE` outcomes, negative and exact-zero Kelvin rejection, a temperature crossing into positive values, and a source-extracted stored-endpoint failure injection at `T=-1 K` in both optimization builds.

## Graph navigation limit

The maintained Cloud-BAL graph contained 7,685 nodes at inspection. Its query exposed nearby KDM6 process-budget and rain-trace tests, but it has no node for the captured Fortran helper `kdm6_rain_process_fraction`; the isolated inherited graph also predates this patch. Source code and the hash-bound Intel harness are authoritative for this change. Graph extraction limits apply, and graph freshness would not establish runtime or scientific validity.
