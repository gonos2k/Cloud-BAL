# C6 area-weighted completed prefix

`area_weighted_completed_prefix.json` contains both OFF and COUPLED results
from the existing `area_weighted_totals` API. The join uses each arm's closed
run receipt, same-run cold-column summary, `wrfout` history, and joint-moment
stage trace. Grid-cell area is taken from actual history `DX`, `DY`,
`MAPFAC_MX`, and `MAPFAC_MY` using `DX*DY/(MAPFAC_MX*MAPFAC_MY)`.

Both runs are `INCOMPLETE` (return code 128), final completed step 7. Steps
1–7 each cover the full 64,960 interior columns (`i=2..233`, `j=2..281`).
Step 8 is partial: 51,272/64,960 columns through `j=222`; `j=223..281` are
missing. Step 8 values and fractions are retained separately and excluded from
the completed-prefix cumulative totals.

The deferred fraction is the area-weighted deferred half-L1 activity divided
by the area-weighted proposed half-L1 activity for the same group and timestep.
The completed-prefix fraction is the ratio of summed weighted deferred and
proposed half-L1 activity over steps 1–7, not an average of timestep fractions.
All amounts are local `DEN*DELZ`-weighted group-vector request activity in kg
per model timestep. These diagnostics do not establish host closure, primitive
precipitation rate, or physical water-budget approval.

| Step | Arm | NG deferred | AUT deferred | G deferred | Coverage |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | OFF | 24.32% | 95.22% | 85.13% | Full |
| 2 | OFF | 19.96% | 92.41% | 84.49% | Full |
| 3 | OFF | 18.12% | 91.20% | 89.87% | Full |
| 4 | OFF | 16.58% | 88.72% | 89.20% | Full |
| 5 | OFF | 14.85% | 85.57% | 89.11% | Full |
| 6 | OFF | 12.98% | 80.85% | 87.74% | Full |
| 7 | OFF | 11.92% | 75.89% | 86.59% | Full |
| 8 | OFF | 12.24% | 71.19% | 84.67% | Partial |
| 1 | COUPLED | 24.33% | 95.22% | 85.13% | Full |
| 2 | COUPLED | 19.96% | 92.38% | 84.47% | Full |
| 3 | COUPLED | 18.12% | 91.17% | 89.85% | Full |
| 4 | COUPLED | 16.59% | 88.71% | 89.09% | Full |
| 5 | COUPLED | 14.88% | 85.59% | 89.07% | Full |
| 6 | COUPLED | 12.99% | 80.86% | 87.74% | Full |
| 7 | COUPLED | 11.94% | 75.92% | 86.61% | Full |
| 8 | COUPLED | 12.29% | 71.19% | 84.65% | Partial |

| Arm | Completed-prefix NG | Completed-prefix AUT | Completed-prefix G |
| --- | ---: | ---: | ---: |
| OFF | 19.063% | 88.289% | 87.589% |
| COUPLED | 19.070% | 88.287% | 87.564% |

The JSON retains per-step signed and half-L1 amounts for proposed, applied,
and deferred activity, plus cumulative completed-prefix amounts, both partial
step amounts, and run/build/executable/source/history/stage/layout hashes.
No `SUM_COLUMNS` ratio is converted to a physical kilogram total; the
calculation uses the i-resolved column rows and actual mapped cell areas.
