# Thermodynamic sample-pressure prior and height consistency

## Research contract

PR37's terrain/LT1 anchored log-pressure interpolant is retained as a sensitivity
experiment, not physical input. This change adds an explicitly selected
`constant-surface-thermodynamics` alternative. It uses LSX surface temperature
and dry-air mixing ratio as **constant over a 0–10 m layer**. That is a declared
thin-layer prior (the generic helper accepts 0–100 m, while this replay fixes
10 m), not an assertion that a 2 m sample resolves the whole layer,
its stability, condensate loading, roughness, or calibrated uncertainty.

The numerical implementation stays in Fortran and reuses the canonical
`cloud_bal_state::moist_gas_density` gas equation of state. No production solver,
D/G, RHS, mask, boundary authority, speed limit or stored state is changed.
The existing face, time and unknown-flux contracts remain: Simpson 12/13/14 UTC
transport and 12–14 UTC surface-volume secant; derived LW3 top is not independent
observation; 0–10 m side transport remains unknown.

## Equations

With dry-air mixing ratio r (kg vapor/kg dry air), the canonical gas EOS gives

\[
 T_v=T\frac{1+r/\epsilon}{1+r},\qquad \epsilon=0.622.
\]

The kernel obtains the same value via `Tv=PS/(Rd*moist_gas_density(PS,T,r))`,
using Rd=287.05 J/(kg K) and g=9.80665 m/s² consistent with the canonical module.
For constant T and r and the declared geometric-height prior,

\[
 p_h=PS\exp[-gh/(R_dT_v)].
\]

No LT1 level is selected to compute p_h; hence a pressure-level crossing cannot
switch its anchor. At fixed T/r/h the mapping is proportional to PS. Returned
sensitivities are partial derivatives with respect to h and independently varied
Tv, not total derivatives of every correlated source quantity:

\[
 \partial_h p_h=-\frac{gp_h}{R_dT_v},\qquad
 \partial_{T_v}p_h=\frac{ghp_h}{R_dT_v^2}.
\]

The hydrostatic/virtual-temperature relationship is described in the
[NOAA/NWS thickness tutorial](https://www.weather.gov/source/zhu/ZHU_Training_Page/Miscellaneous/Heights_Thicknesses/thickness_temperature.htm).
This reference supplies the physical equation, not the actual layer's covariance
or the producer height datum.

The separate height diagnostic evaluates

\[
 r_\Phi=g(z_t-z_b)-R_d\frac{T_{v,b}+T_{v,t}}2\ln(p_b/p_t).
\]

This trapezoid is exact for the declared linear Tv versus log-pressure profile.
It avoids division by a pressure log ratio that tends to zero. We report surface
to first pressure-above-ground and internal above-ground pressure pairs separately.
Negative height differences remain measurable defects; no height or PS is moved
to cancel them. For LT1/static heights the use of g*height is still a conditional
common-datum approximation, not proof that geometric and geopotential heights
are interchangeable. A residual is not automatically an observational error.

## Input evidence and validation

LSX writer `src/sfc/lapsvanl.f:1140–1154,1222–1245` identifies T/TD and MR
as 2 m AGL, PS as unreduced 0 m AGL pressure. MR is dry-air mixing ratio in
g/kg; the NetCDF units retain the producer schema spelling `grams/kikogram`.
The input adapter converts it to kg/kg. The producer routine
`klaps-v5.0_/src/lib/laps_routines.f:1949–1965` derives MR from TD and PS,
so MR, TD and PS are not independent observations. We use direct MR and do not
add another saturation-pressure approximation.

LQ3 SH is converted from specific humidity q to dry mixing ratio q/(1-q)
for the separate LT1 temperature/height consistency calculation. It does not
set the thin-layer pressure prior. Every product is pinned by exact time,
pressure grid, navigation, units and input hash.

The source chain also explains why these are not identical-state comparisons.
`put_temp_anal` calls `get_heights_hydrostatic` using temperature before final surface insertion and model/background SH;
that routine anchors a crossing of **LSX MSL pressure** to zero height (or uses
its fallback reference), while this diagnostic anchors the ground with **LSX PS
and static AVG**. LT1 surface-temperature insertion and final LQ3 moisture
analysis occur later. Consequently final LT1 T3/LQ3 SH need not reproduce the
thermodynamic state originally used to construct HT. The current case sets
`L_ADJUST_HEIGHTS=.false.`. Sources:
`klaps-v5.0_/src/lib/temp/puttmpanal.f:130–262`,
`klaps-v5.0_/src/lib/get_heights_hydrostatic.f:97–242,294–315`, and
`klaps-v5.0_/src/humid/lq3_driver1a.f:567–791,1247–1252`.
The height routine describes geometric thickness in metres; the canonical reader's
`HT*GRAVITY` is an adapter convention, not a native geopotential datum declaration.
The source path is evidence of different reference/construction histories, not
proof that a single producer operation caused every actual discrepancy.

Actual MR reconstructed with the producer TD/PS formula differs by at most
1.63e-5 g/kg across the three cases; substituting reduced P gives up to 2.64 g/kg.
This independently supports the PS basis. No RH/TD observation is added to the
prior cost, and no cost/covariance is calibrated by these differences.

Ground-to-first-level height diagnostics are `DATUM_UNVERIFIED`; their size
cannot identify PS alone as the cause. Internal height differences remove a
constant datum offset, but still depend on the declared geopotential/height
interpretation and log-pressure quadrature. Neither diagnostic is used to
adjust the source arrays or tune a boundary flux.

## Same-case pinned Intel replay

Evidence: `scratch/pr38_validation/final/report.json`, `arrays.npz`,
`prepared.bin`, `intel.log`, and `run.sh`; the invocation is retained in
`scratch/pr38_validation/run_actual.sh`. The report pins input, source and
artifact SHA256 values. O0/O2 were compiled in separate fresh scratch directories
with `tests/intel_toolchain.sh`. Source hashes are checked across compilation.

| Quantity | 12 UTC | 13 UTC | 14 UTC |
| --- | ---: | ---: | ---: |
| Prior-supported nodes | 66,505 | 66,505 | 66,505 |
| Prior-supported lower faces | 198,480 | 198,480 | 198,480 |
| Prior Tv range (K) | 286.414–306.015 | 287.335–305.380 | 285.982–305.086 |
| Maximum unresolved face-mean PS−p10 (Pa) | 115.9013 | 116.0340 | 115.7708 |
| Ground rPhi range (m²/s²) | −2161.507–1908.003 | −2162.756–1909.524 | −2158.588–1936.726 |
| Internal rPhi range (m²/s²) | −42.283–29.126 | −32.701–26.610 | −22.249–30.834 |

At 13 UTC the old height-mapped minus new prior pressure spans
−1045.636 to +113.431 Pa, with median −0.0589 Pa on points where the old map
exists. The surface reference discrepancy is much larger than internal thickness
residuals under this diagnostic. This localizes a ground-reference inconsistency;
it does not establish whether terrain, PS, HT datum or layer representation is
its sole cause.

Recomputed conditional Simpson outer transport is
−1.8138003595933768e11 m² Pa/s. The unchanged surface secant and derived top
combine with it to give known subtotal −1.5217075103309818e10 m² Pa/s.
This replaces the old conditional experiment's subtotal for this prior only;
its opposite is **not** an observed or authorized boundary forcing.
All 1,032 outer faces still have unresolved 0–10 m transport. Internal unknown
faces cancel in the global sum, but all 131,976 column residuals and the domain
physical residual remain NaN/null. Prior support does not mean full physical
profile support.

The new Fortran kernel suite passes 33 assertions at each pinned Intel O0/O2 level. Prepared-stream tests
pass four cases per mode (old height mapping and new thermodynamic prior) at
both optimization levels. They retain time/NaN budgets and show that rejected
LT1 height anchors do not control the new prior. O0/O2 actual masks agree and
numerical outputs pass the declared arithmetic comparisons. The new driver in legacy mode also reproduces both PR37 final2 actual result
binaries byte for byte (`scratch/pr38_validation/legacy_replay/`). No BALCON solve,
ON/native/startup/forecast run is included.

Independent team review is completed before commit; final review receipts are
retained under the same PR38 scratch tree.

Input/report review also retained both canonical MR unit spellings
(`grams/kikogram`, `grams/kilogram`), rejects surface inputs outside the canonical
EOS envelope, and reports finite diagnostic counts. Missing profile defects stay
NaN in arrays and all-missing percentile summaries are null, not zero.
