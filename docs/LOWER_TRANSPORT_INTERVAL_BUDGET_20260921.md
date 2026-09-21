# Conditional lower transport and interval boundary budget

## Scope and decision

PR36 connected the retrospective surface normal flux but left every lower side
strip unknown. This experiment binds LSX 10 m winds to LT1 height and static AVG
terrain, reconstructs the strip above that sample, and uses the same three times
for all transport terms. It does not extend the 10 m wind to the material ground.
Production legacy D/G, solver, RHS, masks, boundary authority, and speed limits
are unchanged. There is no balance candidate, ON output, native run, or forecast.

The explicit research contracts are:

- `--height-model log-pressure-static-avg`: static AVG (meters MSL) and LT1 HT
  (meters) are treated as a common height datum. Linear interpolation of log(p)
  in height is anchored at `(terrain, PS)`. The 10 m target is bracketed, never
  extrapolated. Any nonincreasing above-ground height sequence is rejected.
  This is a conditional coordinate reconstruction, not an independently
  verified geometric-height/geopotential-height conversion or uncertainty model.
- `--lower-model linear-normalized-pressure`: the lower strip connects the LSX
  sample to the first pressure level supported at both endpoints above their
  mapped 10 m pressures. Its normalized-pressure interpolation is declared
  below; it is not assumed to be the original LW3 fixed-pressure interpolant.
- The source grid-north convention remains conditional on the pinned include;
  a historical executable/frame certificate has not been established. Both
  LSX and LW3 undergo the same rotation and equal-area coordinate speed scaling.
- `--top-source lw3-derived`: LW3 OM is derived from analyzed winds and terrain,
  not an independent observation. It is not chosen by minimizing the residual.
- `--retrospective`: 12/13/14 UTC products support a Simpson approximation of
  interval-mean transport. Future analyses are not operationally causal at
  13 UTC. Time quadrature and representation errors remain uncalibrated.

The hypsometric relation motivates a log-pressure/height interpolant, but does
not establish that the supplied height and terrain fields have identical datum
or that the interpolant resolves the true near-surface thermodynamic profile.
See [NOAA hypsometric notes](https://www.aoml.noaa.gov/ftp/hrd/annane/prelim_notes/hypsometric_equation.pdf).

## Equations and code

`tests/qbal_lower_transport.f90` contains two small research procedures.
Between a lower anchor `(z_b,p_b)` and an upper sample `(z_t,p_t)`,

\[
 \log p(z)=(1-\alpha)\log p_b+\alpha\log p_t,
 \qquad\alpha=(z-z_b)/(z_t-z_b).
\]

Only pressure levels strictly above the supplied PS enter the height sequence.
Missing or physically reversed above-ground heights leave the node unmapped;
no adjustment of PS, terrain, or height is made to obtain coverage.

Let `c` be the common pressure cap, `p10(s)` the linearly interpolated 10 m
pressure along an oriented edge, and `d(s)=p10(s)-c`. The two velocity traces
`v10(s)` and `vc(s)` are linear in edge parameter `s`. The declared strip is

\[
 v(s,p)=(1-\eta)v_c(s)+\eta v_{10}(s),\qquad
 \eta=(p-c)/d(s).
\]

Its integrated flux is exactly, for this reconstruction,

\[
 F_{10\to c}=\int_0^1 \frac{d(s)}2
 [v_c(s)+v_{10}(s)]\cdot[\Delta y,-\Delta x]\,ds.
\]

The integrand is quadratic. Zero-width endpoints require no division by `d`.
The covered upper profile still uses `edge_wind_flux`; the common cap may move
up one level to remain above both 10 m samples. This avoids double counting the
thin overlap when a pressure sample is below 10 m. The remaining pressure-span
is `mean(PS-p10)` where both endpoints map. If either fails, the previous
joint-above-ground covered profile is retained and the whole lower gap remains
unknown. An integral pressure-span is not a missing-flux error bound.

For fixed horizontal triangles and finite top, the surface term is the same
endpoint volume secant used in PR36:

\[
 \bar F_s=[V(14)-V(12)]/7200.
\]

Sides and top use `(F12+4 F13+F14)/6`, the mean of the three-sample quadratic
interpolant. It is exact for a quadratic time history, not for arbitrary weather
or a profile that changes its interpolation cap. The diagnostic retains unknown
sub-10 m terms even when the known Simpson sum vanishes.

`tests/qbal_domain_flux.f90` validates the signed edge incidence before summing
only the external terms. Unknown internal shared flux cancels symbolically;
unknown external flux keeps the domain residual NaN. Domain completeness is
separate from local completeness and neither implies physical approval.

\[
 \sum_T R_T=\sum_T\bar F_{s,T}
 +\sum_{f\in\partial\Omega}\sigma_f\bar F_f
 -\sum_T\bar F_{t,T}.
\]

The negative known subtotal is reported only as the aggregate **required**
unknown outer flux for zero domain sum. It is not supplied as a boundary value,
not an estimate of the missing flux, and not a local feasibility certificate.

## Validation and actual evidence

The retained run recipe is
`scratch/pr37_validation/run_actual.sh`. It pins the original 12/13/14 UTC case
products, the audit snapshot/static grid, and the PR35 retained frame include.
The report includes input paths and SHA256, source SHA256, prepared stream and
array hashes. The final pinned replay is `scratch/pr37_validation/final2/`; its `report.json`
binds the exact source and input bytes. `stream_final.log`, `lower_final.log`,
`domain_final.log`, `time_final.log` and `mutations.log` retain validation.

| Actual quantity | 12 UTC | 13 UTC | 14 UTC |
|---|---:|---:|---:|
| Mapped 10 m nodes / 66,505 | 66,166 | 66,202 | 66,224 |
| Mapped lower strips / 198,480 | 196,560 | 196,755 | 196,876 |
| Mapped outer strips / 1,032 | 1,001 | 1,010 | 1,004 |
| Maximum remaining span on mapped edges, Pa | 808.0721 | 824.2342 | 736.1981 |
| Maximum remaining span including unmapped edges, Pa | 5,264.2109 | 5,222.7891 | 5,245.3906 |

Mapped means the declared geometric interpolant can be evaluated, **not** that
its implied near-surface thermodynamic state or physical wind profile is valid.
At 13 UTC the first pressure-above-ground HT is at/below AVG at 303 nodes.
These nodes are retained as unsupported, not removed from the domain. The
303 failures are at the lowest above-PS pressure level (123 at 1000 hPa, 138
at 950, 34 at 900, 8 at 850), not internal nonmonotonicity. Across all 66,505
selected nodes, height-minus-AVG ranges from −141.8038 to 588.3073 m. The rejected
303 nodes range from −141.8038 to −0.0920 m. Another 455 nodes have a positive
first-sample height below 10 m. The pressure cap is moved above the mapped sample when necessary.

The input audit found no declared roughness length or displacement height.
Static `std` is terrain elevation standard deviation, not roughness length;
`drag_coef.dat` has no documented conversion to z0. Neither is used to invent a
log-law continuation below 10 m. LT1 HT has no explicit geometric/geopotential
datum attribute, so the common-datum assumption remains conditional.

### Physical decision from the pressure-height check

**`NOT_SUPPORTED_FOR_PHYSICAL_PROFILE`** is the status of this actual-data
height-anchored reconstruction. Mathematical monotonicity alone is insufficient.
As an independent diagnostic, with Rd=287.05 J/(kg K), g=9.80665 m/s², compute

\[
 T_{\mathrm{eff}}=\frac{g(10\,\mathrm m)}{R_d\log(PS/p_{10})}.
\]

This is the mean virtual temperature that a hydrostatic 10 m layer would need
to reproduce the interpolated pressure drop under the common-height assumption.
At 13 UTC its minimum/median/maximum are approximately **26.84 / 301.88 /
90,474 K**, whereas LSX 2 m temperature ranges **285.49–301.98 K**. T2 is not
itself a layer-mean virtual temperature, but the extreme discrepancy demonstrates
that some numerically mapped columns cannot represent the intended physical
near-surface layer. It is not explained by ordinary moisture corrections.
No temperature cutoff is fitted, no pressure/height value is repaired, and no
mapped node is retrospectively removed to reduce the flux budget. The report
retains all percentiles and states that these lower fluxes are a sensitivity
experiment, not validated boundary input.

This identifies a concrete next requirement: establish a thermodynamically
consistent pressure at the wind sample using independently justified temperature,
moisture and height/pressure provenance, then repeat the flux construction.
A thin-layer hydrostatic prior would be a new declared model; neither arbitrary
PS/HT alignment nor selecting whichever mapping closes the budget is justified.

The fixed mesh has 131,976 columns and 198,480 unique edges. Its 197,448 internal
unknown edge terms cancel in the domain aggregate; 1,032 unknown exterior edge
terms remain. Every column still has unknown transport and a NaN full residual.

| Simpson interval domain quantity | m² Pa/s |
|---|---:|
| Surface endpoint-volume secant sum | +1.9667731714e10 |
| Known outer side mean | −1.8121084168e11 |
| Derived LW3 top mean (before subtraction) | −1.4649522914e11 |
| Known subtotal | −1.5047880826e10 |
| Required unresolved outer sum for a zero domain sum | +1.5047880826e10 |

These are conditional integrated **pressure-volume transports**, not kg/s or
velocity increments. The required unresolved sum is not an approved boundary
forcing. The domain/column arithmetic discrepancy is approximately 1.01e-4
m² Pa/s, checked against uncancelled term magnitudes. The full residual remains
null; no improvement ratio against PR36's mixed-time subtotal is claimed.

Validation uses only `tests/intel_toolchain.sh` in fresh scratch directories:

- Lower kernel: 24 checks at each O0/O2; domain kernel: 13 at each O0/O2.
- Prepared Fortran driver: four manufactured cases at each optimization,
  including a quadratic top time history and zero known subtotal with unknowns.
- Six mutations (lower sign, log-pressure direction, false domain completeness)
  fail the intended tests at O0/O2.
- Existing exact-time input tests pass. Extracted `triangular_mesh` returns
  byte-identical triangle, edge and incidence arrays to the PR36 mesh.
- Actual O0/O2 replay checks support masks, integrated transports, geometry,
  pressure mapping, surface-volume identity and domain/column aggregation.

Initial scratch builds caught a selected-height guard that evaluated the prior
below-ground NaN without short circuit; nested guards and corresponding tests
were added before the final replay. Explicit local arrays removed Intel array
temporary warnings from the large driver. These development trials are retained
separately from the final evidence.
