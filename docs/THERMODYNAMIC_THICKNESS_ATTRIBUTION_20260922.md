# Matched-layer temperature and moisture thickness attribution

## Scope and common operator

PR40 captured temperature after `insert_tobs`, background specific humidity and
pressure immediately before HT generation, and HT immediately afterward. This
study compares that captured state a with final LT1 T3 / LQ3 SH state f on the
same retained 13 UTC case. It does not rerun or change the producer, shift HT,
change PS, fill a missing wind profile, or create a balanced candidate.

Specific humidity q uses the moist-gas mass denominator. For this gas-only
diagnostic, epsilon=0.622 and alpha=1/epsilon-1 give

\[
 T_v=T(1+\alpha q),\qquad
 \delta T_v=(1+\alpha\bar q)\delta T+\alpha\bar T\delta q.
\]

The second identity is exact; the midpoint definitions distribute the bilinear
cross term symmetrically. They are not an estimate of observational causality
or a calibrated error covariance.

For every matched regular layer, bottom pressure pb exceeds top pressure pt.
All five integrals use the same linear quadrature

\[
 Q[f]=\frac{R_d}{g_0}\log(p_b/p_t)\frac{f_b+f_t}{2},
 \quad R_d=287.05,\quad g_0=9.80665.
\]

The outputs are Z_a=Q[Tv_a], Z_f=Q[Tv_f],

\[
 \delta Z_T=Q[(1+\alpha\bar q)\delta T],\qquad
 \delta Z_q=Q[\alpha\bar T\delta q],\qquad
 \delta Z=Q[T_v^f-T_v^a].
\]

Thus delta Z_T + delta Z_q equals delta Z to arithmetic precision. Swapping
states changes all three signs. The quadrature is exact for the declared
linear interpolation of each endpoint integrand in log pressure. It is not
an exact integral of arbitrary atmospheric profiles, nor of the quadratic
product obtained by independently interpolating T and q linearly. No Simpson
or changed interpolation is applied to only one state or contribution.

The numerical bounds (100–120000 Pa, 100–500 K, 0<=q<1) limit research inputs;
they do not certify a physical atmosphere. Nonfinite or invalid supported
inputs reject the calculation, leaving every scalar output NaN. Closure uses
an epsilon scale built from uncancelled before/after thicknesses and absolute
contributions, not an epsilon times an already-cancelled thickness change.
The coefficient is a diagnostic arithmetic allowance, not a universal error
certificate, physical tolerance, sigma or authority to modify a state.

## Support, source order and unchanged heights

Captured arrays use (x,y,pressure) with pressure descending from 110000 to
5000 Pa. Final products store pressure in ascending order and spatial axes
(y,x); preparation explicitly transposes and reverses them. Exact valid time,
units, navigation, shape, pressure values and source hashes are checked.
No interpolation is used to force source grids to agree.

A common level mask requires both states' source support and finite values,
plus p<=the same LSX PS. A layer is present only when both adjacent levels
pass. Missing interior levels break integration; they are not bridged. HT
below AVG is not silently excluded to make the datum diagnostic look better.
The input HT values and their below-sea-level metadata conflict are preserved
as diagnostic evidence; below-ground pressure levels remain excluded.

The lowest retained pressure level need not be the physical surface. Column
outputs are explicitly **sums of matched regular layers**, not completed
surface-to-top thickness. The ground partial layer, unsupported intervals and
absolute height datum remain separate. Different columns can cover different
pressure ranges; their sums must not be treated as equal-domain comparisons.

For the same unchanged HT endpoints, the study also stores

\[
 e_a=HT_t-HT_b-Z_a,\qquad e_f=HT_t-HT_b-Z_f.
\]

Their difference is -delta Z under this operator. A common HT offset cancels
from both layer differences, so neither small e_a nor reproducible HT establishes
the absolute height datum. Changes in these residuals can be attributed under
the common diagnostic operator; an existing stage residual cannot automatically
be attributed to final T/q changes. Geopotential/geometric height conventions,
producer constants and integration rules must still be distinguished.

Extremum records retain the same i/j, bottom/top pressures and all colocated
terms. Separate maxima of temperature and moisture contributions are not added
to manufacture a column or layer effect.

## Retained execution and limitations

The actual arrays, support inventory, colocated extrema, arithmetic checks and
source receipts are recorded after the pinned Intel O0/O2 replay below.
PR40's same-stage capture remains conditional retained-binary evidence. Its
verified launcher's stale builder hash has not been updated by this study.
No full source build or operational launcher closure is claimed.

This diagnosis covers gas virtual-temperature thickness only. Condensate
loading, latent heat, buoyancy response, nonhydrostatic motion, complete face
fluxes, ON/native consumption and forecast skill remain separate.


## Same-stage baseline is not a producer reproduction test

Source inspection of `klaps-v5.0_/src/lib/get_heights_hydrostatic.f` and
`klaps-v5.0_/src/include/constants.inc` distinguishes the two operators. The producer
uses real*4, Rd=287 and g=9.81, converts SH to dewpoint through `make_td`,
and evaluates `W_laps` with a saturation-pressure lookup at rounded integer
Celsius dewpoint. Its endpoint factor is `T*(C2+W_laps)`, with
`C2=Rd/(2*g)` and `W_laps=C2*EP_1*0.622*e/(p-e)`. This is a mixing-ratio
virtual-temperature approximation with a lookup, rather than the direct
specific-humidity formula used here. The producer also anchors heights at
an MSL pressure crossing. These source facts explain why the diagnostic
operator need not reproduce even the captured stage's HT layer thickness.
They do not quantify each cause's share of that baseline difference.

The matched-layer stage defect ranges from -2.270638 to +0.050349 m;
the final-state defect ranges from -3.334525 to +2.713495 m. Their changes
obey `e_f-e_a=-delta Z`. The stage defect is retained, not subtracted from
input HT or called a final-analysis error. PR40's bitwise HT reproduction
and this operator-relative residual therefore answer different questions.

## Actual13 results

The valid time is 2026-08-16 13:00 UTC (epoch 1786885200), on the retained
235 by 283 by 22 grid. Common above-ground support contains **1,228,494
regular layers in 66,505 columns**, with zero source-invalid above-ground
levels. The 168,111 final LQ3 fill values are underground. Neither these
values nor ground partial layers are filled. Static provenance remains
`static.nest7grid` SHA-256
`384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b`
and `pressures.nl` SHA-256
`a02a5e18c39cfaa505d3f52cbf1ec9366ca9f91dc24508fdd0167d3f7ebd014f`
in the retained actual13 `input_snapshot/static/`; the actual calculation
uses captured pressure and final LSX PS, not terrain-based completion.

| Matched regular-layer change, m | Minimum | Maximum | RMS |
| --- | ---: | ---: | ---: |
| Temperature contribution | -2.866622 | 2.885069 | 0.195487 |
| Moisture contribution | -0.473681 | 2.203461 | 0.082454 |
| Total | -2.857763 | 3.142897 | 0.227636 |

| Sum of each column's matched layers, m | Minimum | Maximum | RMS |
| --- | ---: | ---: | ---: |
| Temperature contribution | -2.867064 | 3.783059 | 0.921336 |
| Moisture contribution | -1.826970 | 7.850227 | 0.592256 |
| Total | -2.858205 | 9.601824 | 1.280423 |

These are gas-only thickness changes on varying matched pressure ranges,
not full ground-to-top thickness or observed height errors. At the largest
absolute layer change, Fortran `(i,j)=(68,102)`, 100000 to 95000 Pa,
the colocated contributions are +2.885068858 m temperature and
+0.257828294 m moisture, totaling +3.142897152 m. The largest moisture
layer contribution occurs elsewhere, `(235,2)`, 60000 to 55000 Pa:
+2.203460784 m moisture and +0.000038994 m temperature. This prevents
combining unrelated extrema into an invented layer.

Both pinned Intel builds agree within the common arithmetic allowance.
The maximum layer attribution closure divided by its allowance is
0.005890635. This validates numerical attribution for the declared operator;
it is not a statement of physical uncertainty or a tolerance for changing HT.

The largest absolute matched-column change is at `(55,162)`, covering the
19 regular layers from 100000 to 5000 Pa. Its colocated contributions are
+1.751597725 m temperature and +7.850226581 m moisture, totaling
+9.601824306 m. This result does not include the PS-to-100000 Pa partial
layer and does not repair the unchanged HT.

## Reproduction and checks

Run from the PR41 repository worktree. These commands use retained input
receipts in neighboring scratch worktrees; they are not a standalone input
bundle and do not rerun the historical producer.

```bash
bash tests/run_qbal_thickness_attribution_tests.sh
python3 tests/diagnose_qbal_thickness_attribution.py \
  --source-report "$PR39_REPORT" \
  --ht-dir "$PR40_HT_DIR" \
  --output-dir scratch/pr41_validation/final
. tests/intel_toolchain.sh
python3 tests/test_qbal_thickness_prepared.py \
  scratch/pr41_validation/final/O0/diagnose \
  scratch/pr41_validation/final/O2/diagnose \
  --artifact-dir scratch/pr41_validation/prepared_final
```

`PR39_REPORT` is the absolute path to
`Cloud-BAL/scratch/pr39_profile_20260922/Cloud-BAL/scratch/pr39_validation/final/report.json`
under the KLAPS50 workspace; `PR40_HT_DIR` is
`Cloud-BAL/scratch/pr40_shared_profile_20260922/Cloud-BAL/scratch/pr40_validation/ht`.
Output directories must be new. The PR41 worktree is
`Cloud-BAL/scratch/pr41_thickness_20260922/Cloud-BAL`.

Retained evidence under its `scratch/pr41_validation/`:

- `final/report.json`: current source/input/artifact SHA-256 values, support
  inventory, all field statistics and colocated extrema.
- `final/arrays.npz`: pressure, PS, common support, all nine layer fields and
  matched-layer column sums; `final/{O0,O2}/result.bin` are raw Fortran output.
- `kernel_mutations/original_runner.log`: eight unit-test scenarios with
  52 assertions at each pinned Intel optimization level (PR42 runtime-counter
  correction of the earlier manual count of 54; all eight scenarios pass).
- `kernel_mutations/receipt.md`: temperature sign, moisture sign and failed
  output transaction mutations all detected at O0 and O2 (six rejections).
- `prepared_final.log`: two valid masked/gapped driver runs and eight invalid
  prepared-input runs, using a 70-digit Decimal reference for the valid
  thickness terms. Invalid support, supported NaN, underground support and
  extra stream bytes reject without creating an output file.
- `input_lineage.md`, `math_review.md`, `team_review.md`, `validation.json`:
  source audit, independent review and final validation receipts.

Intel compilation uses `tests/intel_toolchain.sh` and new scratch build
folders at O0/O2. No GNU/ifort substitute is used. The actual replay includes
the complete Python/netCDF4 preparation and Fortran driver, not an API stub.
`actual_v1` and `actual_v2` are intermediate runs; `final` binds the reviewed
sources and is the actual-case validation cited above.

The next physical work is described in
[Lower-profile domain and prior](LOWER_PROFILE_DOMAIN_DESIGN_20260922.md).
This PR closes the requested matched-layer attribution, not absolute datum,
physical lower-domain extension, full column flux or production balance.
