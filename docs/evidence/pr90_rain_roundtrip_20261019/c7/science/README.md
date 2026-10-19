# C7 180-second paired area-weighted cold-column activity

Generated from the PR90 compact per-column collector using `area_weighted_totals` in `tools/pr90_cold_column_summary.py`, bound to each run receipt, candidate build/executable, compiled KDM source, native history, and same-run stage records.

## Coverage and units

Both arms completed timesteps 1–9. Each completed timestep has 64,960/64,960 active columns (`i=2..233`, `j=2..281`) with full j coverage. The history grid is 234×282 with `DX=DY=5000 m`; cell area is `DX*DY/(MAPFAC_MX*MAPFAC_MY)`. Per-column `DEN*DELZ` vertical sums were weighted by that cell area. Per-step and cumulative values are in kg of local process-vector activity over the recorded columns.

The deferred fraction shown below is deferred half-L1 divided by proposed half-L1, calculated per group. The cumulative fraction is a ratio of summed deferred and proposed half-L1 values over the completed prefix.

## Completed-prefix totals (timesteps 1–9)

| Arm | Group | Proposed half-L1 (kg) | Deferred half-L1 (kg) | Deferred fraction | Deferred signed (kg) |
|---|---:|---:|---:|---:|---:|
| OFF | AUT | 7.450271e+10 | 6.307275e+10 | 84.658327% | 0.000000 |
| OFF | G | 6.353380e+11 | 5.491749e+11 | 86.438239% | -188.760754 |
| OFF | NG | 3.415400e+11 | 6.217993e+10 | 18.205755% | -31.852338 |
| COUPLED | AUT | 7.448828e+10 | 6.306002e+10 | 84.657641% | 0.000000 |
| COUPLED | G | 6.350898e+11 | 5.488247e+11 | 86.416858% | -196.749095 |
| COUPLED | NG | 3.415870e+11 | 6.222141e+10 | 18.215389% | -33.174613 |

## Per-timestep deferred fraction

| Step | OFF NG | OFF AUT | OFF G | COUPLED NG | COUPLED AUT | COUPLED G |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 24.3222% | 95.2204% | 85.1333% | 24.3269% | 95.2201% | 85.1294% |
| 2 | 19.9581% | 92.4131% | 84.4905% | 19.9649% | 92.3786% | 84.4659% |
| 3 | 18.1238% | 91.1959% | 89.8701% | 18.1162% | 91.1697% | 89.8492% |
| 4 | 16.5834% | 88.7171% | 89.1978% | 16.5912% | 88.7066% | 89.0917% |
| 5 | 14.8456% | 85.5661% | 89.1083% | 14.8783% | 85.5918% | 89.0714% |
| 6 | 12.9847% | 80.8472% | 87.7372% | 12.9937% | 80.8648% | 87.7389% |
| 7 | 11.9207% | 75.8908% | 86.5872% | 11.9373% | 75.9189% | 86.6117% |
| 8 | 11.5489% | 69.6847% | 83.6438% | 11.5827% | 69.6884% | 83.6272% |
| 9 | 11.7537% | 63.3032% | 80.7000% | 11.7798% | 63.3076% | 80.6970% |

## Evidence bindings

- Candidate build receipt SHA-256: `7a58ac2ae90eca9ffe0500515282b537e11db25ab9de8175856609bf812bba31` (shared by both runs).
- Candidate executable SHA-256: `5f5599e38759a9e2be27a9e7e0977370592c92cab328062d07eb359bddd19572`.
- Compiled KDM6 source SHA-256: `983095a0aa0c76eab4efdda27f9435e61634e08e542ef9bd096aa4cf8004eca4`.
- OFF run receipt SHA-256: `3dc5773680fb0d92cbdf2aeb0a8ebaa1739e11c6366152add51e949c6f767ab1`.
- COUPLED run receipt SHA-256: `72fe00aebe9db05270c747b974218114d3f3f83d1d7c6a87d4032b6399c5a0e0`.
- The JSON records receipt-bound cold-column summary, history and stage-record hashes, verified single-execution layout hashes, grid metadata, all per-step metrics, coverage and cumulative totals.

## Interpretation limit

These totals measure local `DEN*DELZ*A`-weighted group-vector request activity from this candidate. They do not establish host-level water closure, a conversion to precipitation mass, or a precipitation suppression fraction. The warm PSD ledger records new PSD instrumentation; it does not provide a complete budget of the pre-ledger raw-NR cap update, because the cap itself is not generally logged.

## Paired history and one-event PSD evidence

`history_180s.json` binds actual T0/T60/T120/T180 histories to the same closed
180-second arm receipts. Its 27-column fixed T0 support is descriptive and
outcome-selected; it is not the original 162-pressure-cell observation mask.
See [the paired-history report](../../../../PR90_C7_HISTORY_20261019.md).

`psd_t8_event.json` and its extractor bind the single final rain boundary
reconstruction event at timestep 8, call-lat 222, i=188, k=5 in each arm.
This event is not a global number budget or physical nucleation estimate.

The separate same-executable 600-second pair closed INCOMPLETE after nine
completed steps (180 seconds), with a timestep-10 host joint-moment fatal.
These 180-second results do not establish 600-second completion or scientific
approval.
