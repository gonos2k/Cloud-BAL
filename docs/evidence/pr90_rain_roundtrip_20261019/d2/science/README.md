# D2 area-weighted cold activity diagnostic

This is a diagnostic reexecution for the D2 candidate, not a reconstruction of
the immutable C5 history. Historical C5 area-weighted activity remains
`NOT_EVALUATED` because its old collector collapsed columns before the area
weights were recorded.

The result uses `DX*DY/(MAPFAC_MX*MAPFAC_MY)` from the D2 history grid
(`234 x 282`, `DX=DY=5000 m`) and sums the column `DEN*DELZ` weighted metrics
for each timestep. The reported units are **kg per model timestep over
recorded KDM columns**. Each metric includes signed sum and half-L1 sum for
proposed, deferred, and applied activity. The cumulative description means
activity requested across the recorded KDM calls within that timestep; it does
not extrapolate missing columns or steps.

Run status is `INCOMPLETE`, with final completed step 6. Coverage is:

| Timestep | Coverage | Columns |
| --- | --- | ---: |
| 1–6 | Full, `j=2..281` | 64,960 each |
| 7 | Partial, `j=2..222`; `j=223..281` missing | 51,272 of 64,960 |

The artifact binds to run receipt SHA-256
`a25df40c099f4475d30c11ea8bb2ffea4b4bd4b289a68e357d7e02fb7e6b3503`, build
receipt `4fe307b5100de3696b5ff8363d744621174f87b8e041d71ed806b88a585e36af`,
executable `8bc9c2d55b21a8be19b1fb728d2d103b2874631f8d9426b82ea095370cd7c6be`,
compiled KDM6 source `600962920d749196dbab50ef090def2f6404add0af77ec63d6fabc22c32703b2`,
history `1eb247193d4fda3e34e73f13dd4ff979e9840965e7dcea9d7dbfbe939b5a93eb`, and
stage record `31f55bfba07560be06c171e8a31d567bbe9ce4a403972c32eaad610da8adc276`.
The execution layout is `VERIFIED_SINGLE`; its source hashes are retained in
the JSON result.

Files:

- `area_weighted_prefix.json`: per-timestep values, receipt bindings, and
  exact coverage details.
- `../t7_target_packet.json`: corrected T7 trace/warm-row packet.
- `../capture_t7_packet.py`: reproducible raw-row correction, trace crosscheck,
  and decimal-interval validation.
- `../warm_ledger.raw.gz` and `../producer_trace.raw.gz`: compressed source rows
  used by the T7 capture parser.
