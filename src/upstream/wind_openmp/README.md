# Isolated wind producer sources

These copies keep Cloud-BAL validation changes outside the operational KLAPS
source tree.

The Barnes observation-bound precomputation gives each OpenMP iteration its
own `i`, `j`, and `k`. Without `PRIVATE(i,j,k)`, threads can combine coordinates
from different observations while writing otherwise disjoint bounds arrays.
The correction preserves the weighting equations and accumulation order.

Two original 38-thread runs with identical inputs differed by more than 2 m/s.
Two pinned-ifx diagnostic runs using the corrected copy produced identical
LW3/LWM files and all retained input/output files. Evidence is in
`scratch/cp02_completion_ui53t82f/wind_fixed_repeat_comparison.json`.
The diagnostic relink reuses verified unchanged objects. The maintained
`tools/build_upstream_producer.sh` now selects this corrected source; fresh full
builds and the complete four-case regression are being validated.

The invalid-time diagnostic in `get_time_wt` uses the named OpenMP critical
region `barnes_time_diagnostic` because the routine is called by parallel
observation loops. Only its unit-6 write is serialized. The original greater-
than-ten-hour policy, fallback weight of 1, failure status of 0, and valid-time
weighting equation are unchanged.
