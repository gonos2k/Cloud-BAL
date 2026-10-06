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
condensate at fixed pressure geometry can therefore change dry mass. A zero
endpoint accounting identity does not authorize that change.

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
Only their net increment \(I=I_{\mathrm{source}}+I_{\mathrm{boundary}}\) is checked.
The local comparison is

\[
|C_i^a-C_i^b-I_i|\le t_i+e_{\mathrm{arithmetic},i}.
\]

The arithmetic allowance uses the operand scale and binary64 rounding;
it is separate from the caller's physical tolerance. Every changed atmospheric
cell must be covered, including unchanged cells in the declared atmosphere.
Opposite local residuals cannot cancel through a domain
sum. Missing species, geometry changes, missing declarations or unsupported
criteria must remain explicit; they do not become zero residuals.

This prescribed-increment check cannot authenticate the supplied increment.
It must not construct \(I\) from the endpoint it is checking. In a complete
physical contract, independently admitted analysis, physical-time boundary
transport and internal phase transfers determine \(I\). Only internal phase
transfer has zero dry increment and zero total-water increment; external
analysis or transport can change either. Solver iterations are not a physical
transport interval. The current producer does not supply this complete policy.

A local feasibility pass is distinct from stored-value convergence,
observational fit, constrained stationarity, native acceptance and forecast
benefit. In particular, the existing five-field fixed point does not establish
an optimum. The default research path retains its diagnostic status when no
independent contract is supplied.

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

The new contract and its assessment are in-memory API data. The present
SHADOW schema does not serialize the declarations and its writer cannot
independently reconstruct a contracted assessment. It rejects a result whose
assessment differs from its own default research re-evaluation rather than
discarding the new fields. A component PASS therefore does not grant a
SHADOW publication or native acceptance.

These conditions remain open until their actual execution evidence is linked
to the same candidate. This document does not lower an acceptance threshold or
authorize a missing source, driver, PSD or boundary value.
