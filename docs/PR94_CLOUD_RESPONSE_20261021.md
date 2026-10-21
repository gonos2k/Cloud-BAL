# PR94 frozen-C4 cloud response

## Scope and method

This note analyzes the receipt-bound frozen-C4 `OFF` and `COUPLED` ten-minute histories. Both receipts report `COMPLETE`, return code 0, and completed model step 30. The receipt-bound WRF history files contain eleven outputs at 0, 60, …, 600 seconds. Each frame timestamp is checked against the requested time; the two grids must have equal DX/DY, map factors, latitude/longitude and hybrid vertical coefficients. OFF and COUPLED use different candidate `wrfinput` hashes (the initial perturbation under comparison); their `wrfbdy` and namelist hashes match. The full paths and SHA-256 identities are recorded in [`cloud_response.json`](evidence/pr94_cloud_response_20261021/cloud_response.json).

Cloud support is fixed from the source-composed QC vertical influence: a native level is included when its `composed_qc_source_links` list is nonempty. This yields 613 native values in 16 horizontal columns. The other fixed masks are 2-cell and 5-cell Chebyshev expansions of those columns at all native levels, and the full active history domain. The history reader drops the raw WRF mass-grid outer ring with `[1:-1,1:-1]`; buffers are clipped at this active-domain edge with no wraparound. Their native-value counts are 613, 2,496, 7,644, and 2,533,440, respectively.

For each species and unchanged mask, `delta(t) = COUPLED(t) - OFF(t)` is formed from the actual paired arrays. The reported cosine, projection, and orthogonal residual compare `delta(t)` with `delta(0)`. Projection is `dot(delta(t), delta(0)) / dot(delta(0), delta(0))`; the residual is the RMS of `delta(t) - projection * delta(0)`. These are unweighted array-space descriptions. A small initial species delta can make projection coefficients large, as for QICE early in the run. The code and focused tests are in `tools/pr94_cloud_response.py` and `tests/test_pr94_cloud_response.py`.

## Observed cloud response

On the original 613-value QCLOUD support at 600 seconds, actual arrays give cosine **−0.367995**, projection **−0.096917**, delta RMS **3.295×10⁻⁵ kg/kg**, and orthogonal-residual RMS **3.063×10⁻⁵ kg/kg**. This reproduces the previously calculated cosine and projection from the saved fields. The values show that the QCLOUD response pattern on this fixed support has changed substantially in orientation and is not explained by a scalar multiple of its initial pattern. The 2-cell, 5-cell, and full-domain QCLOUD cosines are −0.268804, −0.249043, and −0.151603; the projection remains about −0.096917 across these masks.

The species do not evolve as a single pattern. At 600 seconds on the original support, QICE has cosine −0.001024 and projection −0.018425; QRAIN has −0.170255 and −0.149252; QSNOW has +0.214760 and +0.159384. QGRAUP has cosine and projection zero, indicating no net component along its initial delta under this unweighted dot-product measure; consult the JSON for residual and RMS values. Species-specific patterns and their changes are plotted in [`plots`](evidence/pr94_cloud_response_20261021/plots/).

## State maps, fixed-coordinate series, and translation scan

Pressure (`P+PB`), mass-level geopotential (`PH+PHB` vertically centered), and mass-point W differences have signed whole-domain maps and fixed-support zoom maps at 60, 120, and 600 seconds. Each map shows the signed difference at the native level with the largest absolute difference in that horizontal column. This per-column maximum-level view is a vertical envelope, not a common pressure or geopotential surface. Whole-domain color scales are symmetric within each field; zoom maps use their own fixed symmetric scale to show the support region. Zoom bounds come from the prespecified 5-cell Chebyshev buffer around source support. These summaries show where and how the difference changes; they do not imply a balanced or causal structure.

For each state field, two coordinates are selected at 60 seconds: the maximum absolute paired difference on the original 613-value QC support, and the maximum over the full active domain. OFF and COUPLED values and their difference are then sampled at that same `(k,j,i)` for 0 through 600 seconds. The coordinates are selected from the same run being described, so these are selection-based diagnostics rather than independent validation or skill measures.

For QCLOUD, a horizontal translation scan compares the initial paired difference at each of the original 613 support locations with the later difference sampled at `(j+lag_dj, i+lag_di)`, holding native level and the baseline support fixed. It searches every integer lag from −5 through +5 cells in both axes (121 candidates), with no periodic wrap and no lag-specific cropping; the support is sufficiently interior for all candidates to retain 613 values. The saved zero-lag and best uncentered cosine, lag, aligned-difference RMS, and all candidate rows make the search auditable. Selecting the best lag on these same data is descriptive alignment only: it does not establish advection, a cause, or forecast skill. It cannot assign species conversion or numerical residuals.

The zero-lag QCLOUD cosines at 60, 120, and 600 seconds are −0.342633, −0.384720, and −0.367995. Best scan results are:

| Time | Best lag `(dj,di)` | Best uncentered cosine | Aligned difference RMS (kg/kg) | At search edge? |
|---|---:|---:|---:|---|
| 60 s | (4,2) | 0.236539 | 1.2450×10⁻⁴ | No |
| 120 s | (5,5) | 0.028734 | 1.2509×10⁻⁴ | Yes |
| 600 s | (5,0) | 0.469733 | 1.2085×10⁻⁴ | Yes |

The 120- and 600-second best lags reach the prespecified search edge, so the scan does not show an interior best alignment there. Even the 60-second improvement is only a same-data spatial alignment description; the scan does not identify physical motion or explain the residual pattern. Phase/species conversion is not causally decomposed by these comparisons, and a numerical residual is unavailable without complete timestep-resolved water tendencies and boundary fluxes.

The T60-selected pressure, geopotential, and W coordinates are recorded for both scopes in the JSON. Pressure selects `(10,15,134)` in both; geopotential selects `(38,16,133)` in both; W selects `(38,14,132)` on the original support and `(38,14,131)` on the full domain. At those unchanged coordinates, pressure and geopotential T60 differences are −360.63 Pa and −327.60 m² s⁻², then −9.22 Pa and −2.13 m² s⁻² at 600 seconds. W is −1.27 m s⁻¹ at 60 s and −0.076 m s⁻¹ at 600 s on the original support; full-domain selected W is −1.64 then −0.012 m s⁻¹. This evolution describes only those selected coordinates.

These fields are consistent with spatial redistribution and changes in phase/species composition during nonlinear model evolution. The diagnostics do not causally separate advection, redistribution, conversion, or other processes, and the cosine alone does not establish observation destruction or forecast skill. Falling or changing RMS is not a skill score.

## First-minute state and wind audit

Pressure (`P+PB`) and geopotential (`PH+PHB`, vertically centered to mass levels), plus mass-point U, V, and W, are compared at the same active-grid locations at saved times 0 and 60 seconds. Full-domain values are:

| Field | 0 s RMS | 0 s max abs (k,j,i) | 60 s RMS | 60 s max abs (k,j,i) |
|---|---:|---:|---:|---:|
| Pressure (Pa) | 0.1384 | 33.61 (0,15,134) | 1.5317 | 360.63 (10,15,134) |
| Geopotential (m² s⁻²) | 0.5980 | 116.05 (25,15,134) | 1.5130 | 327.60 (38,16,133) |
| U mass point (m s⁻¹) | 0.03666 | 6.354 (15,14,134) | 0.03528 | 6.806 (15,14,134) |
| V mass point (m s⁻¹) | 0.04265 | 6.177 (15,15,135) | 0.04101 | 6.809 (25,15,133) |
| W mass point (m s⁻¹) | 0 | 0 | 0.007714 | 1.643 (38,14,131) |

The actual staggered-face arrays are also compared at each time. Their U/V/W RMS values are 0.04415/0.04936/0 at 0 seconds and 0.04007/0.04466/0.007979 m s⁻¹ at 60 seconds. Face maxima and indices are in the JSON. All scopes, signed values at maxima, and maximum locations are retained there.

The audit also reads the actual staggered U, V, and W face arrays. They remain reported separately because their shapes differ from mass-point fields. Neither the mass-point nor face differences constitute a continuity closure. The saved evidence contains no authoritative observation array paired with a matching observation operator, so `H(X)-y` is unavailable and was not computed.

## Validation and limits

`python -m pytest -q tests/test_pr94_cloud_response.py` passes (6 tests). Running `python tools/pr94_cloud_response.py` produced the JSON and eleven standalone PNG plots. The analysis uses the closed runtime histories and source-composed support; it does not modify model physics or infer a causal decomposition. This is analysis evidence only, not a physical approval or operational validation.

## Three-arm HYDRO comparison (pending closed HYDRO run)

[`tools/pr94_hydro_response.py`](../tools/pr94_hydro_response.py) adds a separate, receipt-bound comparison for `HYDRO − OFF` and `COUPLED − HYDRO`. It requires complete 600-second receipts for all three arms, exactly 30 model timestamps, the same executed frozen-C4 executable (`20aaa605…e44be`), a common boundary input, and a HYDRO candidate-input binding whose comparison contract explicitly sets `current_generation: true`. It also compares the stored history timestamps and requires identical coordinates and hybrid-grid fields across all arms. The existing 613-value support, fixed clipped 2-cell and 5-cell buffers, full active domain, history reader, and direct array metrics are reused.

At each saved minute from 0 through 600 seconds, the report will retain both pairwise field comparisons for QC species, pressure, geopotential, and mass-point U/V/W. It separately verifies `COUPLED − OFF = (HYDRO − OFF) + (COUPLED − HYDRO)` pointwise on the actual arrays. RMS values are not added or used as a substitute for this identity. The comparison is descriptive: it does not establish causal attribution, forecast skill, observation fit, or a continuity closure.

The HYDRO analysis has not been run. It should be invoked only after the HYDRO run receipt is closed and passes the helper’s provenance gates. Focused tests cover rejection of wrong-generation inputs and a non-C4 executable, plus the pointwise identity check.
