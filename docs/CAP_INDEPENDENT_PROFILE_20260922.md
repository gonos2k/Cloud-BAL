# Cap-independent profile reconstruction and transition audit

## Cause and scope

PR38's thermodynamic sample pressure is continuous. Its legacy lower-transport
experiment is not: changing the common regular-level cap replaces the wind
profile over a finite pressure interval. With coincident endpoint sample
pressures approaching p_k, the per-length jump is

\[
 J_+-J_- = \tfrac12(p_k-p_{k+1})(U_k-U_{10}).
\]

The 95000/90000 Pa, 8/6 m/s pressure winds and 4 m/s sample give 10000 m Pa/s,
even as the sample-pressure perturbation tends to zero. This is a change of
reconstruction, not quadrature error or a defect in the thermodynamic prior.
No pressure tolerance or hysteresis removes that model discrepancy.

The old experiment remains available for reproducibility and is explicitly
`CAP_DEPENDENT_LEGACY_EXPERIMENT / NOT_AUTHORIZED_FOR_PHYSICAL_PROFILE` in all new lower-transport reports. Production D/G, solver, RHS, masks, boundary authority and speed
limits are unchanged. No corrected actual balance candidate is generated.

## One fixed-knot profile

The new Fortran research helper uses fixed, strictly ordered pressure knots p
and their scalar wind values v. For a sample inside that supported interval,
a(p_sample) is the continuous two-node piecewise-linear interpolation row.
The caller must explicitly supply positive nodal variances C (diagonal) and a
positive sample variance R. There are **no default variances**.

It solves the small stated problem

\[
 \min_w \tfrac12(w-v)^T C^{-1}(w-v)
       +\frac{(a^Tw-v_{10})^2}{2R},
\]

by the rank-one expression

\[
 \widehat v=v+Ca\frac{v_{10}-a^Tv}{R+a^TCa}.
\]

This is not a large balance solver. Conflicting collocated values are soft
inputs of the declared objective, rather than two incompatible exact constraints.
Positive C and R keep the denominator positive. At a pressure knot, a is
continuous, so the fitted nodal values and the integral are continuous as the
sample moves across it. Derivatives can change at knots; C1 smoothness is not
claimed. Outside the supplied profile domain or without valid variances, the
helper refuses the reconstruction and leaves outputs NaN.

The helper accepts variances only within 1e-100 to 1e100 and bounds pressure
and wind magnitudes for safe research arithmetic. It rejects values outside
that numerical envelope; it does not clip weights or infer physical QC limits.
A common variance scale is removed before forming the gain.

This is a **pointwise scalar profile prototype**, not a new shared-edge fit or
quadrature. Refitting at every edge quadrature point would generally introduce
a rational dependence on edge position; the old two-point Gauss exactness does
not carry over automatically. No actual edge transport uses this fit.

The existing `integrate_pressure_profile` integrates this **same fitted profile**:

\[
 \int_{p_t}^{p_b}\widehat v\,dp
 =\int_{p_t}^{c}\widehat v\,dp+\int_c^{p_b}\widehat v\,dp.
\]

The cap only partitions this integral; it is not an argument of the fit. Raw
LSX/LW3 inputs are never overwritten. The synthetic tests' diagonal variances
are mathematical fixtures, not calibrated LSX/LW3 error estimates. Correlated
errors, vector/coordinate metrics, profile representativeness and physical
validity of each supplied knot remain caller responsibilities.

## Actual-data transition audit

For each actual face and time, the audit uses its current cap q. Both sample
pressures are translated by p_q-min(p10), preserving their difference, while
all winds are held fixed. It evaluates the exact difference between the old
models with caps p_q and p_(q+1), using the same lower-strip integral three
times (new lower + upper band - old lower). Both regular levels are above the
current ground. This is a frozen-input limit experiment; it is **not an observed
wind tendency, realized temporal jump, or boundary forcing**.

Stored fields are cap index, signed pressure translation, integrated jump,
and endpoint maxima of the U/V sample-versus-cap differences in chart velocity
units. Adjacent-hour cap-index changes are counted separately. A count records
that the selected cap differs at the two samples, not every crossing between
them. Jump per face length has units m Pa/s; chart U/V differences are not an
earth-relative wind-speed acceptance test.

Actual variances and their cross-covariances are unavailable. Accordingly the
weighted helper is not applied to the NE57 data, and no synthetic uncertainty
is chosen to close its budget. The new audit quantifies the old experiment's
conflict while keeping all unresolved 0–10 m transports and full physical
residuals unknown.

## Evidence

The actual audit is retained in `scratch/pr39_validation/final/` with
prepared input, O0/O2 outputs, arrays, report, input/source/artifact hashes and
Intel log; invocation: `scratch/pr39_validation/run_actual.sh`. Original PR38
prior, transport, geometry and budget arrays are unchanged, including NaNs.

| Actual diagnostic | 12 UTC | 13 UTC | 14 UTC |
| --- | ---: | ---: | ---: |
| Faces audited | 198,480 | 198,480 | 198,480 |
| Frozen cap jump / length range (m Pa/s) | −55392.993 to 31480.854 | −66190.041 to 29576.677 | −58831.003 to 33371.864 |
| Maximum U sample/cap difference (chart m/s) | 16.0337 | 14.9405 | 14.0798 |
| Maximum V sample/cap difference (chart m/s) | 23.2857 | 29.3309 | 23.2271 |

Cap indices differ on 1,177 faces from 12 to 13 UTC and 1,094 from 13 to 14 UTC.
These are endpoint index changes, not an attribution of the actual transport
change to the discontinuity: winds, geometry and sample pressures also evolve.
For the limit experiment the median required pressure translation is about
−693, −719 and −733 Pa; thus many limits are not infinitesimally close to the
actual state. The report preserves the full translation distribution.
No reported jump is adopted as a correction, uncertainty or physical threshold.
At their actual separated heights, sample/cap wind differences can represent
vertical shear; the audit does not classify them as erroneous observations.

The cap-limit arithmetic comparison uses the pre-cancellation transport scale
of its three strip integrals, rather than epsilon times the cancelled jump.
Pinned Intel O0/O2 runs use fresh scratch directories. The lower-kernel suite
now contains 29 checks including mismatch/matching limits, reversed face and
invalid limit/NaN rejection.

The pointwise reconstruction suite passes 35 assertions at each pinned Intel
optimization level, including exact-knot matching/conflict, both-sided knot
limits, integrated continuity, arbitrary cap additivity, common variance-scale
invariance, immutable inputs and failed-output NaNs. Update-sign and ignored-
covariance mutations are both detected at O0/O2 (four rejected executions).
An additional 100 cases per optimization verify the objective gradient is zero
without reusing the rank-one expression as the expected result; see
`scratch/pr39_validation/stationarity.log`.
Evidence: `scratch/qbal_profile_reconstruction.e6oeix/` and
`scratch/pr39_validation/profile_mutations.log`.

The prepared-driver regression uses nonzero unequal winds and an HT-consistent
thermodynamic fixture on both sides of 95000 Pa, plus matching-wind controls.
Four cases per optimization retain NaN full residuals. The optional cap-audit
stream adds 45 doubles in this three-edge fixture while preserving the original
972-byte prefix exactly. Reproducer: `tests/test_qbal_cap_transition.py`;
evidence: `scratch/pr39_validation/cap_final_validated/`.

## Same-stage HT evidence

The retained final LT1 T3 follows surface-temperature insertion. The analyzed
`temp_3d` immediately after `insert_tobs` and before `get_heights_hydrostatic`
was not retained. Background FUA SH, LSX PS/MSL, terrain, observation inputs and
run receipts remain available, including the producer-handled absent PIN/SND/LRS
inputs. Thus the same-stage HT comparison cannot be reconstructed from final
T3 alone; a separate scratch producer replay with a capture at that boundary
is needed. No producer replay or height adjustment was performed here.

Source call order: `klaps-v5.0_/src/lib/temp/puttmpanal.f` loads background
fields, runs `insert_tobs`, calls `get_heights_hydrostatic`, then inserts surface
temperature. All three retained cases use `L_ADJUST_HEIGHTS=.false.`. The audit
and source/input hashes are retained at the workspace-relative path
`Cloud-BAL/scratch/pr39_height_audit_20260922/source_audit.md`.

This separates an unavailable intermediate state from missing external inputs;
it does not identify the ground residual as a measured terrain/height error.
The original PS and HT remain unchanged.
