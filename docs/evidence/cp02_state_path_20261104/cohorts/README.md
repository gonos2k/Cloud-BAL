# CP02 state-path cohorts and complete-array recount

This package extends the frozen P01–P04 diagnostic locations with four requested threshold-5 false-alarm transitions. It reuses the already verified B1 two-hour trace and paired precipitation arrays. It does not make a new model-run claim or evaluate a new physics candidate.

## Findings

- The OLD threshold-5 contingency at +2 h changes from 59 hits / 159 misses / 107 false alarms to FIX 59 / 159 / 105. The three removed false alarms are RN1 sample indices 582, 899, and 1870; index 1772 is the new FIX false alarm. These points are `FA01`–`FA04` in that order.
- All twelve lead/threshold rows in `paired_scores.csv` use the entire 3,688-point common-valid RN1 sample, with no averaging. It includes 0.1, 0.5, and 1 mm at +1/+2 h, plus 2.5, 5, and 10 mm at both leads. Each row gives OLD/FIX hits, misses, false alarms, CSI, and all paired transitions among the hits and false alarms.
- P01 has 190 OLD events where raw `prevp` is negative zero and the final process rate is negative. Matching each event to its complete cell-step key shows numeric equality of `q` and `T` from PRE_UPDATE to POST_STEP for all 190; the compact table does not carry state raw-word columns. `process_prev * dtcld` ranges up to 7.38e-12 in magnitude; the maximum is 0.0159 ULP of the REAL32 `q_pre`, and 1.13e-9 of `|q_pre|`. The summed local `qr_post - qr_pre` is -9.4374e-11; this is hydrometeor-state removal in the KDM6 checkpoint, not accumulated precipitation.
- P02 at k=8 has 15 raw-zero events. Their unweighted `sum(process_prev * dtcld)` is -5.4264e-5 across mapped corners; the bilinear-weighted sum is -1.36164e-5. The exact event keys also join to the SHA-pinned OLD run1 `LATENT_INPUT` records. For all 15 event keys, the total logged latent term `-REAL32(REAL32(xlwork2/cpm)*dtcld)` equals the isolated PREVP term from the source-ordered `xl_component=REAL32(REAL32(-xl)*prevp)` equation numerically after REAL32 rounding. Both bilinear-weighted sums are -0.0328197 K (unweighted corner sum -0.130793 K). The summary retains the initial exploratory sign error and its corrected formula. This is the selected zero-event subset only, not a total hour/column temperature integral. The grouped values by forecast hour and matching state changes are in `zero_rate_state_path_summary.json` and the event rows are in `zero_rate_state_paths.csv`.

For additional context, P01's preserved paired precip values are in `selected_points.csv`: OLD/FIX are 6.3874e-5 / 9.2648e-8 mm at +1 h and 0.33377 / 0.08058 mm at +2 h. These forecast precip values are reported separately from the local `qr` state changes above.

## Native instrumentation coordinates

`native_instrumentation_coordinates.json` contains the original P01–P04 and new FA01–FA04 locations with canonical RN1 sample/flat indices, target coordinates, mapping provenance, and the 32 unique global WRF cells. `point_corners.csv` gives the four exact WRF bilinear corners and weights for each point (32 rows). Coordinates use the existing `cp02_precip_control_mapping.py` loader and pinned archived mapper, with the original WRF history grid and analysis coordinates. The bilinear coordinate reconstruction residual is recorded in both files.

The FA number is the canonical RN1 sample-array index; `target_flat_index_yx` separately records the corresponding spatial flat index. This distinction is deliberate.

## Reproduction and validation

Run from the Cloud-BAL root:

```bash
python tools/cp02_state_path_cohorts.py
pytest -q tests/test_cp02_state_path_cohorts.py
```

The script checks array keys, shapes, finite values, unique sample flat indices, frozen OLD point IDs, FA transition membership, and exact coordinate reconstruction. It joins the archived zero-rate events to cell-step rows on the full call/grid key and rejects missing or duplicate state records. `receipt.json` pins all source arrays, trace tables, old point selection, coordinate assets, mapping implementations, script hash, and produced artifacts.

Inputs outside the repository are explicitly listed in `receipt.json`; rerunning requires those pinned source files to remain available. The package is a focused diagnostic and does not establish water or energy budget closure, model-wide causality, or a physics improvement.
