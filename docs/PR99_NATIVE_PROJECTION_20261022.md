# PR99 — a native U/V transfer proposal and its first response

The frozen C1 OFF/HYDRO/COUPLED 600-second results remain the baseline. This
experiment changes the additional COUPLED−HYDRO wind in the actual native
control space. It is a research input proposal, not a replacement approved
for forecasting.

## Control and reference

The pressure producer with omega fixed fails its component compatibility
condition before iteration ([pressure audit](PR99_PRESSURE_TRANSFER_20261022.md)).
The native proposal instead starts from the initialized HYDRO reference and
projects only the additional native U/V onto a frozen-carrier horizontal
dry-flux divergence kernel at each of the 39 levels. The reference has
nonzero atmospheric motion and divergence.
Nonzero native mass tendencies are permitted; their size alone does not
establish a violation of the native continuity equation.

Controls are the 364 interior faces per level of the predeclared five-cell
QC buffer (196 mass columns). A face is free only when both adjacent columns
belong to the buffer; its boundary increments are fixed at zero. The nearest
additional wind is found with a small sparse linear least-squares projection.
This uses an equal-face velocity norm, not an energy or complete momentum
objective. It preserves about 95.8% of the original additional-wind L2 norm.
The applied stored-wind displacement has norm 30.381 m/s, or 28.77% of the
original additional-wind norm. Its maximum absolute changes are 1.744 m/s
for U and 1.872 m/s for V, with no assumption of co-location. The
[stored-array calculation](evidence/pr99_native_projection_20261022/wind_displacement.json)
records the three input hashes and formula. Observation preservation remains
unverified.

Face dry mass, hybrid coefficients and map factors follow `calc_ww_cp`'s
source order. A solver residual gate precedes REAL32 storage. Storage error
is reported separately. The proposal changes only U/V; all other 206 stored
variables, variable metadata and global attributes match the C1 parent.
Pressure omega is not assigned to W. The archived native consumer confirms
the stored proposal's initial mass-coordinate `ww` is near HYDRO: support
RMS difference `1.05e−6 Pa/s`, maximum `4.12e−6 Pa/s`
([consumer replay](PR99_NATIVE_WW_CONSUMER_REPLAY_20261022.md)).

## Receipt-closed native response

One 20-second integration completed with the same `e9195181…768f1` diagnostic
executable, boundary, physics and FP policy used by the original three-arm
20-second captures. Its candidate is `10aff32b…d75cb3`. All 57 response
snapshots are hash-bound to the closed receipt; the unchanged generator,
parent, reference, boundary and staged input are checked. This reuses the
original OFF/HYDRO captures, not a different model for those references.

| Fixed support metric | HYDRO | Original C1 COUPLED | Native proposal |
| --- | ---: | ---: | ---: |
| Observed dry-column mass-rate L2, kg/s | 17,899,337 | 383,305,796 | **15,276,841** |
| Assembled RU L2, source units | 24,361.966 | 41,212.461 | **37,999.028** |
| Assembled RV L2, source units | 23,908.715 | 34,050.805 | **33,199.724** |

The physical mass-rate measure uses the captured MU update, native map area,
hybrid sensitivity and pinned gravity
([measure and limitations](PR99_NATIVE_DRY_MASS_RATE_20261022.md)). RU/RV are
kept in their own source-coordinate units; they are not combined into an
acceleration or energy norm.

The pinned capture hook follows `rk_addtend_dry`. Conditional boundary
updates and small-step preparation follow it before `advance_uv`; that
routine updates coupled perturbation winds. The later
`small_step_finish` call receives separate updated face carriers
`MUUS/MUVS` and hybrid coefficients. The capture does not retain all of
those quantities at the restoration boundary. Dividing the captured RU/RV
by the initial column mass therefore does not establish the actual
physical wind acceleration. No such conversion is used in this report.

Relative to original COUPLED, mass-rate L2 decreases about 96.0%, RU 7.8% and
RV 2.5%. RU/RV remain **1.56/1.39 times HYDRO**. Thus, matching the native
mass-flux degrees of freedom materially improves this mass response but
does not establish that the additional wind correction improves complete
momentum balance. The reference pressure-gradient/Coriolis pair alone still
does not represent the assembled dynamics.

The selected V-advection increment relative to HYDRO decreases from about
19,487 to 16,728 source units, while the horizontal-diffusion increment
increases from 18,712 to 19,938. These vector norms cannot be added as
independent contribution percentages. They help locate the remaining
momentum response after the mass constraint is matched.

## Decision and scope

Keep this candidate as a bounded experiment; preserve the original C1
baseline. The 20-second result does not establish 600-second stability,
reduced initial shock, cloud-signal preservation or observation skill. It
does not close the first grouped rejection after 620 seconds. Physical
approval remains **`FAIL_OPEN`** and observation skill **`NOT_EVALUATED`**.

The [closed response](evidence/pr99_native_projection_20261022/response.json),
[receipt](evidence/pr99_native_projection_20261022/closed_receipt.json),
[proposal](evidence/pr99_native_projection_20261022/proposal.json) and
[provenance](evidence/pr99_native_projection_20261022/provenance.json) bind
the actual inputs, source and output summaries. Field arrays remain private.
The opt-in runner accepts this proposal only for one COUPLED 20-second
diagnostic step; it cannot silently replace a HYDRO input or extend the
experiment into a longrun.
