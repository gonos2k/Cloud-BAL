# PR82 integration progress

The retained PR81 13 UTC candidate now reaches actual WRF initialization through
one hash-bound research chain. Its background alpha weight stays at 0.5.

| Boundary | Result |
|---|---|
| Candidate replay | Exact original NetCDF SHA `135c2315…7ef1` |
| WPS writer | 235 big-endian records; exact candidate/retained-slab readback |
| Intel metgrid | Same-time output and declared field flags verified |
| Real | Actual 13 UTC input plus genuine 14/15 UTC boundary authority |
| WRF initialization | Same-time initial readback and input/output isolation pass |
| First KDM6 call | Rejected: positive cloud mass with zero cloud number |
| Independent observation fit and time response | Open |

[The handoff](PR82_SAME13_HANDOFF_20261012.md) records inherited component
versions, the representation conversions and exact time-configuration changes.
Native initialization changes W by up to 0.603326 m/s and physical P+PB by
2.84375 Pa. Ambient CCN becomes positive, while cloud/ice/rain number fields
remain zero. Checking real output alone would miss those changes.

[Signal readback](PR82_OBSERVATION_SIGNAL_20261012.md) applies the source-linked
liquid-water concentration operator on fixed support. Local LWC input-consistency
RMSE rises about 0.216% relative to PR80. The LWC product is already an analyzed
input; it provides no independent observation-fit approval or calibrated R.

[The separate 12 UTC native trace](PR82_NATIVE_NUMBER_TRACE_20261012.md)
records NC changing from zero to a negative RK2 subnormal, then to the positive
minimum subnormal at RK3. Multiplying by represented dry density rounds that
value to zero even with FTZ/DAZ clear. Exact tendency/geometry operands are still
needed to attribute its source.

The next physical work is a justified joint Q/N/B initialization at the actual
native consumption boundary, followed by completed coupled updates and
same-candidate budgets/time response. Changing wind caps, alpha weight, number
floors or admission checks did not produce these results. Validation and its
limits are recorded in [the team review](PR82_TEAM_REVIEW_20261012.md).
