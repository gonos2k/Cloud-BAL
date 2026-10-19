# PR89 current KDM6 cold-process summary

## Current evidence

Each supplied V50 cold ledger has 954 schema-comment lines and zero data
records. Its status is `NOT_EVALUATED`: it contains no current
timestep or call counts and supports no proposed/applied/deferred estimate.
No saved V17 results are copied into this current summary.

The source bound for the collector is
`/var/tmp/pr87_followup_sources_20261019_v44/module_mp_kdm6.F`, SHA-256
`769cf33f7e6d59d46e2b31ec973a7d44cecce0b505fc18b0890b5b2a4ef2464f`.
The cold transaction commits inside `kdm62D`, after which the existing
per-cell ledger write is guarded by `.false.`. The compact collector observes
the in-memory requests at that commit point and emits one row per
`(pr87_model_timestep,lat)` call after all substeps.

## Compact row contract

`tools/pr89_cold_process_summary.py` provides `add_cold_summary(source,
expected_sha256)`. The caller must supply the expected source hash, allowing
the transform to compose after another source-bound transform without
silently accepting drift. It writes `pr89_kdm6_cold_summary.raw` with call
counts and 18 values: for NG, AUT, and G, each proposed/applied/deferred
stage has signed water change and half-L1 water activity.

For each cell transaction, the water vector is `Q(5)+QV`; `signed` is the
sum of its signed components, and `half-L1` is
`0.5 * sum(abs(Q(5)),abs(QV))`. Applied values use the final accepted group
alpha; deferred values use `1-alpha`. These are same-call request activity
measures, not reaction throughput or a closed conservation budget. Number,
heat, and graupel-volume vectors are not included in this water measure.

The source call provides dry density and layer thickness but no horizontal
area or map factor. The collector therefore weights each column with the
actual same-call `DEN*DELZ` and reports `kg m-2 SUM_COLUMNS`. A call row
contains `step,lat,loops,cell_transactions,raw_cell_rows,
unrecorded_transactions`. The existing verbose cell ledger remains disabled,
so its row count is zero and all transactions are marked unrecorded at cell
resolution even though their aggregate contributes to the summary. Applying
an exact horizontal area field later is impossible after summing over i;
these values must not be labeled global kilograms.

`tools/pr89_cold_process_summary.py` reads only the supplied current ledger
or the new compact output. It validates row widths, finite values, unique
call keys, and the identity
`unrecorded_transactions = cell_transactions - raw_cell_rows`. A header-only
legacy `PR85_KDM6_COLD` ledger is `NOT_EVALUATED`; the compact summary requires
one data row per matching header and rejects an incomplete header/data pair.

## Validation scope

The source-form test extracts the declarations, header, accumulator, and
writer directly from the transformed pinned V44 source. That fixture compiles
and runs with the pinned Intel profile at O0 and O2. Distinct nonzero NG/AUT/G vectors check each group's signed and half-L1
proposal, approval and deferral, including the actual final-alpha assignments
with a manufactured composite factor. This checks group ordering and accounting;
it does not replay runtime composite backtracking. Python checks cover the hash-bound
transform, header-only status, compact call/count decoding, and malformed
count rejection. This validates the collector source form without running the
full KDM6 model. The collector does not change process rates, fractions,
transaction ordering, or state updates.

## Current C1 closed-run prefix

Both requested 120-second runs exited `INCOMPLETE` with return code 1 after four completed 20-second steps. Each compressed summary is SHA-bound in its arm receipt and was fully read and checked: 1,120 call rows per arm, 280 at each of steps 1–4. The summaries contain no step-5 call, so these results cover an evaluated 80-second prefix of incomplete 120-second attempts. The fatal joint-moment event at the next step is outside the cold-summary rows.

The table reports completed-prefix half-L1 water activity by group. Values are `kg m-2 SUM_COLUMNS` after the actual same-call `DEN*DELZ` weights. Ratios are aggregate applied/proposed and deferred/proposed half-L1. Signed values, both ratio metrics, timestep breakdowns, row counts, receipt and gzip hash bindings, and transaction counts are in [`c1_cold_summary.json`](evidence/pr89_process_contract_20261019/native/c1_cold_summary.json).

| Arm | Group | Proposed | Applied | Deferred | Applied / proposed | Deferred / proposed |
|---|---:|---:|---:|---:|---:|---:|
| OFF | NG | 8,696.889938 | 6,874.303419 | 1,822.586518 | 0.790432 | 0.209568 |
| OFF | AUT | 1,534.931910 | 118.199402 | 1,416.732508 | 0.077006 | 0.922994 |
| OFF | G | 10,491.354324 | 1,321.882569 | 9,169.471755 | 0.125997 | 0.874003 |
| COUPLED | NG | 8,697.509705 | 6,874.502418 | 1,823.007287 | 0.790399 | 0.209601 |
| COUPLED | AUT | 1,534.734487 | 118.439518 | 1,416.294969 | 0.077173 | 0.922827 |
| COUPLED | G | 10,490.549201 | 1,326.326273 | 9,164.222928 | 0.126431 | 0.873569 |

All three group vectors are represented separately; zero signed denominators, including AUT, are encoded as `ZERO_DENOMINATOR` with a null ratio in the JSON. This is a same-call diagnostic request measure, not reaction throughput or a closed conservation budget. KDM62D supplies no horizontal area, so these values are not global kilograms. No historical V17 values are included.

## Current C3 closed-run prefix

Both C3 120-second attempts ended `INCOMPLETE` with return code 1 at completed step 4. Their receipt-bound summaries were fully parsed and independently re-aggregated: 1,120 KDM6 call rows per arm, 280 at each of steps 1–4. These values cover an evaluated 80-second prefix of each incomplete 120-second attempt. The executable SHA-256 was `ab8ff2312b8cb8cd65a44b78801d2938367f6e8793148d2ed1211479fe04ff97` for both arms.

The table reports completed-prefix half-L1 water activity by group, in `kg m-2 SUM_COLUMNS` after same-call `DEN*DELZ` weighting. Ratios are applied/proposed and deferred/proposed half-L1. Signed metrics, both ratio metrics, step breakdowns, transaction counts, status fields, and receipt/gzip hashes are recorded in [`c3_cold_summary.json`](evidence/pr89_process_contract_20261019/native/c3_cold_summary.json). Each arm had zero raw cell rows; its transactions are therefore marked unrecorded at cell resolution while their aggregated values contribute to the compact summary.

| Arm | Group | Proposed | Applied | Deferred | Applied / proposed | Deferred / proposed |
|---|---:|---:|---:|---:|---:|---:|
| OFF | NG | 8,696.889938 | 6,874.303419 | 1,822.586518 | 0.790432 | 0.209568 |
| OFF | AUT | 1,534.931910 | 118.199402 | 1,416.732508 | 0.077006 | 0.922994 |
| OFF | G | 10,491.354324 | 1,321.882569 | 9,169.471755 | 0.125997 | 0.874003 |
| COUPLED | NG | 8,697.509705 | 6,874.502418 | 1,823.007287 | 0.790399 | 0.209601 |
| COUPLED | AUT | 1,534.734487 | 118.439518 | 1,416.294969 | 0.077173 | 0.922827 |
| COUPLED | G | 10,490.549201 | 1,326.326273 | 9,164.222928 | 0.126431 | 0.873569 |

These remain same-call request activity diagnostics, not reaction throughput or a closed conservation budget. KDM62D provides no horizontal area, so the column sums are not global kilograms. No historical V17 rates are included.

## Current C4 closed-run prefix

Both C4 120-second attempts ended `INCOMPLETE` with return code 1 at completed step 4. The receipt-bound summaries were fully parsed and independently re-aggregated: 1,120 KDM6 call rows per arm, 280 at each of steps 1–4. These values cover an evaluated 80-second prefix of each incomplete 120-second attempt; no step-5 cold-summary call is included. The executable SHA-256 was `5c7f6ff646d4867e4e21194d071a12db9bfad6ad4ef303d7d3bc75fd150268a4` for both arms.

The table reports completed-prefix half-L1 water activity by group, in `kg m-2 SUM_COLUMNS` after same-call `DEN*DELZ` weighting. Ratios are applied/proposed and deferred/proposed half-L1. Signed metrics, both ratio metrics, step breakdowns, transaction counts, actual process statuses, and receipt/gzip hash bindings are recorded in [`c4_cold_summary.json`](evidence/pr89_process_contract_20261019/native/c4_cold_summary.json). Each arm had zero raw cell rows; its transactions are therefore marked unrecorded at cell resolution while their aggregated values contribute to the compact summary.

| Arm | Group | Proposed | Applied | Deferred | Applied / proposed | Deferred / proposed |
|---|---:|---:|---:|---:|---:|---:|
| OFF | NG | 8,696.889938 | 6,874.303419 | 1,822.586518 | 0.790432 | 0.209568 |
| OFF | AUT | 1,534.931910 | 118.199402 | 1,416.732508 | 0.077006 | 0.922994 |
| OFF | G | 10,491.354324 | 1,321.882569 | 9,169.471755 | 0.125997 | 0.874003 |
| COUPLED | NG | 8,697.509705 | 6,874.502418 | 1,823.007287 | 0.790399 | 0.209601 |
| COUPLED | AUT | 1,534.734487 | 118.439518 | 1,416.294969 | 0.077173 | 0.922827 |
| COUPLED | G | 10,490.549201 | 1,326.326273 | 9,164.222928 | 0.126431 | 0.873569 |

These remain same-call request activity diagnostics, not reaction throughput or a closed conservation budget. KDM62D provides no horizontal area, so the column sums are not global kilograms. No historical V17 rates are included.

## Current C5 completed 120-second runs

Both C5 arms completed all six 20-second steps with receipt status `COMPLETE`, return code 0, and final completed step 6. Each receipt-bound compact summary was fully parsed and independently re-aggregated: 1,680 KDM6 call rows per arm, 280 at each of steps 1–6. The executable SHA-256 was `beb2da6745606566074e15a043d173a8be01d277f00c4cc90ad3915f5de5a2d6` for both runs.

The table reports full-run half-L1 water activity by group, in `kg m-2 SUM_COLUMNS` after same-call `DEN*DELZ` weighting. Ratios are applied/proposed and deferred/proposed half-L1. Signed metrics, both ratio metrics, per-step values, transaction counts, actual process statuses, and receipt/gzip hash bindings are recorded in [`c5_cold_summary_120s.json`](evidence/pr89_process_contract_20261019/native/c5_cold_summary_120s.json). Each arm had zero raw cell rows; its transactions are therefore marked unrecorded at cell resolution while their aggregate values contribute to the compact summary.

| Arm | Group | Proposed | Applied | Deferred | Applied / proposed | Deferred / proposed |
|---|---:|---:|---:|---:|---:|---:|
| OFF | NG | 10,644.980444 | 8,549.730006 | 2,095.250438 | 0.803170 | 0.196830 |
| OFF | AUT | 2,113.424390 | 214.822974 | 1,898.601416 | 0.101647 | 0.898353 |
| OFF | G | 16,251.692320 | 1,989.772783 | 14,261.919537 | 0.122435 | 0.877565 |
| COUPLED | NG | 10,646.299152 | 8,550.089216 | 2,096.209937 | 0.803104 | 0.196896 |
| COUPLED | AUT | 2,113.017420 | 214.899816 | 1,898.117604 | 0.101703 | 0.898297 |
| COUPLED | G | 16,247.776355 | 1,994.900578 | 14,252.875777 | 0.122780 | 0.877220 |

These are same-call request activity diagnostics, not reaction throughput or a closed conservation budget. KDM62D provides no horizontal area, so the column sums are not global kilograms. No historical V17 rates are included.

## Current C5 600-second attempt

Both requested 600-second attempts ended `INCOMPLETE` with return code 128. Each receipt reports six completed 20-second steps (120 seconds). The fully parsed cold summaries contain all 1,680 rows for steps 1–6 plus 221 of 280 call rows at step 7; 59 step-7 call rows are absent in each arm. The partial step is reported separately and is not counted as a completed step. The executable SHA-256 was `beb2da6745606566074e15a043d173a8be01d277f00c4cc90ad3915f5de5a2d6` for both runs.

The first table sums only completed steps 1–6. The second table covers only the observed 221 rows at partial step 7. Both report half-L1 water activity by group, in `kg m-2 SUM_COLUMNS` after same-call `DEN*DELZ` weighting. Ratios use the same subset's applied/proposed values. The evidence JSON contains all signed and half-L1 metrics, per-step rows, exact partial-step counts, completed-prefix and all-recorded aggregates, transaction counts, process status, and receipt/compressed/uncompressed hashes: [`c5_cold_summary_600s.json`](evidence/pr89_process_contract_20261019/native/c5_cold_summary_600s.json).

| Arm | Completed steps | Group | Proposed | Applied | Deferred | Applied / proposed | Deferred / proposed |
|---|---:|---|---:|---:|---:|---:|---:|
| OFF | 1–6 | NG | 10,644.980444 | 8,549.730006 | 2,095.250438 | 0.803170 | 0.196830 |
| OFF | 1–6 | AUT | 2,113.424390 | 214.822974 | 1,898.601416 | 0.101647 | 0.898353 |
| OFF | 1–6 | G | 16,251.692320 | 1,989.772783 | 14,261.919537 | 0.122435 | 0.877565 |
| COUPLED | 1–6 | NG | 10,646.299152 | 8,550.089216 | 2,096.209937 | 0.803104 | 0.196896 |
| COUPLED | 1–6 | AUT | 2,113.017420 | 214.899816 | 1,898.117604 | 0.101703 | 0.898297 |
| COUPLED | 1–6 | G | 16,247.776355 | 1,994.900578 | 14,252.875777 | 0.122780 | 0.877220 |

| Arm | Partial step | Rows | Group | Proposed | Applied | Deferred | Applied / proposed | Deferred / proposed |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| OFF | 7 | 221 / 280 | NG | 593.198316 | 518.897484 | 74.300831 | 0.874745 | 0.125255 |
| OFF | 7 | 221 / 280 | AUT | 238.877720 | 54.331677 | 184.546043 | 0.227446 | 0.772554 |
| OFF | 7 | 221 / 280 | G | 2,032.740100 | 266.021116 | 1,766.718984 | 0.130868 | 0.869132 |
| COUPLED | 7 | 221 / 280 | NG | 593.357573 | 518.896047 | 74.461526 | 0.874508 | 0.125492 |
| COUPLED | 7 | 221 / 280 | AUT | 238.815881 | 54.241748 | 184.574134 | 0.227128 | 0.772872 |
| COUPLED | 7 | 221 / 280 | G | 2,030.771896 | 265.069456 | 1,765.702441 | 0.130526 | 0.869474 |

These are same-call request activity diagnostics, not reaction throughput or a closed conservation budget. KDM62D provides no horizontal area, so the column sums are not global kilograms. The 600-second attempts remain incomplete; no full-run rate or 600-second completion is claimed. No historical V17 rates are included.
