# Joint candidate execution checklist

This checklist tracks one pressure-level candidate from the original analysis
through WPS, real, and native consumption. The same state, support, physical
convention, and evidence identity must be used at every gate. PR49 diagnostics
remain scoped evidence; they are not an approved joint candidate.

Status: **IN_PROGRESS / NOT_AUTHORIZED**. A conditional run may diagnose an
unsupported interval or an infeasible constraint. It does not grant BALCON ON,
native initialization, forecast, or operational authority.

## 1. Fix the candidate contract

- [ ] Identify one immutable background and one candidate by source, cycle,
  configuration, toolchain, and input hashes. Preserve the original inputs.
- [ ] Declare independent controls and reconstruct dependent pressure,
  temperature, geopotential, species, and face motion from the same candidate.
  Do not adjust these fields independently after reconstruction.
- [ ] Record dry-air, vapor, and hydrometeor mass denominators; distinguish
  pressure-coordinate cell mass from dry-air mass and from native dry mass.
- [ ] Record the enthalpy reference, analysis increments, physical-time flux
  interval, phase transfers, and boundary conditions. Never use solver iteration
  as a physical transport interval.
- [ ] Separate atmospheric domain, observation support, and change authority.
  Missing observations do not remove state cells or create authority to fill them.
- [ ] Define a mandatory evaluation domain from the union of every changed
  field's support plus the stencil/shared-face neighborhood and any before/after
  pressure-boundary cells and fluxes. Store its mask and distinguish it from
  both atmospheric support and the narrower domain authorized for corrections.
  Require evaluation coverage to contain the control domain; do not derive
  evaluation coverage only from active balance rows or valid omega targets.
- [ ] Classify conservation, positivity, units, and change authority as hard
  constraints. Scope hydrostatic, geostrophic, saturation, and acceleration
  approximations to the regimes and error models that support them; do not
  require every event to have zero divergence or zero acceleration.

Gate: one versioned candidate contract can be checked without running the
balance solver. Unsupported or inconsistent inputs fail before output creation.

## 2. Reuse one geometry and budget calculation

- [ ] Use the current pressure-interface/partial-face geometry for every
  candidate, residual, correction, and readback. Keep the A-grid-to-face map
  and its matching metric adjoint in the balance operator.
- [ ] Compute dry air and each water species on the declared mass basis. Check
  phase-transfer water sum and dry-air invariance separately from analysis and
  boundary increments.
- [ ] Reconstruct mixture enthalpy with a stated reference. Report omitted
  pressure work, kinetic/gravitational energy, or boundary energy terms; do not
  label mixture-enthalpy closure as native total-energy conservation.
- [ ] Remap extensive mass and enthalpy before restoring intensive q, r, and T.
  Check integrals over matching domains, not pointwise round-trip identity.
- [ ] Evaluate all constraints again on the final stored candidate, including
  neighboring cells and shared faces, after every accepted joint iteration.

Gate: existing counterexamples pass against the same calculations used by the
candidate path. A change that worsens a required invariant is rejected and
rolls back the candidate.

## First implementation batch: shared endpoint evidence

- [x] Recompute a whole-candidate species/dry-mass/mixture-enthalpy endpoint
  ledger after the existing column, geometry, and balance stages. Keep the
  stage ledgers distinct and label this endpoint ledger as accounting, not
  physical-time flux or native energy closure.
- [x] Reject the final candidate and restore the original state if endpoint
  validation or accounting fails. OFF and all rejected trials expose no
  accepted endpoint ledger.
- [x] Verify one combined thermo/radar candidate with an independent budget
  oracle and exercise failure rollback using the pinned Intel profile.
- [ ] Bind an immutable source/input/config identity to the accepted candidate
  and its diagnostic/WPS handoff. An opaque run ID alone is only a join key;
  the legacy WPS records need a sidecar or value-level readback to prove content.

Gate: one actual candidate generation has a single verifiable identity and a
whole-state receipt across the pressure path. Passing only the endpoint ledger
or only an in-memory mapping does not close this batch.

The checked items above are scoped to the source tests: `test_pipeline` checks
the combined thermo/radar endpoint against an independent mass/enthalpy oracle,
and `test_pressure_transition_prior` checks the union-domain geometry, dry-air,
and vapor changes at O0/O2. The writer recomputes and verifies the endpoint
budget at O0/O2 and serializes the signed endpoint into diagnostic attributes.
The independent file validator checks the declared receipt's completeness and
internal mass/enthalpy algebra; the writer checks the receipt against its
in-memory final state. The standalone file does not contain enough background
thermodynamic fields in every schema to independently recompute every endpoint
term. This receipt does not bind source/input/config hashes or prove the WPS
payload is the same candidate. No actual-cycle joint candidate was run. The
batch gate remains open.

The v2 endpoint receipt also carries the absolute pre-cancellation sums for
each species split and the mixture-enthalpy split. The independent validator
uses the accounted cell count and binary64 unit roundoff to bound arithmetic
differences; this is separate from any physical mass or energy tolerance.
Legacy v1 receipts retain their historical, less informative check. Because
some schemas lack full background state, a standalone v2 validator checks the
declared scale's form and algebra but cannot independently recompute every
scale; the writer recomputes it from the final in-memory state. A generation
transaction must bind the stored receipt to its source and payload before it
can be treated as provenance evidence.

## Second implementation batch: one final-state evaluator

- [x] Recompute the endpoint ledger, pressure-grid continuity residual, and
  geostrophic diagnostic from the same final candidate. The SHADOW writer
  independently repeats this evaluation before accepting the in-memory result.
- [ ] Add independently authorized analysis sources and physical-time boundary
  fluxes to evaluate dry-air, water-species, and energy conservation residuals.
  A computed endpoint change must never be copied into its own source term.
- [ ] Evaluate EOS, reference surface, hydrostatic applicability, observation
  operators/errors, change authority, positivity, and local shared-face
  residuals under one versioned candidate contract.
- [ ] Persist a complete final-state assessment with explicit unresolved
  conditions and bind it to the diagnostic and WPS payload readback.
- [x] Persist the current limited endpoint/active-support evaluation flags,
  statuses, count, and metrics in SHADOW and reject malformed receipts on
  independent file validation. This receipt does not satisfy the complete
  assessment item above.
- [ ] Distinguish feasibility, objective stationarity, and step size in a
  common iteration; the current five-field stored-value fixed point is not
  a joint constrained solve.

The first checked item is diagnostic scope only. Continuity and geostrophic
values are measured only on the final state's active balance support with the
existing pressure-grid operator. The receipt records that support count and
each diagnostic's status; zero support is unassessed, not a zero residual.
An operator-build failure can also leave the count at zero; its status
distinguishes that failure from a successfully built empty support.
The evaluator's returned status covers canonical endpoint accounting, not
completion of every diagnostic. These values are not a universal zero-motion
target. The SHADOW file now stores the limited evaluation flags, statuses,
active-balance support count, and metrics, and the independent validator checks
the receipt structure and values. This receipt records what was assessed; it
does not apply physical pass/fail thresholds, cover the mandatory evaluation
domain above, or bind the candidate to source/input/config/build/runtime
identity. The transaction's WPS-pair receipt binds its three stored products
and verifier bundle, not the producer lineage or a complete physical
assessment. External source, boundary, and independent observation fit remain
unassessed.
The evaluator does not issue physical or native approval. The complete
assessment and physical-acceptance gate remains open.

## Third implementation batch: stored WPS pair

- [x] Reopen a completed pressure-level WPS candidate, its retained WPS
  baseline, and the SHADOW diagnostic in one detached snapshot. Compare the
  declared inventory, valid date, units, baseline/candidate WPS header
  metadata, mapped candidate values, retained slabs, candidate support masks,
  candidate surface TT/PSFC where declared, and the declared geopotential
  conversion.
- [x] Bind this scoped numerical check to exact snapshot product hashes and
  the validator/parser source bundle; reject altered WPS or SHADOW bytes and
  a stale validation receipt before an isolated generation is published.
- [x] For the declared Lambert/`SWCORNER` analysis pair, reconstruct the full
  WPS grid from its projection header and compare its coordinates, dimensions,
  spacing, and wind frame with SHADOW. Reject a shared WPS header mutation.
  This does not independently establish the producer's source-grid identity.
- [ ] Bind baseline and candidate WPS metadata to one independent grid
  identity, including its input/configuration/build provenance. Cross-file
  coordinate agreement alone does not establish that source identity.
- [x] Preserve `XFCST` in parsed WPS metadata and require zero forecast hours
  for this analysis-time pair. A future forecast-lead workflow needs its own
  declared lead contract relative to `HDATE`.
- [x] Check the current legacy writer's stored inventory as the canonical
  pressure axis at or below 1001 hPa, independently of above-ground support.
  Keep baseline values and zero hydrometeors on stored below-ground slabs.
- [ ] Define the stored pressure inventory independently from atmospheric and
  change masks for every supported writer/grid, with an explicit versioned
  pressure-list declaration and separate `M_atmosphere(i,j,k)` and
  `M_change(i,j,k)` readback. The current 1001 hPa rule is specific to the
  retained legacy writer; it does not authorize another pressure inventory.
- [ ] Run the current LAPSPREP producer into a detached generation with a
  pinned source/input/configuration/build manifest and verify the pair before
  changing any consumer-visible pointer. The current test republishes a
  historical actual pair in an isolated evidence root.
- [ ] Reproduce this readback with the current writer's surface-boundary
  schema; the historical sidecar lacks candidate surface TT/PSFC and is
  checked against its retained baseline for those fields.
- [ ] Confirm metgrid, real, and native consumed state against that same
  generation and its declared QV, mass, frame, boundary, and omega contracts.

Gate: the current source-produced pair and its input/build identity survive
independent stored-value readback and one atomic research publication. Pair
validation alone does not approve the joint solve or native initialization.

## 3. Run one actual joint candidate

- [ ] On one pinned actual cycle, form one candidate from existing analysis,
  cloud, radar, and surface inputs. Bind observation values, operators, error
  assumptions, correlations, support, and permitted increments before solving.
- [ ] Reuse the existing column and balance blocks inside a common iteration:
  recompute the complete state and all residuals after each trial; accept only
  a step that satisfies the declared bounds and conservation gates.
- [ ] Include independently supported lower-layer state, boundary fluxes,
  surface pressure/datum, and physical omega driver. If any is absent, retain
  an explicit unresolved result rather than fitting it to close a residual.
- [ ] Distinguish exact conservation incompatibility, insufficient information,
  current linearization failure, and numerical nonconvergence.
- [ ] Save one candidate receipt with final-state residuals and every unmet
  condition. Do not publish an unresolved candidate as an initialization.

Gate: the same actual candidate has complete, independently supported mass,
energy, geometry, observation, and boundary accounting. A conditional execution
is a diagnostic milestone only; it does not pass this gate.

## 4. Verify delivery without changing the scientific gate

- [ ] Bind candidate identity, denominator, species, masks, support, time,
  geometry (including the cross-checked grid identity), boundary semantics,
  source/quality provenance, species order, mass metric IDs, QV/RH precedence,
  forecast lead policy, and source hashes to the WPS payload and sidecar.
- [ ] Publish to a fresh generation with no clobber. Reopen and verify data and
  sidecar after close; on any failure, leave the current generation untouched.
- [ ] Verify WPS, metgrid, real, and native consumed fields against the same
  candidate, including native dry-mass and stagger/frame conversions. The
  present WPS bridge omits pressure-level omega; it cannot establish native
  `ww` without an approved driver, time/boundary contract, mapping, and readback.
- [ ] Keep OFF byte identity and failure/rollback tests as release gates.

Gate: the consumed native state matches the authorized candidate within
predeclared field and conservation tolerances. A payload-only or writer-only
test does not pass this gate.

## Physical-initialization execution gates (PR55)

The current evaluator already supports a no-omega diagnostic execution. It
reports endpoint accounting and continuity/geostrophic diagnostics on active
balance support; zero support or a failed operator leaves these diagnostics
unassessed. The continuity diagnostic includes supplied boundary velocities
and valid top/bottom omega, but does not validate their physical provenance or
close independently authorized source and boundary fluxes. It also does not
assess observation fit, KDM6 startup response, or native consumed
state, and it grants no initialization approval. Treat this as the implemented
limited baseline, not a completed physical evaluation.

- [ ] Capture the first KDM6 call's `itimestep`, TH/PII (or derived T), dry
  density `DEN`, vapor and each hydrometeor Q, all N fields, and QIB/BG
  immediately before and after the call. Bind the actual executable, source,
  input, and configuration identities. Check finiteness and the declared
  initialization policy; retain zero or missing moments as such when no
  authorized rule exists.
- [ ] Carry one current producer candidate identity through WPS, metgrid, real,
  and native initialization. Bind source/input/config/build/runtime hashes,
  generation IDs, and independent readbacks of the consumed values and time at
  each stage. Reject identity breaks; do not substitute a historical pair.
- [ ] Run BASE, HYDRO, and COUPLED from the same pinned case, boundary forcing,
  model/physics settings, and toolchain. Freeze the mode definitions, paired
  comparisons, startup metrics, and acceptance thresholds before examining
  results.
- [ ] Retain high-frequency startup output at the cadence needed for the
  resolved fast modes, plus 10-, 30-, and 60-minute checkpoints. Compare at
  least pressure tendency/divergence, vertical and horizontal wind response,
  temperature/moisture/species changes, and finite/positivity status. Report
  each predeclared metric against its frozen threshold; do not infer shock
  safety from hourly output or a 0–6 h aggregate.
- [ ] Record each gate as PASS, FAIL, UNSUPPORTED, or NOT_RUN with its reason.
  Missing inputs, unsupported fields/mappings, or absent native consumers are
  not zeros and cannot count as PASS. Preserve rejected and incomplete runs.

These items remain open until one reviewable execution receipt binds the
pre/post KDM6 fields, stage identities/readbacks, paired startup diagnostics,
frozen criteria, and unresolved dispositions. No item is closed by the
existing no-omega evaluator or historical WPS/native tests alone.
The retained native input has positive hydrometeor mass with zero paired
number/volume moments, and the inspected private `real.exe` initializer has
no identified QIB transfer path. Treat both as handoff questions requiring
source-bound readback; neither permits a fabricated moment initializer.
Read-only MP37 preflight on the retained input hash `f0ccee31...a052e1`
returns `NO_AUTHORITY` (exit 3): positive mass with zero paired moments in
962,388 cloud, 258,832 ice, 219,996 rain, and 817 graupel cells. The CLI's
immediate reason is `EXPECTED_DENOMINATOR_MAPPING_MISSING`; the pair counts
are diagnostic evidence, not an authorization to run KDM6.

## 5. Demonstrate generalization

- [ ] Run the same candidate code for clear, fog, stratiform, convective,
  mixed-phase, complex-terrain, and sparse-observation cases. Change only
  declared data, observation operators, parameterizations, and uncertainties.
- [ ] Hold physical definitions and acceptance thresholds fixed before case
  evaluation. Preserve both successful and rejected cases with receipts.
- [ ] Compare independent observations and the native startup/forecast response
  on the declared NE57 domain and separate events.

Gate: conservation, observational fit, native response, and forecast criteria
pass without case-specific repair rules or post-hoc threshold changes.

## Current evidence and open conditions

- `src/common/cloud_bal_state.f90` already distinguishes pressure mass and
  dry-air mass; `src/common/cloud_bal_column_physics.f90` has species and
  mixture-enthalpy diagnostics.
- `src/common/cloud_bal_balance_operator.f90` already shares face geometry,
  residual, correction, and rollback within its pressure-grid projection.
- `src/common/cloud_bal_pipeline.f90` currently runs column, geometry, and
  balance stages in order. Its feedback is limited to T, vapor, u, v, omega;
  it is not the joint candidate solve in gate 3.
- `docs/PR49_DRY_MASS_HARDENING_20260923.md` leaves the 10 m-to-first-regular
  layer unsupported. The conditional gap bound is not a humidity estimate.
- `docs/CP02_E03_COUPLED_TRANSPORT_READINESS_20260910.md` records missing
  payload identity/authority and downstream canonical readback contracts.

No checkbox above is closed by this checklist alone. For each completed item,
record the exact source SHA, input/config/tool/runtime hashes, receipt,
independent review, and validation scope. Compile in a fresh scratch working
directory with the pinned Intel profile in `tests/intel_toolchain.sh` (O0/O2
as applicable); GNU/gfortran and ifort are not substitute validation.
