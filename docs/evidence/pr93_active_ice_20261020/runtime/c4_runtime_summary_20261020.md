# PR93 C4 closed-runtime science summary

Both receipt-bound C4 runs completed the requested 600 seconds (30 steps at 20 seconds per step), returned code 0, and reported no collector errors. The paired histories store 11 common records from T0 through T600 at one-minute cadence. Completed model timesteps and stored records are separate counts.

The fixed QC source support covers 613 native points across 16 columns. QCLOUD OFF/COUPLED delta RMS is 0.00012509394 kg/kg at T0, 4.3844388e-05 at T420, and 3.2945245e-05 at T600. The RMS of δQC(T600)−δQC(T0) is 0.00014059544 kg/kg. Pressure, geopotential, and W responses are included in the JSON. These are unweighted field differences, not inventory or observational skill.

Area-weighted cold-process half-L1 diagnostics are reported on two nested windows from these same complete runs: timesteps 1–23 and 1–30. Per-group and per-timestep outputs and summed totals are preserved in the activity JSONs. Half-L1 activity is not total physical throughput; the nested-prefix comparison does not establish physical improvement, observation skill, or water/energy closure.

| Arm | Requested/completed window | Stored history | Completed steps |
|---|---:|---:|---:|
| OFF | 600 s | 0–600 s, 11 records | 30 |
| COUPLED | 600 s | 0–600 s, 11 records | 30 |

Reducer and input identities are recorded in `c4_runtime_summary_20261020.json`. This is a separate C4 runtime artifact; the preserved PR92 C18 report and evidence are unchanged.
