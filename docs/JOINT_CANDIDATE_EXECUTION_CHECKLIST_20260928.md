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
  geometry, boundary semantics, source/quality provenance, species order, mass
  metric IDs, QV/RH precedence, and source hashes to the WPS payload and sidecar.
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
