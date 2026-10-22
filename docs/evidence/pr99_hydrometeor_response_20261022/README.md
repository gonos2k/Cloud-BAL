# First KDM6 hydrometeor state and response at 20 s

This compares receipt-bound pre/post arrays around the first public native KDM6 call at model time 20 seconds. The scope is the first call's T1 post-physics state and the increment during that call. It does not describe all host changes over 20 seconds, later RK operations, end-of-forecast fields, total-water inventory, or observation skill.

The four runs are original C1 OFF, HYDRO, and COUPLED, plus the U/V projection proposal. Each has a closed one-step receipt at 2026-08-16 13:00:20, matching executable and boundary-file identities; each staged boundary file hash matches its receipt. Pre/post trace compressed and expanded hashes also match their receipts. Active arrays have KJI shape 39×280×232 (all 39 mass levels). The fixed native QC support has 613 cells in 16 columns; the 5-cell buffer is the fixed Chebyshev expansion of those columns; the domain includes all active mass cells.

Three quantities are kept distinct:

1. Each arm's KDM6 microincrement, `POST − PRE`.
2. The cross-arm POST state contrast, `proposal POST − OFF POST`, compared against the original initial `C1_COUPLED − OFF` pattern. The projection is descriptive alignment, not causal attribution.
3. The cross-arm microincrement contrast, `(proposal POST − proposal PRE) − (OFF POST − OFF PRE)`.

The T0 fields come from receipt-bound `wrfinput_d01` files. The proposal and original C1 COUPLED QCLOUD, QICE, QRAIN, QSNOW, and QGRAUP arrays have matching full-grid shapes and dtypes and identical SHA-256 hashes over original-dtype full-array bytes. Thus the T0 moisture contrast is the original coupled-minus-off signal. The reducer reads each full variable through the existing finite-value reader before cropping; it rejects nonfinite and declared fill/missing sentinels. All Q fields are kg/kg dry mixing ratios. Signed cell sums are not extensive water mass.


## PRE-KDM6 entry alignment

The PRE dump is the captured state at entry to the first KDM6 call at 20 s. It already includes host operations preceding that call, so these alignments show whether the initial T0 C1−OFF pattern is present on call entry; they do not isolate which earlier operation produced it.

| Species | T0 C1−OFF RMS | Proposal−OFF PRE RMS / cosine | HYDRO−OFF PRE RMS / cosine | C1−OFF PRE RMS / cosine |
|---|---:|---:|---:|---:|
| QC | 1.250939e-04 | 1.238663e-04 / 0.997572 | 1.233353e-04 / 0.999659 | 1.239059e-04 / 0.996963 |
| QI | 2.985045e-07 | 6.839672e-06 / 0.145471 | 1.618792e-06 / 0.826410 | 7.631943e-06 / 0.099525 |
| QR | 5.785855e-05 | 5.573674e-05 / 0.998899 | 5.567591e-05 / 0.999191 | 5.583492e-05 / 0.998799 |
| QS | 7.590343e-05 | 7.517418e-05 / 0.999371 | 7.520020e-05 / 0.999820 | 7.533161e-05 / 0.999122 |
| QG | 6.919132e-05 | 6.727783e-05 / 0.999229 | 6.724067e-05 / 0.999207 | 6.729217e-05 / 0.999232 |

For QC, the near-unity PRE cosines show that all three coupled/control contrasts retain the initial C1−OFF pattern at KDM6 entry. Their negative POST cosines show that this alignment rotates across the measured KDM6 interval. These comparisons do not attribute the rotation to a specific process within the call.

## 613-cell native QC support

| Species | T0 C1−OFF RMS | P−OFF POST RMS / cosine | HYDRO−OFF POST RMS / cosine | C1−OFF POST RMS / cosine | P−HYDRO POST RMS |
|---|---:|---:|---:|---:|---:|
| QC | 1.250939e-04 | 1.234053e-05 / -0.589857 | 1.475689e-05 / -0.487781 | 1.846038e-05 / -0.446216 | 1.259268e-05 |
| QI | 2.985045e-07 | 6.118710e-06 / 0.200214 | 9.325077e-05 / 0.027644 | 2.125340e-04 / -0.020309 | 9.341946e-05 |
| QR | 5.785855e-05 | 6.392573e-05 / 0.222839 | 6.373798e-05 / 0.223386 | 6.390455e-05 / 0.222531 | 1.935927e-06 |
| QS | 7.590343e-05 | 7.397831e-05 / 0.993312 | 1.264718e-04 / 0.576538 | 2.482158e-04 / 0.470892 | 1.017460e-04 |
| QG | 6.919132e-05 | 0.000000e+00 / undefined | 0.000000e+00 / undefined | 0.000000e+00 / undefined | 0.000000e+00 |

The JSON also gives signed means, cell sums, maximum absolute values, fixed-buffer and full-domain metrics, PRE-state contrasts, and the microincrement contrast. The same initial C1−OFF pattern is used to report alignment for proposal−OFF, HYDRO−OFF, and original C1−OFF POST state contrasts; proposal−HYDRO POST contrast RMS is also included. Projection is null only when the initial baseline has exactly zero norm; cosine is null when either compared vector has zero norm. In the POST QC table QG cosine is undefined because the current POST contrast is zero, while its initial C1−OFF signal is nonzero. Metrics are finite checks performed on the full captured active arrays before reduction.

The existing `native_kdm6_trace.read_dump` parser is used after decompressing each trace to a temporary file. The reducer fails closed on receipt state, input and boundary SHA, duplicate/missing trace rows, compressed and expanded trace SHA, stage, timestep, call-header, and grid-shape mismatches. See `reduce.py` for the exact reduction procedure and private paths bound to the source evidence.
