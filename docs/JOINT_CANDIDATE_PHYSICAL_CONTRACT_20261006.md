# Joint candidate physical contract: NE57, 2026-08-16 12 UTC

## Scope and immutable reference

The PR59 source-produced reference is `90179191edc33b5ae5606a37f4cd67eac507eed0`,
not the subsequent main merge `ea2c02bb808bc9cf77b97fc4a25a2da06dfd73a1`.
Its exact input, configuration, executable and product hashes are recorded in
`evidence/pr59_current_lapsprep.json`. The 122 copied inputs remain immutable.
The baseline is the same-run legacy LAPSPREP output; the research candidate is
`LIQUID_RADAR_RH1_PHI` on 235 x 283 x 22 pressure points with 5 km spacing.
This reference establishes a pressure candidate and WPS readback, not a
COUPLED solution or native initialization approval.

## Fixed quantities, controls and reconstruction

| Quantity | Current research definition | Joint-initialization disposition |
| --- | --- | --- |
| Time, horizontal geometry, pressure coordinate | Fixed to the copied input | Preserve and verify at every stage |
| Surface pressure and atmospheric domain | Fixed in this experiment | Moving volumes require a separate flux/remap contract |
| Radar-derived hydrometeor proposal | Existing reflectivity relation and declared phase policy | Its uncertainty and independently admitted analysis increment remain unresolved |
| Temperature and vapor/cloud liquid | Liquid RH=1 adjustment only on the immutable radar footprint | Research ablation; no universal saturation or mixed-phase equilibrium requirement |
| Geopotential | Existing loaded-mixture thickness increment, lowest supported center anchored | Preserve the declared background residual; no universal zero-residual target |
| U/V/omega | Same background; wind correction disabled by the retained configuration | No manufactured omega driver or hidden zero-divergence target |
| Number moments and graupel volume | Not delivered by this WPS bridge | QNCLOUD/QNICE/QNRAIN need a named PSD/producer; QIB needs a named volume/density prior |

For dry-air mixing ratios, the represented pressure-coordinate cell measure
and dry mass are different quantities. The current code reconstructs dry mass from
the pressure-cell measure and all represented water ratios. Changing vapor or
condensate at fixed pressure geometry can therefore change dry mass. The
canonical relation is

```text
m_d = P / (1 + Σ r_s)
m_s = m_d r_s
m_d + Σ m_s = P
```

Here `P` is the pressure-coordinate cell mass measure and the six `r_s`
include vapor and every represented condensate. So even when condensate loading
changes `m_d`, the sum of dry and all species masses remains `P`. For example,
at `P = 100 kg`, total water ratios of `0.1` and `0.2` give dry masses of
`90.909... kg` and `83.333... kg`, respectively; the species masses are
`9.091... kg` and `16.667... kg`. Both totals remain `100 kg`.

Mixture enthalpy uses the existing `moist_species_enthalpy` reference at
273.15 K and the dry-air basis. Kinetic energy, gravitational energy, pressure
work and native total energy are outside this enthalpy check.

## Local feasibility before accepting a block trial

For an explicitly supplied fixed-geometry contract, compare the final state
of each trial with the same background. Use the eight extensive quantities

\[
C=(m_d,m_v,m_c,m_i,m_r,m_s,m_g,H).
\]

The optional `physical_joint_candidate_contract` API requires the caller to
prescribe source and boundary increments, complete atmospheric coverage,
field change permissions, and physical tolerances \(t\) before solving.
Their prescribed increments are compared separately in scaled arithmetic; an
optional internal phase ledger is a third term and is never folded into an
external source. A phase ledger is caller supplied and stoichiometrically
constrained (zero dry mass, zero net water, zero represented enthalpy); it is
not a solved phase extent or a global optimizer.
The local comparison is

\[
|C_i^a-C_i^b-I_{\mathrm{source},i}-I_{\mathrm{boundary},i}-I_{\mathrm{phase},i}|
\le t_i+e_{\mathrm{arithmetic},i}.
\]

The arithmetic allowance uses the operand scale and binary64 rounding;
it is separate from the caller's physical tolerance. Every changed atmospheric
declared coverage must include every required atmospheric cell, including
cells whose values remain unchanged.
Opposite local residuals cannot cancel through a domain
sum. Missing species, geometry changes, missing declarations or unsupported
criteria must remain explicit; they do not become zero residuals.

Because pressure geometry is held fixed, the declared net increments in
components 1–7 must also satisfy the per-cell necessary condition

```text
Σ(c=1..7) [source_c + boundary_c] = 0
```

When no surface-pressure reconstruction is requested, the pipeline checks this
before any candidate trial. A pressure request defers the fixed-geometry
decision to the endpoint gate, even if the requested pressure happens to be
unchanged. Its allowance is the sum
of the seven declared physical tolerances plus a separate floating-point bound
scaled by pressure mass and declaration magnitudes. Component 8, enthalpy, is
not part of the mass sum. This early check only rejects an incompatible
declaration; it does not create or infer a physical source term.

This prescribed-increment check cannot authenticate the supplied increment.
It must not construct \(I\) from the endpoint it is checking. The endpoint
ledger keeps source, boundary and phase declarations separate:
\[
C^a-C^b=I_{\rm source}+I_{\rm boundary}+I_{\rm phase}.
\]
The optional phase ledger is caller supplied and checked independently for
zero dry-mass change, zero net water change and zero represented mixture
enthalpy. It is a prescribed local feasibility extent, not an inferred source
or a solved global phase-transfer field. External analysis and physical-time
boundary transport can change dry mass or water; solver iterations are not a
physical transport interval. The current producer does not supply a complete
admission policy for those terms.

A local feasibility pass is distinct from stored-value convergence,
observational fit, constrained stationarity, native acceptance and forecast
benefit. In particular, the existing five-field fixed point does not establish
an optimum. The default research path retains its diagnostic status when no
independent contract is supplied.

For an explicitly contracted fixed-pressure trial, the pipeline closes the
stored dry-air-mass representation on cells whose committed temperature or
water fields changed, using the fixed pressure-cell mass and stored float32
water values:

```text
md_stored = pressure_mass / (1 + sum(stored water mixing ratios))
```

The standalone phase-transfer kernel continues to use its pre-transfer dry
carrier when computing the physical extent and phase ledger. This final
pipeline step reconciles stored representation; it is not a dry-mass source,
phase transfer, or physical correction. Cells outside the changed
thermodynamic mask remain bitwise unchanged. The caller's predeclared component
tolerance bounds the resulting endpoint representation residual; it does not
authorize an additional physical source. Variable-pressure contracts remain
outside this fixed-geometry closure path.

## Native consumption and first call

Follow the current candidate, not the retained 13 UTC native probe, through
WPS, metgrid, real, physics initialization and the first KDM6 call. Preserve
stage time, input/executable/configuration hashes, field units, dry-air mass
basis, QV/RH precedence and wind coordinates. Pressure omega is not present in
the current WPS payload; native W must have an explicit construction and
readback rather than an externally substituted trajectory.

At the first call, capture T (or TH/PII), dry density, vapor, every hydrometeor,
QNCCN/QNCLOUD/QNICE/QNRAIN and QIB before and after. Keep initialization resets,
floors and clipping separate from physical process increments. Configured CCN,
the separately tested 400 kg m-3 graupel prior and the private 900 kg m-3
zero-volume numerical guard are distinct policies. None initializes the three
missing hydrometeor number fields automatically.

## Remaining scientific gates

- Independently admitted analysis increments, boundary fluxes, observation
  operators/errors and moment priors are not supplied by PR59's research mode.
- A common iteration must meet its declared local constraints and observation
  criterion, with step size and constrained stationarity reported separately.
- BASE, HYDRO and COUPLED must use the same model, physical options, boundary
  forcing, damping and time step. Freeze metrics and thresholds before results.
- First-call response and 10/30/60-minute pressure, divergence, wind,
  thermodynamic and Q/N/QIB diagnostics must retain observed cloud and dynamic
  signals. Quieter fields alone are not proof of better initialization.

When a block trial fails this optional check, both output states return to the
immutable background and the accepted endpoint ledger is empty. The returned
failure assessment identifies the rejected trial; it does not describe an
accepted state. The check runs before testing the five-field stored fixed point.
An absent contract retains the existing research diagnostic path.

The schema now serializes physical component snapshots, source and boundary
declarations, tolerances, coverage, and—when present—the optional internal
phase ledger under `physical_internal_phase_v1`. The writer replays the same
contract against its received endpoint; the independent reader checks the
complete optional-field group and recomputes the eight-component local
residual from stored values. Legacy no-phase receipts remain valid. A focused
4×4×3 pipeline fixture exercises a nonzero, independently predeclared
condensation extent through writer and both independent readback checks. Its
storage tolerance is a float32 representation allowance fixed from the
fixture inputs and oracle before invocation; it is not physical permission to
alter the state. This fixture demonstrates local feasibility and file replay,
not source authentication, global optimization, a full production candidate,
native acceptance or forecast benefit. The schema-7 production validator
retains its 235×283×22 domain gate and is not used to admit this deliberately
small synthetic artifact.

These conditions remain open until their actual execution evidence is linked
to the same candidate. This document does not lower an acceptance threshold or
authorize a missing source, driver, PSD or boundary value.
