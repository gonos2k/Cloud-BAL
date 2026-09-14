# CP02 six-hour precipitation sensitivity verification

Status: SIX_HOUR_RUNS_AND_LAND_ONLY_CSI_COMPLETE. This experiment extends the retained OFF/HYDRO/LIQUID initial states from 2026-08-16 12 UTC through 18 UTC. It evaluates initialization sensitivity, not a newly implemented physical cloud-omega operator, and does not close CP02.

## Fixed experiment

- Preserve each retained initial state, the pinned native executable, 8 MPI ranks per case, one OpenMP thread, 20-second timestep, and all physical/dynamical settings.
- Output at initialization and every hour through lead 6. Compare adjacent-hour differences of `RAINC + RAINNC` (total surface precipitation, liquid-water equivalent) with RN1 at 13–18 UTC. Check `RAINSH` separately; do not add snow/graupel subset counters again.
- Use the same lateral boundary for all cases. The extended boundary uses the original 2026081606 KLBG cycle; its 12–15 UTC values are exactly preserved. At 18 UTC, absent LAPS QV is replaced by the existing real.exe conversion of background RH/temperature. This boundary provenance is part of the experiment. Source review confirmed the existing `FLAG_QV=0/FLAG_SH=0` RH/TT fallback in the pinned `module_initialize_real.F:1112–1139,4099–4131`; 18 UTC QC/QG/QI/QR/QS are present and finite.
- Use RN1 under the supplied one-hour/mm product convention. RN1 is a processed radar/AWS analysis, with positive-scan averaging and station/cloud adjustments; agreement is not independent observation validation. Matching PTY is retained but no forecast precipitation-type score is asserted.

## Verification region and scores

Only South Korean land is eligible. Select ODAM region codes `11,21,31,41,51,61` from `ANAL/NE57/DABA/landseamask.dat` and intersect with `lnd == 1` from `ANAL/NE57/DABA/static.nest7grid`. The latter is explicitly labelled “land (1) water (0) mask”. This excludes water cells even where the regional mask selects them. The intersection contains 3,688 points; 747 of the 4,435 regional candidates are excluded by the land mask.

Use the original ODAM crop (Fortran x=76:224, y=7:259) and verify exact static/analysis latitude-longitude agreement. The checked ODAM source has no full textual country-code legend; the regional interpretation is supported by the source selection and static-coordinate map, with land eligibility independently enforced by `lnd`. No latitude cutoff, rainfall-dependent support, or threshold-dependent geographic mask is allowed. Bilinearly interpolate forecast amounts to actual ODAM point coordinates, requiring all four contributors and no extrapolation. Record any common-data validity exclusions separately from the fixed geographic mask.

For each lead 1–6 and threshold 0.1, 1, 5, and 10 mm, count hits H, misses M, false alarms F, and correct dry points. Define CSI = H/(H+M+F), with an undefined score when the denominator is zero. Pool contingency counts across the six hourly events for an additional summary; this is not a threshold applied to six-hour accumulated rainfall.

The old full-ODAM-domain comparison does not satisfy this geographic restriction and is superseded for the requested verification.

## Evidence

- Run inputs, settings, mask inventory, comparison script, and results: `scratch/cp02_six_hour_20260914/`.
- Extended boundary provenance: `scratch/cp02_native_12_18_AkoPPp/RESULT.json`.
- Pinned runtime: `tests/intel_toolchain.sh`; native executable SHA-256 `de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168`.
- Native boundary SHA-256 `74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45`.

Initial U/V/T/moisture differ between these retained cases while initial W is unchanged. Therefore precipitation differences cannot be attributed exclusively to omega. Any forecast failures or missing hours must remain explicit; a partial trajectory is not six-hour completion.

## Completed results

All three runs exited 0 with `SUCCESS COMPLETE WRF`, seven hourly outputs, and unchanged staged initial/boundary files. All 72 hour × case × threshold contingency tables use 3,688 points and match an independent calculation using the previous alignment helper. Accumulation checks found no large negative differences; RAINSH remained zero.

| Hourly threshold (mm) | OFF pooled CSI | HYDRO pooled CSI | LIQUID pooled CSI |
|---:|---:|---:|---:|
| 0.1 | 0.3460 | 0.3379 | 0.3379 |
| 1.0 | 0.2874 | 0.2863 | 0.2831 |
| 5.0 | 0.1904 | 0.1852 | 0.1869 |
| 10.0 | 0.1174 | 0.1039 | 0.1152 |

OFF has the largest pooled CSI at all four thresholds in this case; the retained HYDRO/LIQUID changes do not show consistent improvement. Some individual late-hour thresholds improve, so the hourly tables remain relevant. This is one case and supports no statistical-generalization or isolated omega-effect claim.

[Full hourly report](../scratch/cp02_six_hour_20260914/REPORT.md), [CSV](../scratch/cp02_six_hour_20260914/hourly_csi.csv), [CSI figure](../scratch/cp02_six_hour_20260914/hourly_csi.png), [verification mask](../scratch/cp02_six_hour_20260914/reference/verification_mask.png), [independent check](../scratch/cp02_six_hour_20260914/INDEPENDENT_CSI_CHECK.json).

The first diagnostic attempt used incorrect coordinate offsets/source indices and was rejected. The corrected results above reproduce the existing first-hour aligned amounts within 1.2e-12 mm and independently reproduce all 72 contingency tables. `REJECTED_RESULT_INDEXING_ERROR.json` is not a valid score product.
