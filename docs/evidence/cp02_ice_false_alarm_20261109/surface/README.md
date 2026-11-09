# Stored surface precipitation components

Four actual WRF history series (ORIGINAL, B1, PR153 conservative sedimentation, and first-ice velocity) were read at 12–18 UTC on 16 August 2026. For each of the frozen 3,688 RN1 points and each preceding one-hour window, `native/hourly_points.csv` reports separately remapped RAINC and RAINNC, the PR154 total, and the floating-point difference between their sum and that total. This is a description of stored fields; it does not identify a cause or assign precipitation to an individual physical process. The hourly histories do not resolve subhour timing.

The archived evaluator checks times, units, full-grid coordinates and valid fields, `BUCKET_MM=-1`, `PREC_ACC_DT=0`, and zero RAINSH. All I_RAINC, I_RAINNC, and I_RAINSH counters were absent; the disabled bucket contract applies. Full-grid component reset checks found no decreases beyond 1e-6 mm. History hashes are checked against the sealed historical and PR154 receipts and rechecked after extraction; see `native/receipt.json` for each input and check. The reference point mask and the native coordinate grid reproduce the frozen bilinear mapping.

`native/native_corners.npz` contains arrays keyed by case with shape `(3688, 7, 2, 4)` in point, cumulative UTC 12–18, component RAINC/RAINNC, and corner 00/10/01/11 order. It also stores point keys and bilinear `u`, `v`. To reproduce the output without external WRF histories, from the repository root run:

```
python tools/cp02_ice_surface_components.py --replay docs/evidence/cp02_ice_false_alarm_20261109/surface/native/native_corners.npz --output /tmp/surface-replay-new
```

The replay also uses the sealed PR154 point arrays in this repository. Cumulative native totals are formed at each corner, remapped, then differenced; this reproduces every PR154 total bit for bit. Separately remapped cumulative components are differenced and clamped according to the archived tolerance. Their sum differs from the prior total by at most **7.82e-14 mm**, due to floating-point operation order. Output publication refuses an existing path.

`native/group_means.csv` contains hourly means for four fixed cohorts. The lead-6 persistent/new/resolved groups have observation and B1 below 5 mm, classified by PR153 and first-ice crossing 5 mm (65/26/37 points). At lead 6 their mean RAINNC changed from 8.1681 to 7.5184, 3.7947 to 6.2119, and 6.0932 to 3.4706 mm respectively. RAINC means for these groups are 0.0002–0.0012 mm. The three lead-1 new false alarms use observation and B1 below 10 mm and first-ice at least 10 mm; their mean RAINNC was 9.9075, 11.4174, and 10.7054 mm for B1, PR153, and first-ice. These three are new relative to B1, not necessarily PR153. Cohort membership is frozen from forecast outcomes and is descriptive.

Validation: four focused unit tests cover bilinear values, temporal and clamp ordering, malformed and negative inputs, and reset rejection. A fresh replay produced byte-identical point and group CSVs; a second write to the native output failed with `FileExistsError` before modification. No WRF integration was performed.
