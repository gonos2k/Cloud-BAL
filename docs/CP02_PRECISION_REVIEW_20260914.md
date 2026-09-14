# CP02 scientific, meteorological, mathematical and numerical review

Date: 2026-09-14. Scope: current maintained Cloud-BAL source and retained
12–13 UTC pilot forecasts. This review does not promote CP02 to complete.

The requested production direction is an internally diagnosed analysis-time
omega consistent with the chosen mass-continuity equation. External forecast
omega targets and a recreated empirical cloud-velocity function do not satisfy
that objective. Forecast integration is used here only to assess retained
initialization responses.

Omega is a diagnosed dynamical variable coupled to precipitation processes, not
an observed verification target. Evaluate its discrete mass/boundary consistency
and its influence on hydrometeor structure and subsequent forecast errors. Do
not require an observed omega field to proceed. An explicitly stationary
analysis-time diagnostic may set the chosen mass tendency to zero; time-bracketed
analyses are needed only when an unsteady tendency is to be estimated. Neither
choice implies introducing an external model target.

## Legacy QBAL: highest-priority mathematical findings

1. **Reproduced pressure-derivative sign error in `nonlin`.** Pressure descends
   with stored level while `dp(k)=p(k-1)-p(k)>0`. The code uses
   `(U(k+1)-U(k-1))/(dp(k)+dp(k+1))`, which equals `-dU/dp` for a linear pressure
   profile. The omega inputs retain the standard pressure-velocity sign. An
   isolated extraction of the unchanged FORTRAN routine was compiled with the
   pinned Intel ifx profile in fresh O0/O2 scratch builds. Both produced
   `nu=-7.49999963e-5` and `nv=-1.12500005e-4` m/s² where the declared
   perturbation-advection formula gives positive values. This establishes the
   routine-level sign error, not its magnitude in a deployed forecast.
   Source: `src/balance/qbalpe.f:173–196, 2986–3013`.
2. **Full/perturbation omega input mismatch.** The caller subtracts background
   U/V, but passes full omega to a routine whose `om` argument represents omega
   perturbation. Its background-shear term can therefore remain nonzero for
   zero state perturbation. This source contract mismatch is distinct from the
   derivative sign: correcting the derivative alone cannot correct the input.
   Source: `qbalpe.f:1359–1393, 2973–3013`.
3. **Unconditional error-weight overwrite.** The “For winds” weights are dead
   stores overwritten by “For heights” in the same loop. The effective wind
   profile uses 1.0 and the height profile 0.5; no namelist selector chooses
   between them. The overwrite is confirmed, but the intended weights are not.
   Source: `qbalpe.f:477–495`.

[Legacy mathematical review](../scratch/cp02_precision_review_20260914/legacy_math.md),
[ifx O0 reproduction](../scratch/cp02_qbalpe_nonlin_sign_20260914_7l4p9k/run/nonlin_o0.log),
[ifx O2 reproduction](../scratch/cp02_qbalpe_nonlin_sign_20260914_7l4p9k/run/nonlin_o2.log).
The probe exits successfully when it reproduces the defect; its exit status
must not be interpreted as passing the physical equation. No maintained source
was changed. Production executable/source binding must be established before
attributing these findings to an operational run.

The legacy unknowns are geopotential and wind/omega work fields plus a continuity
multiplier. Temperature is subsequently reconstructed hydrostatically; pressure
and moisture are supplied. It uses a sequential perturbation balance and local
relaxations, not the new Cloud-BAL normal operator. Its COM input/fallback and
stationary continuity correction do not generate a new physical cloud-omega law.

## Confirmed central design gap

`apply_localized_balance` constructs its right-hand side from the divergence of
the proposed increment (`b=r_proposed`), not from the total background-state
residual. Its intended result is approximately divergence-free **increments**.
Therefore an existing background residual can remain after a successful solve.
The model-target physical limit explicitly permits the background residual plus
a tolerance. This is internally consistent with an increment-preserving
projection, but it is not the requested diagnosis of a mass-consistent full state.

Source: `src/common/cloud_bal_balance_operator.f90:735–779, 822–850, 1226–1239`.
`build_cloud_targets` identifies cloud sublayers and retains the supplied target;
it does not yet generate the replacement physical cloud omega
(`src/common/cloud_bal_column_physics.f90:1374–1415`).

The smallest next physical change should reuse the existing face geometry and
boundary handling, explicitly define which mass equation and tendency assumption
are being solved, and diagnose the full-state residual. If fixed horizontal winds
and both vertical boundaries are incompatible, report that incompatibility;
do not remove its mean and label the result mass closure. Preserve Barnes wind
information when deciding any necessary horizontal adjustment.

## Evidence and limitations

- Current source identities: [snapshot](../scratch/cp02_precision_review_20260914/SOURCE_SNAPSHOT.json).
- [Radar structure and retained one-hour sensitivity](CP02_RADAR_STRUCTURE_REVIEW_20260914.md).
- [One-hour accumulation binding](../scratch/cp02_one_hour_sensitivity_20260914/RESULT.json).
- RN1 and PTY for 13 UTC have now been delivered. [The same-hour RN1 comparison](../scratch/cp02_odam_13utc_20260914/REPORT.md) is recorded separately; instantaneous model PTY mapping remains open. Integrated pc/spt/ptt are not substitutes.
- No source changes or new model integration are part of this review.

## Team findings and priorities

| Priority | Finding | Classification and next action |
|---|---|---|
| P1 | The current projection constrains increments; it does not diagnose total-state omega from continuity. | Design gap. Reuse the face operator to solve the declared full-state mass equation, including compatible boundaries. |
| P1 | `MODEL_DYNAMICS` requires an external paired target; no internal diagnostic generator is connected. | Integration gap. Add the internal calculation in the actual production path with its own provenance, without an observed-omega requirement. |
| P1 | Cloud-layer detection retains background W; radar loading uses an empirical efficiency and speed caps. | Physical scope gap. Keep the empirical experiment distinct from the internal mass diagnostic. Continuity alone does not guarantee a correct precipitation life cycle. |
| P2 | Pressure-coordinate carrier residual, dry-air flux divergence, and water/enthalpy endpoint accounting are different quantities. | Validation gap. Name the mass basis and stationary assumption explicitly; validate water transport and phase exchanges separately. Sedimentation is not a dry-air mass source. |
| P2 | WPS omits omega; native W is handled by a separate staged consumer under a fixed-geometry/tendency assumption. | Integration limitation. Verify the final consumed native initial state, not merely a successful WPS write. |
| P2 | OFF/HYDRO/LIQUID differ in several native initial fields and share initial W. | Attribution limitation. Their one-hour responses assess whole initialization differences, not an isolated omega effect. |

The observed-target terminology in existing interfaces must not become a demand
for an observed omega field. Existing Barnes radial-wind processing remains the
wind-analysis input; its implementation need not be duplicated.

The review found useful safeguards worth retaining: exact OFF behavior,
immutable operational-state copies, rejection before publication, a common
finite-volume/adjoint operator, explicit residual diagnostics, and the separate
native W readback checks. Successful safeguards establish their stated scope;
they do not establish precipitation accuracy or complete the missing diagnosis.

Detailed reviews: [science and meteorology](../scratch/cp02_precision_review_20260914/science.md),
[runtime integration](../scratch/cp02_precision_review_20260914/integration.md).

## Matching-time analysis comparison

The retained 12 UTC initializations were compared with the actual 13 UTC LAPS
analysis. Curvilinear bilinear interpolation uses the actual native mass-point
coordinates, pressure interpolation does not extrapolate, and all three cases
share each variable's valid mask. Comparison counts are 65,988 for surface
pressure, 65,606 for T850, and 65,464 for vapor mixing ratio at 850 hPa.

| Case | Surface-pressure RMSE (Pa) | T850 RMSE (K) | Vapor-mixing-ratio RMSE at 850 hPa (g/kg dry air) |
|---|---:|---:|---:|
| OFF | 243.263 | 0.59915 | 0.67460 |
| HYDRO | 243.364 | 0.59888 | 0.67362 |
| LIQUID | 243.435 | 0.59853 | 0.67318 |

Temperature and vapor RMSE decrease slightly while surface-pressure RMSE
increases slightly. This one-case result establishes analysis agreement only;
it is insufficient to select a superior initialization or claim an omega effect.
Surface-pressure errors also include differing terrain representations. U/V and
hydrometeor accuracy were not computed in this pass because their frame and
concentration conversions require separate matching; no proxy was substituted.

[Accuracy report](../scratch/cp02_analysis_accuracy_20260914/REPORT.md),
[metrics and source identities](../scratch/cp02_analysis_accuracy_20260914/RESULT.json),
[comparison script](../scratch/cp02_analysis_accuracy_20260914/compare_analysis_accuracy.py).

## Mathematical review extension

For the fixed-geometry Cloud-BAL increment projection, let $S$ interpolate
cell values to faces, $D$ compute finite-volume divergence, $A=DS$, $M$ be
the pressure-volume metric, and $K$ the nonnegative correction weights on the
allowed support. The implemented operators are

$$G=-KA^TM,\qquad L=-AG=AKA^TM.$$

For a requested increment $q$, the code solves $L\lambda=Aq$ and forms
$\delta v=q+G\lambda$. Consequently,

$$A\delta v=Aq-L\lambda\simeq0,$$

while the full candidate residual remains

$$r(v_b+\delta v)=r(v_b)+A\delta v\simeq r(v_b).$$

This identity explains why successful increment balance does not remove an
existing background imbalance. On the permitted support,
$\lambda^TML\lambda=(A^TM\lambda)^TK(A^TM\lambda)\ge0$; the system is
positive semidefinite, so nullspace and compatibility handling matter. Component
mean removal fixes componentwise constant modes; the graph is built from the
actual normal-operator coefficients and the uniform A-grid fixture checks its
parity components. This is not a general rank proof for every support, and it
must not be interpreted as removing a physical mass source. CR iteration limits and bounded box refinement give
finite execution and rejection on failure, not universal convergence.

An internal stationary diagnostic instead needs the selected **full-state** mass
residual to close. With fixed U/V this is an equation for the vertical flux,
with compatible boundary fluxes; a dry-air formulation must retain its dry-mass
face weights. Changing the RHS of the carrier increment projection alone is
not sufficient to establish the dry-air equation or physical boundary closure.

See [numerical equation-to-code review](../scratch/cp02_precision_review_20260914/numerics.md).
The independent [mathematical RED review](../scratch/cp02_precision_review_20260914/math_red.md)
found no face-sign, weighted-adjoint, or CR normal-operator counterexample in the
inspected source. It confirms an additional fixed-wind limitation: current
configuration requires positive U/V correction weights, so setting an omega
target does not keep Barnes U/V fixed. A restricted omega-only solve needs its
own component compatibility check; the full wind/omega operator's check is not
sufficient. The [initialization mathematics review](../scratch/cp02_precision_review_20260914/initialization_math.md)
traces the remaining local equations and operation order. The legacy findings and their isolated FORTRAN reproduction are summarized above.


The finite internal phase-transfer kernel uses a declared dry-air mixture
enthalpy, with six water species $r_s$:

$$h(T,r)=\left(c_{pd}+\sum_s c_s r_s\right)(T-T_0)+\sum_s h_{s0}r_s.$$

For a nonnegative final composition and $\sum_s\Delta r_s=0$, its temperature
update is

$$T'=T-\frac{\sum_s\Delta r_s[h_{s0}+c_s(T-T_0)]}
{c_{pd}+\sum_s c_s(r_s+\Delta r_s)}.$$

Substitution gives $h(T',r+\Delta r)=h(T,r)$ at fixed dry-air mass. This is a
well-defined local water/enthalpy constraint, not conservation of native total
energy including kinetic and potential energy. Radar analysis increments and
later pressure-geometry changes are separate operations and cannot inherit this
local conservation claim automatically. Source: `cloud_bal_column_physics.f90:
2448–2454, 2557–2600`.
