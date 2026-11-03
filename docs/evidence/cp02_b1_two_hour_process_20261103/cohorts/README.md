# B1 first two hours: paired rain cohorts

This read-only probe uses the base-838 / PR142 evidence export in `/var/tmp/cloudbal-recount-contract`. The selected forecast comparison is `ORIGINAL_B1_100` (OLD executable, B1 input) against `IMPROVED_BG_FIXED` (FIX executable, the same B1 input). The exact `wrfinput_d01` SHA-256 is `9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5` for both B1 arms. FIX histories come from `/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED`; OLD histories come from the current PR142 retained `ORIGINAL_B1_100` run. It keeps the original-input cross-check (`ORIGINAL` vs `FIXED_ORIGINAL_100`) as a separate pair. Every lead is its own one-hour accumulation window; +1 and +2 end at 13Z and 14Z.

## Pairwise score recount

For threshold `t`, observed event `O = RN1 >= t`, forecast event `F = P >= t`, hit `H = count(O and F)`, miss `M = count(O and not F)`, and false alarm `A = count(not O and F)`. `CSI = H / (H + M + A)`. `paired_scores.csv` recalculates these integer counts and CSI separately for each pair, lead, and threshold from the six canonical 3,688-point arrays. No lead, threshold, or input-pair averaging is performed. At +2, both executable changes reduce hits and increase false alarms on the original-input and B1-input contrasts; those are separate evidence pairs. At +2 through +6, low CSI worsens in 13/15 lead-threshold cells for each input pair, counted separately.

## Four selected locations

Selection is explicitly posthoc and diagnostic. At +2 on the B1-input pair, one point per group is selected by largest absolute one-hour `FIX − OLD` precipitation difference, with the smallest RN1 target flat index breaking ties:

1. Weak observed hit lost: `0.1 <= RN1 < 1 mm`, `OLD >= 0.1 mm`, `FIX < 0.1 mm`.
2. Weak new false alarm: `RN1 < 0.1 mm`, `OLD < 0.1 mm`, `0.1 <= FIX < 1 mm`.
3. Weak stable hit: `0.1 <= RN1 < 1 mm` and both forecasts in `[0.1,1) mm`.
4. Strong stable control: if any threshold-5 hit-gain exists, choose from it. This mask is empty (0), so the predeclared fallback selects a stable hit with `RN1, OLD, FIX >= 5 mm` by the same tie-break rule.

These locations are not a performance holdout and do not define a physics or initialization input mask. The prior unrestricted point picks are recorded in `selection.json` as a superseded selection attempt; the weak-observed groups are the final four.

## Native mapping and reconstruction

RN1 target coordinates are read from the stated analysis grid crop `[y=6:259,x=75:224]` in 0-based NumPy slicing, shape `(253,149)`. The four-point mapping calls the existing `cp02_precip_control_mapping.load_archived_mapper()` and its pinned `build_curvilinear_mapping()` function. It uses `XLAT/XLONG` from OLD B1's 12Z `wrfout` as the native geogrid/time-zero coordinate history. For each mapped point, `u,v` define the four bilinear weights `(1-u)(1-v), u(1-v), (1-u)v, uv`; `corners.csv` stores 0-based array indices and global one-based WRF `(j,i)` indices. The script verifies each sum is 1 within `1e-12` and that weighted native latitude/longitude reconstructs the RN1 target coordinates within `1e-6` degrees. It also remaps native cumulative `RAINC + RAINNC` with the same canonical function at 12Z/13Z/14Z, differences the one-hour windows, and compares all 16 OLD/FIX × point × +1/+2 predictions with the saved NPZ; they match exactly (maximum difference 0.0 mm). The four points have 16 unique corners.

`history_samples.csv` prepares the four-corner 39-level `AL`, `ALB`, and `QVAPOR` audit for OLD and FIX at 0/1/2 hours. `AL` and `ALB` are present in the shared B1 `wrfinput_d01` at hour 0 but are absent from the hourly `wrfout` histories; those cells are marked unavailable, not filled. `QVAPOR` is recorded where written. This is a paired state inventory only; it gives no process attribution.

## Files

- `selection.json`: frozen points, selection rule/fallback, input pair, source/runtime/mapping hashes.
- `corners.csv`: four WRF corners and weights per selected point.
- `selected_points.csv`: RN1, OLD, FIX values and +1/+2 event conditions.
- `paired_scores.csv`: independently recalculated counts and CSI for all 6 leads × 4 thresholds × 2 input pairs.
- `history_samples.csv`: available native state values and explicit absent-history cells.
- `native_precip_reconstruction.csv`: native-history hourly precipitation remap replay against the selected NPZ values.
- `recalc.py`: standalone deterministic recalc and mapping driver.
