# PR92 science response: C14 fields and QC vertical support

## C14 matched history response

The two C14 240-second runs completed 12 model steps. This response uses same-time history records at 0, 60, 120, 180, and 240 seconds, with each OFF/COUPLED history hash bound to its run receipt. It reports native `P+PB` at mass levels, `PH+PHB` at interfaces, and `W` at vertical faces. The fields are subtracted at the same grid location and level; no remapping is applied.

The fixed support is the 27 mass-grid columns where any native water tracer differs between arms at T0. The summary separates the whole grid, the interior with the outer one-cell boundary ring removed, that boundary ring, fixed T0 support, and the one-cell neighborhood around the fixed support. These are response scopes; the 27-column mask does not represent an observational or QC footprint.

| Elapsed | Field | Whole-grid mean signed Δ | Whole-grid max absolute Δ | Fixed-support max absolute Δ | Neighbor max absolute Δ |
|---:|---|---:|---:|---:|---:|
| 0 s | Pressure (Pa) | -0.00112 | 33.609 | 33.609 | 0.078 |
| 0 s | Geopotential (m² s⁻²) | -0.00498 | 116.047 | 116.047 | 0.855 |
| 0 s | W (m s⁻¹) | 0 | 0 | 0 | 0 |
| 60 s | Pressure (Pa) | -0.00418 | 360.633 | 360.633 | 114.906 |
| 60 s | Geopotential (m² s⁻²) | 0.00414 | 332.884 | 332.884 | 124.292 |
| 60 s | W (m s⁻¹) | 0.000025 | 1.729 | 1.617 | 1.729 |
| 120 s | Pressure (Pa) | -0.00429 | 157.094 | 157.094 | 56.186 |
| 120 s | Geopotential (m² s⁻²) | 0.01045 | 276.701 | 276.701 | 125.939 |
| 120 s | W (m s⁻¹) | -0.000046 | 2.219 | 2.219 | 2.101 |
| 180 s | Pressure (Pa) | 0.01098 | 77.102 | 77.102 | 62.258 |
| 180 s | Geopotential (m² s⁻²) | -0.00607 | 102.143 | 92.284 | 92.609 |
| 180 s | W (m s⁻¹) | -0.000004 | 1.405 | 1.405 | 0.525 |
| 240 s | Pressure (Pa) | -0.00411 | 74.961 | 74.961 | 28.383 |
| 240 s | Geopotential (m² s⁻²) | 0.00732 | 88.573 | 71.441 | 88.573 |
| 240 s | W (m s⁻¹) | 0.000042 | 1.464 | 1.464 | 0.565 |

The table above uses elapsed-time labels from the receipt-bound C14 archive; full five-time metrics and explicit scope counts are in [c14_field_scopes.json](evidence/pr92_science_20261020/c14_field_scopes.json). The 27-column support and its neighbor scope are interior columns. The whole-grid maxima extend beyond the original support by 60 seconds. C14 uses distinct OFF and COUPLED frozen analysis inputs, so these matched differences describe the C14 analysis-arm response, not a pure-model causal effect or observational skill.

## Same-location tracks and stored-level separation

[Response maps and fixed-location tracks](evidence/pr92_science_20261020/response_maps/README.md) retain each peak’s native `(i,j,k)` through all five times. At `(136,17,11)`, the pressure difference is −28.1875, −360.6328125, −84.6171875, −14.0078125, and −2.53125 Pa. A different location, `(136,18,1)`, has −74.9609375 Pa at 240 seconds and controls that time’s maximum. Thus different-time maxima are not one point’s time series.

The 60/120-second W maxima occur at the highest stored interface. Excluding the lowest/highest interfaces gives maxima 1.5579816/2.0035478 m s⁻¹; the interior fixed point `(136,17,14)` reaches +1.4636528 m s⁻¹ at 240 seconds. This separates stored-level responses without diagnosing a boundary error or force/continuity closure. Maps use the signed value at each column’s maximum absolute native-level difference; the selected level can change. The fixed geographic view remains a descriptive view of T0 response support, not an observation footprint.

## C16 partial-run bridge

The paired C16 runs requested 600 seconds but closed `INCOMPLETE` after 14 completed steps (280 seconds); T15 has committed RK1/RK2 states, with no RK3 or POST15 state. Each complete C16 WRF history file is byte-identical to its same-arm C14 history file, covering the five records at 0, 60, 120, 180, and 240 seconds. The existing same-position C14 maps therefore describe the identical observed C16 fields at those times. This identity does not extend the history through 260 or 280 seconds, and C16 adds no new mapped field values.

C16's own receipt-bound, area-weighted half-L1 request activity over completed steps 1–14 (20–280 seconds) gives these COUPLED/OFF ratios:

| Group | Proposed | Applied | Deferred |
|---|---:|---:|---:|
| NG | 1.000046 | 0.999924 | 1.000631 |
| AUT | 0.999894 | 0.999792 | 0.999926 |
| G | 0.999769 | 1.000046 | 0.999704 |

Within each C16 arm, the deferred share of proposed activity is:

| Group | OFF deferred / proposed | COUPLED deferred / proposed |
|---|---:|---:|
| NG | 17.16% | 17.17% |
| AUT | 75.53% | 75.53% |
| G | 81.16% | 81.16% |

The activity values are same-run C16 cold-process diagnostics, weighted with native column mass and map area. They are request-activity measures, not realized transport, precipitation, or an endpoint inventory budget. The [C16 partial activity output](evidence/pr92_source_store_20261020/c16/closed_runtime_20261020/area_activity_through_step14.json), [closed-run audit](evidence/pr92_source_store_20261020/c16/closed_runtime_20261020/closed_runtime_summary.json), and [C16/C14 history identity evidence](evidence/pr92_source_store_20261020/c16/closed_runtime_20261020/history_exact_identity_c14.json) preserve the source and receipt bindings. The exact source-coefficient audit remains FAIL ([OFF](evidence/pr92_source_store_20261020/c16/closed_runtime_20261020/off_closed_runtime_summary.json), [COUPLED](evidence/pr92_source_store_20261020/c16/closed_runtime_20261020/coupled_closed_runtime_summary.json)); the separate declared inactive-ice policy split has zero active outliers ([OFF](evidence/pr92_source_store_20261020/c16/closed_runtime_20261020/off_ice_policy_split.json), [COUPLED](evidence/pr92_source_store_20261020/c16/closed_runtime_20261020/coupled_ice_policy_split.json)).

## C17 partial-run bridge

C17 requested 600 seconds and closed `INCOMPLETE` after 21 completed steps (420 seconds). The five shared WRF history records at 0, 60, 120, 180, and 240 seconds are bit-identical to C14, for `P`, `PB`, `PH`, `PHB`, and `W` in both arms. The existing C14 same-position maps therefore describe those common C17 history values. C17's history adds records beyond 240 seconds, so this identity does not validate mapped C17 fields at 300–420 seconds. The exact per-variable comparison and history hashes are in [the C17/C14 common-history check](evidence/pr92_source_store_20261020/c17/closed_runtime_20261020/history_common_c14.json).

The C17 receipt-bound, area-weighted half-L1 request activity through its 21 completed steps (20–420 seconds) gives these COUPLED/OFF ratios:

| Group | Proposed | Applied | Deferred |
|---|---:|---:|---:|
| NG | 1.000069 | 0.999917 | 1.000808 |
| AUT | 1.000012 | 1.000157 | 0.999948 |
| G | 0.999612 | 0.999995 | 0.999469 |

Within each C17 arm, the deferred share of proposed activity is:

| Group | OFF deferred / proposed | COUPLED deferred / proposed |
|---|---:|---:|
| NG | 17.04% | 17.05% |
| AUT | 69.48% | 69.48% |
| G | 72.72% | 72.71% |

Activity is a cold-process request measure weighted with native column mass and map area, not realized transport, precipitation, or an endpoint inventory budget. Both arms completed POST_KDM6 at 300, 320, and 420 seconds; neither reached 600 seconds. The strict exact source-coefficient audit remains FAIL in both arms (18 failures and 3 passes among the completed state checks). The separately declared inactive-ice policy split passes with 126 states per arm and zero active outliers; this does not replace the generic audit result. These outcomes and the partial activity totals are preserved in the [OFF audit](evidence/pr92_source_store_20261020/c17/closed_runtime_20261020/off_closed_runtime_summary.json), [COUPLED audit](evidence/pr92_source_store_20261020/c17/closed_runtime_20261020/coupled_closed_runtime_summary.json), [ice-policy splits](evidence/pr92_source_store_20261020/c17/closed_runtime_20261020/off_ice_policy_split.json), and [activity output](evidence/pr92_source_store_20261020/c17/closed_runtime_20261020/area_activity_through_step21.json).

The 11 committed code-5 events per arm, including the committed RK1/RK2 rows of incomplete T22, can also be bounded in physical units. The compiled operator forms `newcarrier = C1H × (MU + MUB) + C2H`; the same-run fields show dimensionless C1H and pressure-valued MU, MUB, and C2H, so the carrier is pressure-valued. Source code makes each event's signed Q and B change negative, while the retained ledger sums carrier-weighted deltas by RK row and omits event levels and columns. Using the C17 history's static, arm-identical `MAPFAC_MX/MY` and `DNW`, with native cell area `DX × DY / (MAPFAC_MX × MAPFAC_MY)`, the global factor extrema `−DNW[k] × area / g` bound the cumulative code-5 adjustment in both arms to −2.05×10⁻³²…−2.27×10⁻³³ kg for Q and −2.43×10⁻³⁵…−2.70×10⁻³⁶ m³ for B. The bounds span all native layers and grid cells because event coordinates were not retained. They cover storage adjustments only; they are not an RK transport sum or endpoint water-loss/conservation estimate. The history geometry, field hashes, source pins, factors, and calculation are in [the physical-weighting audit](evidence/pr92_source_store_20261020/c17/closed_runtime_20261020/bulk_event_physical_weighting.json). The earlier DX×DY-only calculation is retained as explicitly non-authoritative evidence alongside it.

At T15, committed RK1, RK2, and RK3 endpoint records are present; the emitted local mixture trial values match the same-coordinate committed RK1 values (12/12 OFF and 22/22 COUPLED). T15 RK3 and POST_KDM6 are distinct states: only 2 of 24 selected QG/BG values match bitwise in each arm. At T22, only RK1 and RK2 endpoint records were captured; RK3 and POST_KDM6 are absent. These endpoint checks are limited to the 12 fixed target locations, and trial diagnostics are not additional committed stages. See the [OFF endpoint record](evidence/pr92_source_store_20261020/c17/closed_runtime_20261020/off_t15_t22_endpoints.json), [COUPLED endpoint record](evidence/pr92_source_store_20261020/c17/closed_runtime_20261020/coupled_t15_t22_endpoints.json), and [committed bulk event counts](evidence/pr92_source_store_20261020/c17/closed_runtime_20261020/bulk_committed_event_counts.json). C18 is summarized below; it also did not reach 600 seconds.

## C18 partial-run bridge

C18 requested 600 seconds and both arms closed `INCOMPLETE` with return code 128 after 23 completed steps (460 seconds). The trace contains only PRE_RK, RK1/RK2/RK3, and PRE_KDM6 at T24; there is no POST_KDM6 for T24 and no completed 480-second state. The run therefore supports no 600-second endpoint claim. Both arms used the same receipt-bound executable (`32a324…`) and module source (`f88708…`).

Each completed arm has 138 states (23 × 6). The generic exact source-coefficient audit remains **FAIL**: 20 completed timesteps fail the strict audit in each arm. A separately declared inactive-ice split passes for its narrower QI/NI outlier policy: 0 active outliers and 0 strict state failures among those 138 completed states; inactive outlier counts are 1,450 OFF and 1,280 COUPLED. This result does not establish that all cloud, rain, snow, or graupel source checks pass, and does not replace the generic audit. The closed summaries and source-bound split records are available for [OFF](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/off_closed_runtime_summary.json) and [COUPLED](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/coupled_closed_runtime_summary.json).

C18 and C17 same-arm history files are byte-identical through the eight records at 0–420 seconds, including `P`, `PB`, `PH`, `PHB`, and `W`. The existing C14 maps therefore also describe these observed C18 values through 240 seconds, while the C18/C17 history identity alone does not extend those maps to 300–420 seconds. Per-variable hashes and record comparisons are in the [C18/C17 history check](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/history_common_c17.json). The first 14 complete timesteps also match byte-for-byte in the stage trace: 113 records per arm, bound to the C17 and C18 trace hashes ([prefix check](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/trace_prefix_c17_first14.json)).

C18's receipt-bound area-weighted half-L1 request activity, summed over its own completed steps 1–23 (20–460 seconds), is:

| Group | OFF proposed (T kg) | OFF applied (T kg) | OFF deferred | COUPLED proposed (T kg) | COUPLED applied (T kg) | COUPLED deferred | COUPLED/OFF proposed |
|---|---:|---:|---:|---:|---:|---:|---:|
| NG | 0.540729 | 0.447189 | 17.30% | 0.540773 | 0.447156 | 17.31% | 1.000082 |
| AUT | 0.106938 | 0.033151 | 69.00% | 0.106941 | 0.033156 | 69.00% | 1.000020 |
| G | 1.118923 | 0.319816 | 71.42% | 1.118502 | 0.319795 | 71.41% | 0.999623 |

These are request activity measures weighted by native column mass and map area, not realized transport, precipitation, or endpoint inventory changes. Per-arm activity artifacts and their totals are [OFF](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/off_area_activity_through_step23.json), [COUPLED](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/coupled_area_activity_through_step23.json), and [summed totals](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/activity_totals_steps1_23.json). At T22 point `(2,252,14)`, the actual committed RK3 and PRE_KDM6 QG values are 900 REAL32 subnormal units and BG is one; POST_KDM6 is zero for both. This is a fixed point check, not a domain endpoint summary ([OFF](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/off_t22_p4_endpoint.json), [COUPLED](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/coupled_t22_p4_endpoint.json)).

## QC vertical influence

The actual PR83 initialization path is bound to the archived met_em input (SHA-256 `5c896…`), its real.exe receipt, and the PR84 moment-prior transaction. PR84 changes only moment variables; QCLOUD, PB, MU, MUB, P_TOP, C3H, and C4H remain bit-identical through the C14 OFF input. The input has direct QV, `FLAG_QC=1`, and no CL/SPECCLDL correction. The selected real source is `/var/tmp/pr61_ccn_origin_20261006/hostcopy/dyn_em/module_initialize_real.F`.

The QC call uses `vert_interp(..., var_type='Q')` with `linear_interp=1` and the actual EM Registry default `interp_type=2` (log pressure). The pressure path is `sfcprs2` → direct-QV `integ_moist` → `p_dts` → half-level `p_dry`, followed by 500-Pa close-level selection and the source `lagrange_interp`. The target pressure at this call is subsequently overwritten; final wrfinput PB is not a substitute for it. `lagrange_order` is not the order argument passed by this QC call.

A pinned-Intel REAL32 source-form replay of this path reproduces all **16 selected columns × 39 levels = 624 QCLOUD values bit-for-bit**, with identical O0/O2 output. The preserved inputs, exact interpolation procedure, driver, outputs, and hashes are in [the replay manifest](evidence/pr92_science_20261020/qc_r32_fortran_probe/manifest.json). Earlier linear-pressure and promoted-precision trials are retained as rejected/preliminary evidence. This is selected-column source-form validation, not execution of the complete real.exe initializer or a domain-wide influence map.

Horizontal attribution remains open. The PR91 component replay matches 288/288 values in its own met_em product (`e635b4…`), but that product differs from the actual PR83 initializer input: 131/288 corresponding QC values differ. Grid dimensions, projection, lat/lon, pressure and relevant surface fields agree, so its geometric stencil transfers; source selection does not. The component manifest correctly binds LAPS SHA `d73b33…`; a derived JSON mislabeled unrelated PR81 `joint_candidate.nc` SHA `135c23…` as LAPS. [The additive lineage/provenance result](evidence/pr92_science_20261020/qc_vertical_support_pr83_trial.json) records this correction without rewriting PR91 artifacts.

Thus the actual selected-column QC vertical transfer is validated. The original pressure-analysis support → actual operational horizontal product → complete native footprint is not yet closed. Other variables' masks, fallback behavior, wind rotation and staggering are outside this QC result.

## Evidence and limitations

- [C14 field-scope output](evidence/pr92_science_20261020/c14_field_scopes.json) is generated by [pr92_c14_field_scopes.py](../tools/pr92_c14_field_scopes.py), which verifies receipt and history hashes and exact static geometry before calculating deltas.
- [Source bindings](evidence/pr92_science_20261020/source_bindings.json) pin the C14 receipts, real.exe source, met_em input, and archived horizontal QC replay.
- [QC vertical source lookup](../docs/evidence/pr91_science_sources_20261020/support_operator_lookup.json) records the original horizontal replay; [the PR83 lineage trial](evidence/pr92_science_20261020/qc_vertical_support_pr83_trial.json) records the source-bound vertical reconstruction and its validation limits.
- The C14 pair closed at 240 seconds. C16 closed incomplete at 280 seconds with history through 240 seconds; C17 and C18 closed incomplete at 420 seconds of history; C18 completed model states through 460 seconds. The field maps remain limited to the five shared, receipt-bound C14/C16/C17/C18-identical times described above. This response gives no physical approval, observation score, model-only causal attribution, budget closure, or precipitation conclusion.

## Current cold-process attribution limit

[The C14 alpha source audit](evidence/pr92_science_20261020/c14_alpha_constraint_source_audit.md) distinguishes a full-proposal first-failed predicate from the predicate limiting the accepted fraction. Existing compact C14 summaries quantify current area-weighted activity, but omit the selected local state and competing predicate outcomes at that fraction; they cannot identify the unique active constraint. This does not turn the earlier v17 full-proposal reasons into current C14 process attribution. A bounded future probe can compare the accepted REAL32 alpha and its next representable neighbor at fixed NG/AUT/G states, retaining the separate composite gamma. No physical limiter or KDM6 rate was changed for this source audit.
