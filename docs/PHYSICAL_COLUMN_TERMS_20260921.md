# Retrospective surface flux and explicit incomplete column budget

Status: **RETROSPECTIVE_SURFACE_VOLUME_CONNECTED / INCOMPLETE_COLUMN_FLUX**.
Base: PR35 merge `81faedcd473b717d62bcf0697a6746541a3cc12b`.
Production Fortran, legacy D/G, RHS, support, boundary permission and increment
limits are unchanged. The numerical connection is in small research Fortran
procedures; Python prepares inputs and records evidence.

## Surface normal flux on the same reconstructed triangle

For a fixed horizontal triangle of area A, affine surface pressure, and fixed
finite top pt, the pressure volume and surface normal flux are

```
V(t) = A * (sum(PS_vertices(t))/3 - pt)
Fs   = A/3 * sum((PS_after - PS_before)/(t_after - t_before))
     = (V_after - V_before)/(t_after - t_before).
```

`surface_pressure_flux` calls the existing `pressure_secant` and
`sloping_column_faces`, so the surface integral and endpoint volumes use the
same geometry. It checks their difference on the uncancelled volume scale.
The 64-epsilon arithmetic allowance is not an accepted physical residual or a
statistical boundary uncertainty. Units are m2 Pa/s, not kg/s. Area division
produces Pa/s, not a local omega observation.

This is the integrated normal combination
`omega_s - U_s*PS_x - V_s*PS_y`, so separate material-surface velocity samples
are not needed to evaluate this pressure tendency term. They are still needed
to reconstruct individual surface omega or the missing lower side transport.
The volume tendency is not added again to the column equation.

## Exact time contract and retrospective scope

The PR35 preparer no longer converts `valtime` to integer before checking it.
`validate_product_time` follows the existing single-record double, epoch-unit,
finite/nonmissing and integer-second contract, then compares the exact value.
LSX and LW3 with fractional seconds are rejected, including .25 and .75.
The same validation is reused for the surface time pair and LCO top inventory.

The actual LSX pair is 12 and 14 UTC on 2026-08-16, centered on the 13 UTC
geometry and LW3 sample. `--retrospective` is required. This secant is a two-hour
mean tendency. It is neither an instantaneous 13 UTC derivative nor available
at 13 UTC; no operational delivery receipt is inferred from file times.
The known subtotal combines this interval-mean boundary trend with central-time
LW3 transport (and central-time top data if present). Temporal representation
remains unresolved; it is not an exact instantaneous or interval-integrated
continuity residual even if all spatial terms become available.
The horizontal chart/triangle connectivity is fixed across all three samples.
The pressure surfaces can change, but every endpoint must remain above pt.

## Column terms and unknowns

```
R = Fs + sum(sign_f * (Fcovered_f + Fmissing_f)) - Ftop
Ftop = integral_A omega(pt) dA
```

`column_flux_budget` accepts explicitly known missing-strip and top terms.
Its `subtotal` includes only known terms. Its full `residual` is NaN whenever
any required term is unknown; the report keeps the full physical result null.
An unknown value is never replaced by a physical zero. Zero missing-strip
transport is allowed only when the measured uncovered interval is exactly
zero. Synthetic complete cases verify the full equation and signs; those tests
are not substitutes for the incomplete real input.

The explicit `--top-source lco` inventory uses same-time, same-navigation
LCO COM at 5000 Pa.
All **66,505** top samples are fill values, so all **131,976** triangle top terms
remain unknown. This is a data-availability result, not a zero-flux condition.
COM is cloud-derived omega, not a separately established observation of the
finite-top boundary.

A second, explicitly selected `--top-source lw3` experiment integrates the
same-grid LW3 `OM` field at 5000 Pa: `Ftop = A*mean(OM_vertices)`. All 66,505
samples are finite. This is a **conditional file-field integral**, not an
approved boundary. Legacy `bgdata/lapsio.f` reads this LW3 omega but does not
use it as the QBAL omega target. Its numerical availability does not establish
its producer physics or boundary authority. Both source alternatives are
retained; neither is selected by whichever subtotal is smaller. The scalar
omega integration does not require a horizontal wind-frame rotation.

Available producer source `klaps-v5.0_/src/wind_openmp/main_sub.f` calls
`wind_post_process` then `vert_wind`, and writes its `wanl` as LW3 `OM` in
Pa/s. `vertwind.f` constructs terrain-induced omega from surface wind and
pressure gradients, then integrates horizontal convergence with its beta
correction upward. Thus this field is derived from the analyzed winds and
terrain forcing. It is **not independent evidence** for those same winds and
must not be weighted again as an independent observation. Source hashes are
retained in `inputs/omega_source_receipt.json`; the historical executable
identity has not been revalidated. The FUA and LW3 finite-top fields also have
very different ranges (-0.303459 to 0.600421 versus -10.371717 to 11.317911
Pa/s); these are different products, not interchangeable boundary estimates.
No calibration or collocated forecast-error statistic is inferred.

The background FUA `OM` is a separate model prior. Its origin metadata differ
from LSX (`La1`: 31.34450912475586 vs 31.344505310058594 degrees;
`Lo1`: 119.79930114746094 vs 119.79931640625 degrees). It is not substituted
by array index or silently remapped. The pressure/boundary contract and
coordinate mapping must be established before using it on these triangles.
The separate LSX U/V are 10 m AGL samples: their valid values do not by
themselves define the unobserved material-surface profile. No lower strip is
filled with a nearest pressure-level or 10 m value in this change.

## Actual pinned Intel evidence

The fresh O0/O2 replay rebuilds the PR35 sloping-face calculation first,
including its exact input/time/geometry checks, then constructs the surface
and column terms. The earlier conditional wind-frame interpretation remains;
no source flag is promoted to a verified historical producer identity.

| Quantity | Result |
| --- | ---: |
| Triangular columns | 131,976 |
| Side faces with missing lower transport | 198,480 / 198,480 |
| Valid LCO samples at finite top | 0 / 66,505 |
| Columns with complete physical flux | 0 |
| Maximum absolute surface normal term / area | 0.0552086950231 Pa/s |
| Maximum Fs minus endpoint-volume secant | 5.16447e-8 m2 Pa/s |
| Maximum difference / its arithmetic allowance | 0.0116306 |
| Maximum known subtotal / area | 27.3622356475 Pa/s |
| Complete physical column residual | null |

The table above is the LCO selection. With the conditional LW3 selection,
all 131,976 top integrals can be evaluated; their maximum absolute value
per area is **11.1003621419 Pa/s**. The known subtotal maximum is then
**28.5702595603 Pa/s**. All lower side strips remain unknown and the complete
residual is still null. The raw LW3 top OM spans -10.37171745 to
11.31791115 Pa/s; finiteness and file range checks do not constitute a
meteorological acceptance test.

The known subtotal is **surface tendency plus covered side transport** in
the LCO selection. It omits the unknown bottom-side and top terms. The LW3
selection subtracts the conditional top integral, but still lacks lower-side
transport. Its magnitude is
not a full imbalance, target, observation error or evidence of balance
improvement. The reconstructed triangle surface term is not expected to
match the maximum individual node pressure tendency.

The new term outputs are byte-identical at O0/O2 in this replay. The nested
PR35 wind integration still has its recorded nonzero O0/O2 rounding difference;
its comparison uses uncancelled arithmetic scales, not a bitwise claim.
An independent pressure-difference/triangle-area calculation matches Fs within
1.75e-10 m2 Pa/s. Summing the covered side terms over cells and over only outer
edges differs by 6.11e-5 m2 Pa/s, within the uncancelled sum allowance.
These identities do not remove the unknown boundary terms.

The central PS differs from the mean of the two endpoint pressures by up to
195.46875 Pa. This is evidence of temporal representation differences, not a
calibrated error estimate or a reason to enlarge a physical tolerance.

## Validation and reproduction

```
python3 tests/test_qbal_sloping_inputs.py
bash tests/run_qbal_column_budget_tests.sh
python3 tests/diagnose_qbal_column_budget.py \
  --snapshot /path/operator_snapshot.bin --static /path/static.nest7grid \
  --lsx /path/262281300.lsx --lw3 /path/262281300.lw3 \
  --frame-evidence /path/main_sub.inc --radius-m 6371200 \
  --lsx-before /path/262281200.lsx --lsx-after /path/262281400.lsx \
  --lco /path/262281300.lco --epoch 1786885200 --interval-seconds 3600 \
  --retrospective --top-source lco --output-dir scratch/column_actual
```

The new Fortran suite passes 19 checks per Intel level. Six wrong surface-sign,
top-sign and incomplete-residual mutations are rejected across O0/O2.
Exact-time tests use real temporary NetCDF files. Actual preparer CLI calls with LSX +0.25 seconds and LW3 +0.75 seconds are both rejected before any build. The actual replay and its
input/source/artifact hashes are retained in
`scratch/pr36_column_budget_20260921/Cloud-BAL/scratch/pr36_validation/final_lco/`.
The companion `final_lw3/` run records the explicit LW3 top alternative
(`--top-source lw3`, omitting `--lco`). LCO is required only for the LCO
selection and is not an input or hash dependency of the LW3 selection.
The adjacent `inputs/manifest.json` retains 12/14 UTC LSX and LCO inputs by hash;
`independent_budget.py/json` records the independent arithmetic comparison.

Next resolve the lower profile's height/frame/sampling and the finite-top
source-to-triangle mapping. Evaluate the complete column equation only when
all terms have defensible support. Vertical subdivision then needs common
moment origins, volume partition and shared-flux conservation. Mobility,
velocity-space limits, production balance, ON, native mass/thermodynamics and
forecast verification remain separate and unapproved.
