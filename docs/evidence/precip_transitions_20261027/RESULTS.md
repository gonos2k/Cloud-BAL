# CP02 paired precipitation transitions

Diagnostics use the six retained hourly arrays (`hour_13_arrays.npz` through `hour_18_arrays.npz`) from `precip_hourly_20261027/rn1_recovery/`. Each hour has the same 3,688 flattened grid indices and coordinates. The analysis compares OFF, HYDRO, and LIQUID with the reference at inclusive thresholds 0.1, 0.5, 1, 2.5, 5, and 10 mm. Per-arm bias, MAE, RMSE, rain fraction (amount ≥0.1 mm), conditional rain intensity quantiles, conditional mean, and maximum are unweighted point summaries.

At 13 UTC and ≥5 mm, OFF has 74 hits; HYDRO and LIQUID each have 55. Each arm loses 19 OFF hits, and the union of lost-hit locations contains 20 unique points. Both arms share 55 of the OFF hits, so this focused comparison has no hit gains at that threshold. The CSV lists those exact points with flattened indices, coordinates, all three forecasts, reference amounts, and hit/loss flags; the focus map labels each 1-based focus rank for lookup; the CSV separately preserves the original flattened grid index.

At 13 UTC, arm bias / MAE / RMSE are 0.010 / 1.114 / 4.062 mm (OFF), −0.062 / 1.133 / 4.110 mm (HYDRO), and −0.069 / 1.127 / 4.085 mm (LIQUID). Reference rain fraction is 43.2% (1,593 points) versus 18.9% (OFF), 18.1% (HYDRO), and 18.1% (LIQUID). Full hourly values and intensity quantiles are in `transitions/continuous_metrics.csv`.

Scope is the retained common paired-point sample, with no area weighting or extrapolation beyond those points. No missing or uncovered locations are zero-filled. Sparse-point FSS and physical attribution are not claimed. This is an offline diagnostic of retained arrays, not a model rerun or independent validation. Existing hourly score evidence is unchanged.

## Artifacts

- `transitions/threshold_counts_and_transitions.csv` — per-arm contingency counts and OFF-to-arm hit/false-alarm gains and losses.
- `transitions/continuous_metrics.csv` — per-hour continuous and rain-intensity summaries for all arms and the reference.
- `transitions/hour_13_ge5mm_off_hit_lost_union.csv` — exact 20-point focused union, with `focus_rank` values matching labels in the map.
- `transitions/threshold_5mm_hit_transitions.png` — six-hour hit-change maps with longitude aspect correction.
- `transitions/hour_13_ge5mm_lost_hit_focus.png` — separate HYDRO and LIQUID focus panels with ranked point labels.
- `transitions/rain_point_distributions.png` and `transitions/hourly_threshold_5mm_transitions.png` — hourly rain amounts and 5 mm hit/false-alarm series.
- `transitions/summary.json` — evaluated scope and focused counts.
