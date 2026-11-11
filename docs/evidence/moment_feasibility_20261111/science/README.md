# B1 analytical fixed-mass feasibility recount

This read-only recount uses the pinned producer `wrfinput_d01` and the unchanged policy from `physical_moment_handoff_20261110/native/actual_real/policy.json`. It computes density as `float32(1 / float32(AL + ALB))` and performs the interval arithmetic in float64. For each positive mass with the policy's zero threshold, it tests `[q / upper, min(q / lower, cap / density)]` for emptiness. Hashes identify C-order uint8 masks in z,y,x order; first locations are 1-based i,j,k in the completion loop's k,j,i traversal order.

The fixed 50 µm ice mask counts where that single prior exceeds the cap. Its 106,128 cells are not the number of empty intervals: 1,362 intersect the empty interval mask, and 104,766 have a nonempty analytical interval. The first fixed-prior exceedance is (1,228,13), while the first empty ice interval is (209,94,17). The independent ice mass-concentration maximum is 0.003299869047 kg/m³ against the analytical ice limit 0.002098274639 kg/m³.

File density is a proxy and these are ideal analytical bounds, not a claim about first-use runtime density or whether a REAL32 stored value can pass at a rounding boundary. No WRF model was run and no NetCDF file was modified.

Reproduce with Python, NumPy, and netCDF4:

```sh
python3 docs/evidence/moment_feasibility_20261111/science/feasibility_recount.py \
  /path/to/pinned/wrfinput_d01 \
  docs/evidence/physical_moment_handoff_20261110/native/actual_real/policy.json \
  /new/path/feasibility_recount.json
```

The output records the input, policy, and script hashes and checks the independently established fixed-prior count. The original input path is environment-specific and is recorded in the JSON.
