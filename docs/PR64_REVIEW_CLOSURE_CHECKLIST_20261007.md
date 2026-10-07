# PR63 review follow-up: call identity and joint transport

Base: `c2ff3f5b030d40d8c8512e38cb63aa8d06d83a50` (PR63 merge).
Full physical initialization remains **FAIL/OPEN**. Prior scoped results and
failed attempts keep their original source, executable, and artifact identities.

## Current implementation and investigation

- [x] Correct the selected QC/NC interpretation using both successful matched
  PR63 stage captures; retain original artifacts and identify incomplete-run
  finer cuts separately. A named-column reader now crosschecks text headers
  and predicate counts with the same binary masks.

- [x] Define the source-bound geometry/KDM6 call-duration relationship; reject
  unsupported or mismatched durations without assuming all host clocks equal.
- [x] Test malformed real-format captures and replay the retained same-call
  geometry against the actual public KDM6 parameters.
- [x] Capture QC/NC tendencies and RK dry carriers in a new solve observer
  retaining the archived advection member; compare ten output artifacts with
  the successful baseline. NC's RK1/RK2 negative contribution is advective;
  QC's positive tendency already exists before `rk_scalar_tend`.
- [x] Identify the QC source channel with a separate guarded observer: target
  QC tendency equals the active PBL `rqcblten` contribution; the other logged
  QC/NC physics channels are zero. The internal PBL process is still open.
- [x] Inspect the current Shinhong source: QC vertical mixing has no NC
  argument in that interface. Keep this source-supported interpretation
  separate from archived PBL object identity and runtime channel attribution.
- [ ] Complete the reconstruction with individual NC donor-face fluxes and
  the internal PBL transport/process that supplies QC without an admissible
  coupled number state at the final physics boundary.
- [ ] Distinguish incomplete sequential updates, invalid donors/boundaries,
  different transport/process operators, and floating-point/cutoff effects.
- [x] Execute an actual-data conditional phase trial with predeclared zero
  external increments, internal exchange, representation allowances, and
  protected variables through the existing pipeline and readback. This is
  separate from the joint physical approval gate below.
- [x] Extend that trial to geopotential using the existing lowest supported
  background reference and a common-layer residual comparison; independently
  read back both the component contract and pressure/geopotential bundle.
  Original full-run receipts remain FAIL_OPEN; corrected normal replay and
  storage-tail checks pass separately on the unchanged O0/O2 artifacts.
- [x] Align the common SHADOW validator with the stored component dimension
  and the contracted changed-cell dry carrier. Preserve the legacy rule when
  no component contract is declared; the old radius mismatch remains rejected.
- [x] Finish independent agent-team review, fix findings, and validate affected
  paths with Python and the pinned Intel profile in fresh scratch directories.
- [x] Freeze the source and update separately dated KLAPS50/Cloud-BAL
  graph overlays and derived wiki audit for the reviewed PR.

## Physical approval gates

- [ ] Q/N/volume state is admissible at the completed transport and actual
  physics evaluation boundaries. Do not floor or erase a remaining bad cell.
- [ ] Shared air transport preserves the relevant coupled moment domain;
  differential sedimentation retains its own physical moment velocities.
- [ ] Same-call mapped water/energy budgets include independent process and
  boundary terms; the captured hybrid carrier alone is not budget closure.
- [ ] Feasible joint trials connect thermodynamics, geopotential, mass/wind,
  boundary conditions, moments, and observation fit. Feasibility, optimality,
  and step change have separate meanings and fixed scales.
- [ ] A fully traced native candidate preserves physical signals and improves
  fixed-setting BASE/HYDRO/COUPLED first-call and 10/30/60-minute responses.
- [ ] Independent observations and later forecasts confirm useful changes;
  full host build and parallel execution retain their own gates.

## Interpretation

PR63's 4x4x3 nonzero contract, same-call hybrid carrier, and paired terminal
BG cleanup remain PASS_SCOPED. The QC/NC return gap (one cell), negative QC
(23,539 cells in the RK3 host tile; 23,494 in the KDM active-entry region),
and source of the 11 pre-cutoff BG ghosts remain
open until new evidence establishes the respective causes and corrections.
Do not reinterpret the 44.978 m3 BG descriptor removal as melted or removed
water, or convert representation differences into physical sources.

Mutable outputs and build artifacts must have unique paths and no aliases to
prior comparison artifacts. Declared-input/output hash guards are not an OS
sandbox or proof of a complete compiler/runtime chain. Operational/native
maintenance sources are preserved while research experiments run in copies.


## Current evidence links

- [Call-duration contract](PR64_CALL_DURATION_CONTRACT_20261007.md): selected
  host and maintained driver source inspected; compiled-driver lineage remains
  a separate limitation. Whole-audit manufactured binaries cover mismatch
  rejection and differing grid-clock metadata; retained 20-second capture passes.
- [Independent math review](PR64_TEAM_MATH_REVIEW_20261007.md).
- [Native transport investigation](PR64_NATIVE_TRANSPORT_CAUSE_20261007.md):
  observer identities are separate from the archived baseline. The aggregate
  PBL QC channel is identified; its internal process, individual NC donor
  faces, and complete host build remain open.
- [PBL source follow-up](PR64_PBL_SOURCE_FOLLOWUP_20261007.md): current-source
  hashes and a concrete coupled-transport investigation plan, with archived
  physics-object binding and internal native fluxes still open.
- [Actual-data conditional candidate](PR64_REAL_CANDIDATE_20261007.md):
  observational inputs are withheld for this scoped experiment; the existing
  physical background is retained. This is not a full joint optimizer.
- [Root targeted review](evidence/PR64_ROOT_REVIEW_20261007.json): 50 focused
  Python tests, a separate legacy transition-validator regression, successful
  PR63 stage-text verification, six exact target RK replays and the new QC
  source-channel replay. These are distinct from the native model executions.

- [Maintained KG update](PR64_KG_UPDATE_20261007.md): frozen source overlay,
  separately dated corpora, derived wiki audit and preserved content.
