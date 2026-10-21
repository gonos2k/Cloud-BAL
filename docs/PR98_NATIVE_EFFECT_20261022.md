# PR98: native effect of the C1 COUPLED wind correction

## Scope and decision

This report measures the extra C1 COUPLED initial U/V correction relative to
HYDRO, then compares it with the same-location pressure, geopotential (`Phi`),
and mass-point W states in the already completed native 600-second C1 histories.
It changes no model equation, weight, prior, precision, or tolerance. The
receipt-bound numerical result is in
[`native_effect.json`](evidence/pr98_native_effect_20261022/native_effect.json).

HYDRO disables the continuity and force priors together. C−H therefore
measures the combined wind treatment, not either prior's individual effect.

The decision is **do not scientifically approve the additional COUPLED
correction on the measured native-tendency criteria**. Preserve frozen C1 as a
reproducible diagnostic baseline. On the 613 source-supported native mass cells at
initial time, `h = H-O` in U/V has L2 0.03257 m/s over the concatenated fields,
while `b = C-H` has L2 86.2044 m/s. Their inner product is −0.03507, with
`h·h = 0.001061`, `b·b = 7431.204`, and `|h+b|² = 7431.135`; the independent
identity from the terms gives 7431.135. The native face arrays show the same
pattern across the full active crop: H−O U/V RMS are 1.986e−5 and 9.421e−6
m/s, while C−H RMS are 0.04415 and 0.04936 m/s.

At 0 s, C−H pressure, Phi, and W differences are exactly zero on the support.
At 60 s, C−H versus H−O RMS are 34.53 versus 68.26 Pa for pressure, 66.12
versus 42.79 m²/s² for Phi, and 0.2576 versus 0.2450 m/s for W. The added
correction therefore changes the early state response, with different response
sizes by field. These state differences do not say which response is more
accurate.

The balance objective controls U/V increments relative to the background
with 4 m/s scales and evaluates a pressure-level one-neighbor geostrophic
residual (`−f v + dPhi/dx`, `f u + dPhi/dy`) against its background residual.
WRF's native tendency assembly also contains advection, staggered pressure
gradient, Coriolis, curvature, diffusion, RK and mass-flux terms. A smaller
background-relative balance residual would therefore not by itself show that
the assembled native momentum or dry-mass operator improves. The source-form
capture below reports those actual arrays on their native staggered supports.

Receipt-hash-checked raw C1 `wrfinput_d01` files confirm that COUPLED and
HYDRO match in every stored field except native staggered U and V. Their
maximum C−H initial differences are 9.04857 m/s for
U at zero-based `[k,j,i]=[15,15,135]` (one-based native `[i,j,k]=[136,16,16]`)
and 7.99578 m/s for V at zero-based `[16,16,134]` (one-based native
`[i,j,k]=[135,17,17]`). These are staggered faces, so the corresponding
60-second pressure/Phi/W responses are sampled at both adjacent mass centers
after the existing raw outer-ring crop. The four centers are
`[k,j,i]=[15,14,133]`, `[15,14,134]`, `[16,14,133]`, and `[16,15,133]`; all
four happen to lie in the 613-cell support. Their C−H 60-second response
triples `(pressure Pa, Phi m²/s², W m/s)` are respectively `(-7.70, -14.83,
-0.0351)`, `(-0.50, 20.01, -0.1510)`, `(-7.59, -18.16, -0.0438)`, and
`(-6.41, -58.54, 0.2892)`. The checked input dimensions, data types, units,
and staggering match between arms.

A separate complete stored-variable audit reads the same two receipt-bound
HYDRO and COUPLED `wrfinput_d01` files. All 208 variable names, dimensions,
types, units/stagger attributes, complete per-variable attributes, and global
attributes match. Every stored variable is byte-identical except native U and
V. This establishes that U/V are the only stored `wrfinput` variable changes
between these two candidate files; it does not establish equivalence of
unrecorded preprocessing or other candidate artifacts.

## Historical context

The C1 runs did not save per-stage WRF momentum or dry-mass tendency arrays.
The staged source has separate U/V tendency assembly in `rk_tendency`:
advection, horizontal pressure gradient, Coriolis, curvature and diffusion
calls; `rk_addtend_dry` then combines RK tendencies. Dry-mass tendency is
carried separately through `mu_tend`. The saved pressure, Phi, W, U and V
histories do not recover those source terms. Mass-point and map-factor-free
derivatives would not be the native force or continuity operator. The
source-form evidence below comes from a diagnostic-only observer overlay.

## Source-form native capture

A read-only observer overlay saved the native arrays during one 20-second
first step for OFF, HYDRO, and COUPLED. All three runs completed with rc=0 and
one timestep. The raw receipt and two-pass snapshot manifest bind 57 files
(429,851,256 bytes) per arm. The first-20-second trace hashes match the frozen
C1 traces, all 11 checked t0 history fields match bytewise, and expanded T1
pre/post memory dumps match the frozen C1 hashes. This supports observer
noninterference for those checks; it does not prove full-run equivalence.

The guarded first per-tag/per-tile source snapshots lie inside `rk_tendency` in the
Runge-Kutta loop, with the corresponding dry assembly saved around
`rk_addtend_dry`. The actual MU update is captured around `advance_mu_t`.
Snapshots do not encode timestep or RK ordinal; their placement at the first
call follows the source call order and the one completed 20-second timestep.
The `c1h/c2h` rank-1 coefficient files are overwritten at each source call;
the final arrays are identical across arms. Source signatures declare these
coefficients `INTENT(IN)`, and the captured calls do not assign them.
The momentum support is the boolean union of native i/j/k faces adjacent to
the original 613 supported mass cells. Each face is counted once. MU and MUDF
are evaluated on the 16 unique support columns. Norms are equal-cell,
unweighted L2 values in the source arrays' native units. They are not
acceleration or energy norms. W is reported separately because the capture
does not include the vertical coefficients needed to normalize its tendency.

On the 613-cell-derived support, the broad `rk_addtend_dry` assembled RU
output has L2 17,016 (OFF), 24,362 (HYDRO), and 41,212 (COUPLED). Its
increments are `h=H-O` 17,542, `b=C-H` 34,199, and `C-O` 38,785, with
`h·b=13,507,815`. For RV, absolute L2 values are 17,654, 23,909, and 34,051;
the corresponding increment L2 values are 14,447, 28,148, and 27,889, with
`h·b=-111,619,536`. For RW, absolute L2 is 2,125, 2,126, and 2,193; `h`, `b`,
and net L2 are 376, 641, and 742, with `h·b=-1,217`. RU/RV/RW remain separate
because they occupy different native staggers. The machine-readable evidence
records each absolute norm, increment norm, dot product, square, and net-norm
identity.

The captured source-call deltas explain where the extra initial wind enters
these tendencies. For U, the advection increment `b` has L2 16,456 and the
horizontal diffusion increment has L2 28,461. For V, those values are 19,487
and 18,712. The source pressure-gradient C−H increments are about 0.001 for
RU and RV despite identical initial pressure/Phi inputs; these are differences
between observed R32 tendency arrays and can include within-call R32
accumulation roundoff. The Coriolis increments are 408 for RU and 363 for RV. Selected operator
contributions are not an exhaustive decomposition: buoyancy, W damping,
implicit advection, vertical diffusion and other conditional terms are not
captured. Vertical-diffusion hooks were inserted in the source but emitted no
snapshots: `bl_pbl_physics=11` bypasses the `bl_pbl_physics==0` branch.
`dyn_*_final` is sampled before `rk_addtend_dry`; the assembled output is the
broadest captured momentum endpoint.

Summing the captured pressure-gradient and Coriolis call deltas componentwise
before taking norms gives a selected two-source partial RHS. Its RU absolute
L2 values are 16,920 (OFF), 24,263 (HYDRO), and 24,025 (COUPLED); the `h`,
`b`, and net increments are 17,541, 408, and 17,206, with `h·b=-5,915,766`.
For RV, the absolute values are 17,558, 23,848, and 23,618; the increments
are 14,441, 363, and 14,119, with `h·b=-4,660,332`. The compatible native
arrays are summed before norms; these values do not represent a complete force
balance residual. As for individual operator deltas, differences and sums are
computed in float64 after promoting captured R32 operands; they are not
unrounded formula evaluations.

The actual small-step dry-mass output `MUDF` has L2 3.064 (OFF), 6.893
(HYDRO), and 147.643 (COUPLED) over 16 columns; its `h`, `b`, and net increment
norms are 6.121, 148.843, and 148.106. `MUDF` is the actual returned combined
native `DMDT+MU_TEND` output. Separately inspected source at
`/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/dyn_em/module_small_step_em.F`
(SHA-256 `cabf1a17…c17634`) expresses `MUDF=DMDT+MU_TEND`; it is not proven to
be the compiled implementation in this overlay. The actual returned `MUDF`
and observed `MU` update are authoritative. The saved `(MU_after-MU_before)/dts` matches it to a
maximum absolute residual of 3.23e-8, 8.20e-8, and 1.87e-6 by arm, with
`dts=6.6666665 s`. This checks the combined update only. DMDT flux operands
were not captured, so it is not a continuity-flux closure.

All captured coordinate coefficients and map-factor arrays are byte-identical
across arms. Dynamic `mu/mut/muu/muv` hashes differ over full allocated arrays,
but C−H is exactly zero over the 16 unique support mass columns for `mu/mut`
and the 20 unique adjacent U/V-face columns for `muu/muv`; H−O differs. The
native support origin explicitly maps the history mask's one-cell cropped
coordinates to source Fortran mass indices starting at `(i=2,j=2,k=1)`.
The analysis uses no mass or map-factor weighting, so it
does not treat these arrays as a common energy metric. The native capture
source, executable, receipts, raw snapshot manifests, geometry hashes, and
noninterference checks are bound in
[`native_effect.json`](evidence/pr98_native_effect_20261022/native_effect.json)
and the per-arm capture package in `evidence/pr98_native_capture_20261022/`.

Observation skill is **NOT_EVALUATED**: no independent observation target or
observation operator was used. Physical approval remains **FAIL_OPEN**. The
measured C tendencies do not demonstrate a reduction in the scoped assembled
RU/RV and MUDF criteria relative to HYDRO. Preserve the frozen baseline for
diagnosis. A future revision should address the pressure-level objective's
mismatch with native advection, diffusion, and continuity after causal
attribution; this evidence does not support a blind weight or cap change.
Forecast skill remains **NOT_EVALUATED**.

## Reproduction

`tools/pr98_native_effect.py` validates the three closed receipts and history
hashes, reads saved 0 and 60 second fields, and reuses the unchanged 613-cell
support. It also verifies the native-capture run receipts against the stable
raw manifests, verifies each raw file against its receipt hash, and summarizes
the source arrays over boolean native face masks. Native U/V face statistics
use the original staggered arrays; the same-cell initial U/V inner products
use the existing mass destagger. The pressure, Phi, and W comparisons use the
existing history reader. This is post-processing only and launches no forecast.
Focused tests passed 14/14;
`py_compile` and `git diff --check` passed. The native capture used the pinned
Intel profile in a fresh scratch build. It was a partial source-mapped overlay,
not a clean full-model build.
