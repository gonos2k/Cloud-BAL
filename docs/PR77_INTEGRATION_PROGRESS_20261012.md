# Common estimator assessment and native entry evidence — 2026-10-12

Base: merged PR76, `9701ef23f04576d875508a0882d0e0af67282587`.
The PR76 KKT solver is unchanged. Its small manufactured-problem certificate
does not establish acceptance of a meteorological initialization.

## Common pipeline inlet

The nonzero H/B/R fixture now supplies its endpoint and independent analysis
increment contract to `run_cloud_bal_pipeline()`. The pipeline validates the
canonical state, preserves background observation/support/boundary/geometry
identity, evaluates the endpoint with the existing water/enthalpy accounting,
and returns the original operational state. Missing or inconsistent contracts,
altered ancillary metadata, manufactured source bits, unsupported combined
requests, and invalid state values reject atomically.

This is an **assessment inlet for an externally estimated endpoint**. It does
not reconstruct the endpoint using the column/balance producers, authenticate
real H/B/R authorities, or supply an operational assimilation experiment. Its
producer and overall receipts deliberately retain `FAILED/REASON_AUTHORITY`.
Only this inlet and the writer's existing estimator-serialization branch can
use analysis provenance without claiming column/balance production. A contract
with an allocated analysis increment alone does not enable that permission.

The fixed 4×4×3 fixture changes one cell. Pinned Intel O0/O2 endpoint evaluation,
NetCDF write/readback and corruption controls pass. The canonical standalone
validator still reports `UNBOUND`, `REJECTED`, `numerical_decision=INVALID`,
`physical_continuity_assessed=false`, `dry_air_mass_continuity_assessed=false`,
and `science_assessed=false`. Its failures are preserved in
`docs/evidence/pr77_estimator_canonical_20261012.json`.
Normal producer acceptance and the standalone validator's thresholds are
unchanged.

## Copied native build correction

The earlier native harness copies KDM6 to lowercase `.f90` but did not request
preprocessing. Intel reports ignored `#ifndef/#else/#endif` directives; both
branches then execute, so a successful `specific_number_to_volume()` result is
overwritten by the `TEST_DIRECT_VOLUME` branch's direct assignment. This is a
research build defect independent of the FTZ/DAZ conversion failure.

A pinned Intel O0/O2 minimal compiler probe confirms the branch overwrite
without `-fpp` and correct selection with `-fpp`. The first unpreprocessed
observer run also records internal NI bits `04A25EC5`, equal to the specific
public NI. The corrected run records `04B2D031`, the converted volumetric NI.
Both native observer arms now explicitly compile `.f90` with `-fpp`; the
shared PR76 runner also defaults to explicit preprocessing for future runs.
The old PR76 execution receipts and model sources/inputs remain unchanged.

Observer critical sections compile/link with `-qopenmp` in both arms. The
retained physical KDM6 source has no OpenMP directives; its physical loop is
unchanged. Compile/link additions and the inherited archive identity are
recorded separately rather than described as identical compiler commands.

## Actual native outcomes

Both runs stage the same 100 model inputs and verify their bytes after execution.
They reuse the pinned research archive; only copied KDM6 and, in the startup arm,
copied main are newly compiled. This is not a full upstream/host rebuild.

| Arm | Outcome | Direct observation |
| --- | --- | --- |
| KDM6-entry gradual underflow | exit 128, REJECTED | Original species validator rejects an ice number-only state at `KDM62D_ENTRY` |
| Startup plus KDM6-entry gradual underflow | signal 6, REJECTED | Intel `forrtl: error (65): floating invalid` during host initialization, before KDM6 |

The actual first entry violation is `(i, call_lat_index, k)=(104,2,1)`, with
ice mass `0` (`00000000`) and internal number
`4.2038792500161422e-36 m^-3` (`04B2D031`), MXCSR `00001FBF`.
The public number is `3.8173049035872155e-36 # kg^-1 dryair` (`04A25EC5`).
The wrapper latitude index is recorded as such; global-j mapping is not claimed.
The observer precedes the unchanged validator and follows its species/check
ordering. It records full entry-slice class counts and covers each later slope
and local validator site without adding a floor or modifying model values.

The full same-call pretrace audit contains 299,933 moment-only pairs, 740
mass-only pairs, and 23,494 negative/invalid pairs (no nonfinite pairs).
These are state-class counts on this captured research input, not test counts,
meteorological error rates, or the number of completed physics calls. The
predicted pretrace first violation agrees with the actual entry observer.
Earlier hypothetical graupel cutoff coordinates are not substituted for this
ice failure.

At `(211,2,15)`, the corrected KDM6-entry arm still records the same positive
NI conversion `0093B134 * 3F449EE9 -> 00716F5A`; it also retains the PR74
pretrace and driver-capture hashes. Passing this conversion does not repair
the other invalid states in the entry slice.

The startup arm validates one main-thread row and all 68 distinct initial
OpenMP team rows, verifies main-thread membership, and checks that each helper
preserves every bit outside `0x8040`. However, rebuilding main with the pinned
O0/strict/`-fpe0`/`-no-ftz`/OpenMP profile changes startup initialization relative
to the inherited main. Its early invalid-operation trap cannot be attributed
solely to the explicit FTZ/DAZ intervention. All startup rows already have
FTZ/DAZ clear before the helper (`1920` on main and `1900` on workers); the
helper correctly acts as an idempotent no-op on those rows. Symbol lookup associates the
preserved stack with `module_sf_noahdrv::lsminit` via `bl_init`, `phy_init`, and
`start_domain_em`; it does not identify the exact invalid expression.
Later or external thread pools and their FP policies remain unassessed.

## Validation and limits

`docs/evidence/pr77_validation_20261012.json` binds the final source and checks;
`docs/PR77_TEAM_REVIEW_20261012.md` records independent review findings and fixes.
Final reported builds use `tests/intel_toolchain.sh` and fresh external scratch.
Nineteen nested unit runners now honor `CLOUD_BAL_TEST_SCRATCH_ROOT` (default
`/var/tmp`), including the mapping runner that previously failed in a clean
worktree because a source-tree scratch directory did not exist. Nested runners
that need KLAPS sources also honor the explicit `CLOUD_BAL_WORKSPACE_ROOT`.
Three runners received their path-only correction after the broad suite had
already executed them. Their separate final Intel checks in external scratch
supersede those earlier source-tree builds; no physics source changed during
that follow-up.
The full unit run subsequently stopped at a lightning-test workspace lookup.
That test now honors the explicit workspace; replay and lightning checks pass.
The remaining original unit-script commands were then executed with their
dependencies freshly compiled in external scratch. The receipt labels this
combined coverage `PASS_SEGMENTED` and retains the whole-script exit 1 and
the initial continuation-bootstrap failure. It does not claim one uninterrupted
exit-zero execution of the final whole unit script.

Initial failed build, earlier unpreprocessed observation, and earlier serial
observer attempts are retained separately. They are not counted as final
validation. The source tree and the selected copied native inputs are distinct
from the manufactured estimator endpoint; no same-candidate handoff is claimed.

Current batch: **PASS_SCOPED** for central endpoint assessment/serialization,
source-selection correction, observer identity and scoped regressions.
Native candidates: **REJECTED**. Overall physical initialization: **OPEN**.

The next required result remains a valid common spatial candidate with real
observation/background authority, completed native first call, same-carrier
dry-mass/water/energy and cell/shared-face mass–wind closure, WPS/metgrid/real
handoff, and fixed-setting BASE/HYDRO/COUPLED short-time response. These gates
are neither replaced by this inlet nor closed by graph freshness.

## Twelve-team audit follow-up

The separate audit inventory is `docs/PR77_AUDIT12_20261012.md`. Its team
reports separate reproduced defects, static risks, missing implementations,
and missing scientific evidence. One reproduced E01 freshness bypass is fixed:
output inventory now rejects symlink directories before testing for regular
files, so stale generated output cannot hide behind a skipped directory.
The twelve focused E01 regressions pass. This is a publication preflight fix,
not completion of an E01 launch chain or native initialization.
