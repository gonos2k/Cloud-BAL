# P01 hour-two timing: RN1_10942

The portable capture covers 180 calls, actual steps 181–360, at three calls per minute. At native model level k=12, the weighted FIX return is no greater than OLD for the first 149 calls (181–329) and greater for steps 330–360 (31 calls). A comparison of full-hour means hides that ordering.

| Minutes in hour 2 | Actual calls | Surface baseline step | Mean return QR k=12 OLD / FIX (mg kg⁻¹) | RAINNC increase OLD / FIX (mm) |
|---|---:|---:|---:|---:|
| 40–50 | 301–330 | 300 | 82.7982 / 41.5773 | 0.1481668 / 0.0225705 |
| 50–60 | 331–360 | 330 | 72.9392 / 200.0177 | 0.1756597 / 0.0498594 |

Each bin includes 30 returns. The cumulative surface difference uses the immediately preceding call as its lower boundary; the first bin uses retained step 180. Step 330 is included in the earlier bin even though it begins the run of FIX>OLD returns. The hourly non-convective surface totals and returns are different quantities. RAINNC excludes RAINC.

The figure shows the actual four original native corners as faint curves and their fixed weighted point as bold curves. Levels are model indices, not geometric heights. Per-call native corner QR and cumulative-rain increments, all bins, source hashes, corner coordinates and weights are in the adjoining CSVs and receipt. The pinned input arrays were checked for identical coordinates, finite values, expected units and exact interpolation to the captured point. The pattern is descriptive for this one point and pair of simulations; it does not establish a vertical mass budget, causal attribution, or general forecast skill. No density or height was assumed.

Reproduce from the repository root with `python tools/cp02_sedimentation_focus.py` and `pytest -q tests/test_cp02_sedimentation_focus.py`. The figure uses the same SHA-pinned Nanum Gothic font as the previous native figures. The receipt records input and output hashes and library versions.
