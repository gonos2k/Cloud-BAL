# PR101: cloud thermodynamics and native upper-wind response

PR100's C2 OFF/HYDRO/COUPLED 640-second controls remain the baseline. This work adds diagnostics and one unchanged projected-input run; it does not change model physics, moments, precision, tolerances, diffusion, or wind inputs.

The additional PROJECTED run is now receipt-closed **COMPLETE**: 640 seconds, 32 calls, return code 0, no fatal or processing errors, and unchanged executable/input identities. Its receipt SHA-256 is `d0a7920687aecbef15b91f2641638918f00beea67de5fb2af6e5597175bc5da2`. The common stored history window is 0–600 seconds; selected microphysics trace states extend through 640 seconds. Endpoint and generic audit outcomes are reported separately in the projected-run evidence.

## Candidate and evidence boundaries

| Experiment | Model and input | Purpose |
|---|---|---|
| Existing three controls | C2, original OFF/HYDRO/COUPLED inputs | Reuse closed 640-second controls |
| PROJECTED | Same C2 executable, existing PR99 projected input P | Closed 640-second/32-call run |
| Liquid observer replay | Retained PR100/C1 first-call kernel and four retained first-call inputs | Explain actual liquid adjustment; require unchanged returned fields |
| Upper-wind capture | C2 overlay with additive call-boundary diagnostics, HYDRO and P | Reproduce selected native diffusion operands and output |

The retained C1 replay, diagnostic overlay, and unchanged C2 forecast are separate evidence cohorts. A diagnostic replay cannot establish forecast completion. The PROJECTED result cannot establish observational skill or energy closure.

The closed PROJECTED audit passes the declared strict source endpoints and active/inactive ice policy. Generic Q/N/B conversion remains **FAIL in 171 of 192 state records**. The selected sedimentation ledger also retains an intermediate valid-to-invalid transition at step 24; subsequent completed endpoint checks pass. These findings are preserved in the [closed response](evidence/pr101_projected_c2_20261023/closed_response.json), rather than collapsed into one PASS label.

## Completion requirements

- Bind the closed PROJECTED receipt to the same executable, boundary, namelist, and existing input P; compare common stored times against the three closed controls.
- Record source saturation, the thermodynamic state used to produce heat capacity and latent heat, unbounded demand, bounded transfer, and actual stored changes. Keep Python transcendental comparisons advisory; the captured Fortran values are authoritative.
- Capture the original upper U/V diffusion calls, including their stencil, hybrid carrier, map metrics, coefficients, options, timestep, and RK stage. Verify the original source routine against captured post-call bits before interpreting field/coefficient contrasts.
- Check the frozen PR100 final per-column T1 residuals once with an independent exact sum. Preserve numerical removal and physical conservation as separate conclusions.
- Run stand-alone replays through the common hash-bound fresh-directory launcher. Preserve unsuccessful attempts and validate executable, input, output, and completion identities.

## Scientific disposition

Physical approval remains **OPEN** (`FAIL_OPEN` in integration records); observation skill remains **NOT_EVALUATED**. This batch does not select a new thermodynamic analysis or upper-wind correction. Source evidence must first distinguish necessary evaporation from an inconsistent incoming analysis, and upper-wind curvature from changes in diffusion coefficients and carrier.

The liquid observer has completed all four retained first-call replays with the returned 17 fields and XLAND byte-identical to their respective references. At the strongest general-branch COUPLED−OFF contrast, OFF enters the adjustment at liquid RH 0.8203 and evaporates; COUPLED enters at RH 1.0148 and condenses. The source temperature and vapor state explain the opposite transfer directions at this cell. This supports interpreting the earlier negative QC-pattern cosine through absolute changes in both arms. It does not establish that all cloud adjustment is desirable or that the original observations are retained.

The independent exact sum of the frozen binary64 T1 remainder arrays reproduces PR100's signed and L1 totals for all three controls. The maximum remaining column residual stays `5.3398584443087316e-8 kg`. No residual was reassigned or corrected, and cutoff remains an actual numerical removal.

The paired upper-wind captures reproduce the exact original Fortran routine's six post-call REAL32 values in each arm. Captured coefficients, carrier, and map metrics are identical in HYDRO and P at these two faces. At k39, the increment `b = P−HYDRO` has the following grid-index second differences:

| Face | Center increment (m/s) | `b_e − 2b_c + b_w` (m/s) | `b_n − 2b_c + b_s` (m/s) |
|---|---:|---:|---:|
| U (136,16) | +7.84588 | −9.87201 | −14.01931 |
| V (135,17) | −7.22398 | +14.92102 | +8.17073 |

The same stencil contrasts occur to displayed precision at k37 and k38. These are grid-index curvature diagnostics, without metric/spacing normalization; they are not acceleration or energy. The [captured-stencil values](evidence/pr101_cloud_thermo_native_20261023/upper_grid_index_curvature.json) identify a local peak/trough in the added wind. The actual weighted diffusion replay attributes the local difference to that field stencil under unchanged coefficients. This narrows the next candidate design to the wind increment's spatial structure within the existing mass constraint. It does not justify switching diffusion off or clipping these faces.

Native source-array norms are not energy or acceleration norms. The local KDM6 T1 measure is not the full native hybrid host water or energy budget. No missing term is filled from another time or inferred from the endpoint residual.

## Matched C2 history response

These are unweighted spatial RMS values of each arm minus OFF on the fixed 613-point support, using actual common saved times. OFF is a reference, not truth. U/V/W in the history reader are destaggered to mass points; the upper-wind source replay instead uses the original staggered face operands.

| Time (s) | Field and unit | HYDRO−OFF | COUPLED−OFF | PROJECTED−OFF |
|---:|---|---:|---:|---:|
| 60 | Pressure (Pa) | 68.260 | 78.194 | 72.637 |
| 60 | Geopotential (m²/s²) | 42.788 | 72.734 | 33.572 |
| 60 | W (m/s) | 0.24497 | 0.34710 | 0.23909 |
| 60 | QC (kg/kg dry) | 4.24529e-5 | 5.05435e-5 | 4.87002e-5 |
| 600 | Pressure (Pa) | 4.241 | 5.902 | 5.702 |
| 600 | Geopotential (m²/s²) | 4.439 | 11.059 | 11.106 |
| 600 | W (m/s) | 0.11202 | 0.22599 | 0.21939 |
| 600 | QC (kg/kg dry) | 2.28606e-5 | 3.29452e-5 | 3.27128e-5 |

Projection reduces the 60-second geopotential and W response relative to the original COUPLED input. By 600 seconds the four reported projected responses remain above HYDRO; geopotential is also slightly larger than the original COUPLED value. Thus the initial mass-response improvement is useful evidence, but these data do not establish a general reduction of adjustment or better forecast skill.

The 600-second QC-pattern cosine is −0.38319 for PROJECTED, −0.36799 for COUPLED, and −0.09225 for HYDRO. These uncentered fixed-region alignments must be interpreted with the measured absolute liquid transfers, rather than equated with destruction of observed cloud. The [receipt-bound RMS reducer and results](evidence/pr101_cloud_thermo_native_20261023/control_response_rms.json) also include the predeclared five-cell buffer, additional fields, and intermediate times.

## Detailed records

- [Projected C2 run](PR101_PROJECTED_C2_20261023.md)
- [Cloud thermodynamics](PR101_CLOUD_THERMO_20261023.md)
- [Upper-wind source replay](PR101_UPPER_WIND_20261023.md)
- [Frozen T1 independent sum](PR101_T1_SUM_20261023.md)

The final source checks pass [96 focused Python tests](evidence/pr101_cloud_thermo_native_20261023/validation/closed_focused_validation.json). Pinned Intel source replays, native runtime receipts, and independent team reviews are separate evidence. The derived graph publication is recorded after the reviewed source commit; graph freshness does not establish runtime or scientific validity.
