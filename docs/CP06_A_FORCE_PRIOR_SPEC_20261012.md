# Retained CP06-A force-prior experiment

This specification precedes the force-refinement candidate run. The retained
2026-08-16 13 UTC OFF/HYDRO/COUPLED artifacts remain immutable. This is a research
prior, not an observed acceleration, covariance estimate, or scientific approval.

Use the original 500-cell wind control, 980-cell continuity shell, and 900-cell
force mask without selection or enlargement. Preserve pressure, geometry,
boundary metadata, temperature, vapor, hydrometeors, geopotential, and omega.
The fixed boundary flux belongs to the background boundary contract; a boundary
cell's analyzed omega is not itself the prescribed boundary-face flux.

The force reference is the background's nonzero geostrophic residual. Minimize
the sum of squared total horizontal wind increments with 4 m/s prior scale and
squared force-residual increments with scale |f| times 4 m/s. Reject unusable or
zero Coriolis parameters. Do not replace the reference with zero or choose scales
from the candidate's residual. Project one descent direction into the existing
dry-flux operator's nullspace, then minimize the quadratic along that direction.

Retain the original continuity thresholds: RMS <= max(0.002 times
1.0152186264544263e-7, 1e-12) and maximum <= max(0.002 times
7.2467128524046317e-7, 1e-12), in s^-1. Bound total candidate-minus-background
horizontal wind by 10 m/s and omega by 5 Pa/s; use 0.95 analytic headroom and
recheck the stored REAL32 state against the hard caps. Require objective decrease
and no increase in the same-mask absolute force RMS beyond 64 REAL32 epsilons
times max(input RMS, background RMS). Exact-background no-op is permitted.

Failure retains the input component state. Pipeline use must retain the complete
background operational state and reject the failed candidate. A component probe
must not claim pipeline producer authority. Independent readback must recompute
force and flux from the stored state and geometry and identify metadata omissions.

WRF initialization is a separate, necessary integration boundary: trace wrf_init,
physics initialization, KDM6 coefficient initialization, and first coefficient
consumption. The native 12 UTC diagnostic baseline is not this 13 UTC analysis
candidate. A repaired radar initializer alone does not establish same-candidate
native acceptance, completed microphysics, or reduced initial forecast shock.
