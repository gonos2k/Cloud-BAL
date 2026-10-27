# PR110 — static-grid input and portable execution boundaries

Baseline: PR109 merge `6b4ee5d71c9a88acd861b41d607d31087c165267`.

The dynamic LAPSPREP FLOAT contract, native W output validation, and Git failure
propagation fixed in PR109 remain unchanged. This change closes the separate
static-grid reader boundary and the two remaining portable existence dependencies.

## Static-grid input

`module_laps_static.f90` reads the static grid before the dynamic input preflight.
The legacy NetCDF generic readers do not convert DOUBLE payloads to the default
REAL destination. The reader now uses typed, status-returning `nf90` calls and requires FLOAT
metadata before reading. It retains the producer layout and the stored-meters
to-kilometers conversion. Every lookup/read/close status is checked; missing
variables cannot terminate through the legacy library's success-status path. The regression harness uses the actual module, not the dynamic LAPSPREP
suite's constant-value static stub.

## Portable inputs and temporary paths

- PR71's patch-hash negative supplies its own temporary source file; it still
  requires the intended patch-hash rejection and no generated output.
- PR83's portable provenance test checks exact keys, path structure, and exclusion
  of optional initialization inputs. A native sibling preserves the actual host
  file-existence check; production provenance validation is unchanged.
- The documented virtual environment may remain in checkout scratch, while
  `TMPDIR` is a separate executable directory outside any checkout. The replay
  guard remains unchanged.

PR109 Landlock denied external file reads/execution but allowed metadata lookup.
Its PASS did not establish that files were absent. PR110 qualification must test
with the research paths absent, including `stat`/`is_file`, rather than describing
read denial as file absence.

## Validation

Pinned Intel O0/O2 tests pass for the actual reader with the synthetic fixture,
the hash-pinned archived static grid, and the same 17 rejection cases per build.
The cases cover DOUBLE scalar/arrays, rank/order/length, grid-type storage, missing
file/variable, and zero/negative/NaN Dx/Dy. The original module license and public
state interface are retained. The new harness is registered in the native unit
entry point. [Native evidence](evidence/pr110_static_portability_20261027/static_reader.json).

The archived file stores Dx/Dy=5000 with legacy `kilometers` attributes; this PR
preserves the existing /1000 behavior rather than redefining producer units.
Portable validation uses two distinct scopes:

- An explicit PRoot guest root omits the reported research paths. The old PR71/
  PR83 checks fail (2 failed / 2 passed); the revised checks pass (4 passed).
  PRoot cannot execute the suite's sealed CLOEXEC memfd tests, so this guest-root
  run is not a complete portable PASS.
- The complete maintained command runs natively under a Linux seccomp notification
  gate returning ENOENT for the configured research/toolchain prefixes, including
  metadata lookups. It passes 208 Python modules and two shell suites, with
  1,340 pytest cases passed and one optional reference case skipped. No module
  is entirely skipped. Raw stat/lstat probes also confirm the absence behavior.

The latter is nonadversarial syscall-absence qualification, not a new physical
host, mount-isolated environment, or security sandbox. Prefixes and intercepted
syscalls, commands, failed setup attempts and evidence are recorded in the
[portable receipt](evidence/pr110_static_portability_20261027/portable_receipt.md).
The tests and production guard are not weakened to accommodate either setup.

Independent team reviews cover static input handling and the portable separation.
The native harness is rerun after dependency-hash checks are moved before invoking
nf-config. All 13 committed changed paths match the tested archive.

Graphify updates are separate for KLAPS50 (41,232 nodes / 85,662 edges) and
Cloud-BAL (15,404 / 27,204), each +15 nodes / +26 edges. Independent readback
confirms the 140 prior snapshots plus four additions, derived wiki scope, source
and pin preservation. Eight selected code/test paths were extracted; five other
paths were hash-bound. Cross-file Fortran CALL extraction is partial.
[Graph evidence](evidence/pr110_static_portability_20261027/kg/manifest.json).

Focused fixture tests are not full model, scientific, or hosted-CI results.

## Research scope

No C2 physics, wind input, solver tolerance, source-cache policy, or existing model
run is changed. H/A/N one-hour integration remains INCOMPLETE at 760 seconds,
and 14 UTC observation skill remains NOT_EVALUATED. T39 diagnosis and whole-host
water/energy acceptance are separate open work.
