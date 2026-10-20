# C14 current response summary

This summary is limited to the two closed C14 240-second runs. Both receipts report `COMPLETE`, return code 0, and 12 completed model timesteps. Both used the same executed overlay executable (`5581e1be3febd54409304ccf7cbe305830a75968858075bf0d95f68b48d812be`) and the same compiled KDM source/build receipt. Each analysis arm is bound to its corresponding frozen candidate inputs; the different OFF and COUPLED `wrfinput_d01` hashes are expected under the C7/PR84 comparison policy. The results are a descriptive matched response under C14 and do not establish observational skill, a pure-model causal effect, or full-field treatment attribution. No 600-second result is included.

## Receipt-bound cold-process activity

The existing `pr90_cold_column_summary.area_weighted_totals` function validated each run receipt, build/executable/source identity, same-run history, and stage-record geometry before area weighting. Both runs have complete interior-column coverage for all 12 completed timesteps on the 234×282 grid. Activity is weighted using the native `DEN*DELZ` column values and `DX*DY/(MAPFAC_MX*MAPFAC_MY)` area. The displayed sums combine steps 1–12, separately for each arm and process group.

| Arm | Group | Proposed half-L1 (10⁹ kg) | Applied half-L1 (10⁹ kg) | Deferred half-L1 (10⁹ kg) | Deferred / proposed |
|---|---:|---:|---:|---:|---:|
| OFF | NG | 394.347 | 325.545 | 68.802 | 17.45% |
| OFF | AUT | 89.302 | 18.778 | 70.524 | 78.97% |
| OFF | G | 806.617 | 132.105 | 674.511 | 83.62% |
| COUPLED | NG | 394.378 | 325.535 | 68.843 | 17.46% |
| COUPLED | AUT | 89.289 | 18.778 | 70.512 | 78.97% |
| COUPLED | G | 806.379 | 132.136 | 674.243 | 83.61% |

These are signed/half-L1 cold-process request-activity diagnostics from the instrumented ledger. Applied and deferred are the logged acceptance-factor partition of proposed half-L1 request activity, not separately measured stored-endpoint deltas or realized reaction throughput. They are not precipitation or an inventory-change budget. In particular, the large AUT/G deferred activity is not assigned a unique donor, PSD, density, storage, or composite cause by these aggregates.

## Same-time history snapshots

The machine-readable [summary](summary.json) contains receipt-bound differences at 0, 60, 120, 180, and 240 seconds for total pressure (`P+PB`), interface geopotential (`PH+PHB`), and native vertical-face `W`, plus `QCLOUD`, `QICE`, `QSNOW`, and `QGRAUP` inventories. Each inventory uses the hybrid dry mass calculated from that same arm’s history at that same snapshot time. The state-field and inventory differences describe the matched response under C14; they do not establish observational skill, a pure-model causal effect, or full-field treatment attribution.

Scope remains narrow: the C14 240-second cold activity and snapshots do not close observation-footprint, source/operator, budget, or physical-approval gates. The 600-second runs and final-inventory/precipitation conclusions are outside this evidence.
