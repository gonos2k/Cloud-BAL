# Physical boundary decision after PR31

Status: **EVIDENCE_REVIEWED / BOUNDARY_RECONSTRUCTION_SELECTED / NOT_AUTHORIZED**.
Base: PR31 merge `a0ea9ccbf44b27e3f281ad2f32894c45d8a9f25b`.
This records the next research path, not a new production boundary condition.
Production Fortran, RHS, masks, solver, residual tolerances and increment caps
are unchanged. No new BALCON candidate, ON, native startup or forecast is run.

## Decision

Stop retrying the exact-active / receiver-non-worsening problem on the old fixed
face set. Select **same-case physical boundary reconstruction** as the next work,
before choosing any relaxed receiver interval or constrained optimizer. Start
with the actual surface-pressure lineage and its kinematic boundary relation;
also retain explicit lateral and finite-pressure top flux contracts. The existing
pressure-level analysis remains the primary path; moving analysis onto native
levels is not authorized by this decision.

No numerical value for a new target error, receiver allowance, boundary covariance
or source is authorized here. Available evidence does not yet justify those
values. This is a concrete restriction on implementation: retain production
rejection while reconstructing the boundary inputs and their uncertainty. Do not
introduce another acceptance switch or a new generic solver framework.

## Why the old problem is closed

PR31's arithmetic fix is `PASS_SCOPED`; keep its normal-circulation and wrong-
divergence regressions. `A=DG`, the unweighted RHS, face gate and NaN corrections
retain their previous scopes. Four of seven coupled groups fail the necessary
condition `|B-d|<=C`, where `C=sum(z_R*abs(r_before))`.

Re-evaluation of the existing PR31 report gives the receiver weighted L1 lower
ratio `|B-d|/C=2.0510985872`, or `sum_c|B_c-d_c|/C=2.0661980511` when groups are
kept separate. The positive group shortfalls sum to `72,006,356.7648804` in the
legacy weighted units. These are algebraic consequences of the old report, not
new candidate runs, kg/s, RMS ratios, energy changes or forecast scores.
For independently established active and receiver allowances, the necessary
condition is `sum_P(z*t)+sum_R(z*epsilon)>=max(0,|B-d|-C)` in each group.
The right-hand side must never be used to choose those allowances.
Adding only internal paths on the same closed union cannot remove its net defect.

## Physical equation and where it belongs

For an impermeable material surface, pressure-coordinate surface motion obeys

```text
omega_s = partial_t(p_s) + v_s dot grad(p_s).
```

It is not generally zero, even for stationary terrain. Pressure tendency alone
is not omega_s: the horizontal pressure-advection term is essential. This is a
boundary relation, not permission to insert a compensating source into the
interior pressure continuity equation. The pressure and wind must share the
same physical surface, time, frame and metric. ECMWF's pressure-coordinate
boundary derivation supplies this relation ([section 4.1, equation 82](https://www.ecmwf.int/sites/default/files/elibrary/2002/16949-adiabatic-formulation-models.pdf)).

If surface wind is adjusted while the pressure time series is fixed, impose the
coupled equation `omega_s-u_s*grad_x(p_s)-v_s*grad_y(p_s)=partial_t(p_s)`.
Its correction is `delta_omega_s-grad(p_s) dot delta_v_s`; computing a boundary
omega once and then changing its wind independently breaks this relation.
If pressure geometry also changes, rebuild the gradients, faces and equation.

No separately observed complete omega field is made a prerequisite. Pressure,
surface winds, existing radar and background can jointly constrain it, but their
errors must follow the same mapping. For time/space derivative operators H_t,
G_x and G_y acting on a pressure time-series vector, the first-order boundary
error is `delta_s=J delta_x`, with pressure block
`J_p=H_t+diag(u_s)G_x+diag(v_s)G_y` and wind blocks
`J_u=diag(G_x p)`, `J_v=diag(G_y p)`. Thus a justified input covariance gives
`C_s=J C_x J^T+C_representation` when representation error is uncorrelated
with x; otherwise its cross terms are required as well. The latter term and temporal error must be
estimated independently, not set from the incompatibility. Cross-covariances
matter because pressure/wind analyses can share background and observations.
This specifies the missing error propagation; it does not claim C_x or the
representation error is presently calibrated.

The present `terbnd` marks donor values with a sentinel; it does not integrate a
surface flux on a terrain-cut cell. A pressure row can be above ground and still
be excluded because a neighboring donor is masked. Neither that missing donor
nor a pure support face is automatically a physical ground face. A boundary
replacement must first map the physical surface to the actual discrete faces,
including all incident rows and any truncated pressure layer. Retain the old
mask until that geometry is established; do not fill sentinel values by zero.

Native dry-mass tendency is a separate relation with native flux metrics. WRF's
hybrid coordinate and C-grid require their own evaluation ([WRF dynamics](https://www2.mmm.ucar.edu/wrf/site/users_guide/dynamics.html)).
An analysis mass difference divided by an invented time interval cannot supply
either that tendency or a legacy interior source. The existing
[NATIVE_MASS_FRAME_CONTRACT](NATIVE_MASS_FRAME_CONTRACT.md) remains authoritative.

An existing Fortran helper, `set_real_numerical_test_boundaries` in
`src/common/cloud_bal_real_netcdf.f90:813–917`, already evaluates three hourly
FSF pressure samples plus surface-wind advection. Its source flags explicitly
retain `SOURCE_MANUFACTURED_TEST` because the FSF wind frame is not declared;
it also prescribes zero top omega. Do not duplicate this algebra or promote it
by clearing that flag. It requires its center pressure to match the state within
0.5 Pa. The maximum absolute difference between 13 UTC FSF `PSF` and snapshot `PS`,
after the documented array alignment, is **154.390625 Pa**, so the
FSF pressure cannot silently replace this legacy snapshot's LSX geometry.
The helper is test-only evidence, not the selected physical boundary contract.

## Actual available surface evidence

The retained six-producer case index binds hourly analyses at 12, 13 and 14 UTC
on 2026-08-16. Matching FSF files have one reference cycle, 06 UTC, and valid times
12/13/14 UTC (+6/+7/+8 h). This follow-up opened the six actual NetCDF files,
checked internal `valtime`/`reftime`, units and full 283×235 arrays, and hashed
all input bytes. Navigation metadata match within each hourly series. LSX and
FSF origin metadata differ slightly (`La1` by about 3.81e-6 degrees and `Lo1` by
1.53e-5 degrees); their cross-role subtraction below is an index-aligned
diagnostic, not proof of exact coordinate collocation. All six pressure arrays are finite and non-fill at 66,505 points.

The 13 UTC LSX `PS` array, transposed to the solver's storage order, is **exactly
equal at every point** to `snapshot.ps`. FSF `PSF` is not equal. This independently
binds the actual snapshot's pressure geometry to the analysis, rather than
silently replacing it with background pressure. The producer reads LSX `PS`
through `get_laps_2d` at [qbalpe.f](../src/balance/qbalpe.f), lines 287–293.

| Valid UTC | LSX file SHA256 | FSF file SHA256 |
|---|---|---|
| 12 | `5ad8062e404863e21e329c5139bce43b5ed1d242261e8fe60a0cec194a3410d1` | `06781a2d8e14844e26c1ec519d2880b00caf70a6cfcf196e5cb5e4259679e252` |
| 13 | `ad31e6fe7c9f42172d8c8afd5ff60b0761c13d81519f804f868b753af901014a` | `e63b6db409eecd706c09257f167203f05acb74ca2701172846f05d5a0a6c51bd` |
| 14 | `7681b61ef75aa33bfd6afd083d41c51221d24a68676076cf6b4b5652e80f52ef` | `0e39caa1086e9575980408a166d648cb04099babfb8c84dcc0eb32ef35c853b4` |

The raw central temporal difference `(p14-p12)/7200` gives:

| Field (Pa/s) | Minimum | Maximum | RMS |
|---|---:|---:|---:|
| LSX analysis temporal estimate | -0.01408746 | 0.05715386 | 0.01286303 |
| FSF raw background temporal estimate | -0.01651042 | 0.05715495 | 0.01249815 |
| Analysis minus background estimate | -0.00160482 | 0.00755859 | 0.00188084 |

These are resolved hourly temporal estimates, **not** instantaneous derivative
error bounds, sigma estimates, omega targets or permission to modify a boundary.
Successive analyses share observations/background; the one forecast cycle is not
an independent error ensemble. The RMS difference is not a calibrated uncertainty.

There is also a metadata distinction to preserve. FSF `PSF` declares
`valid_range=[0,100000] Pa`, but 40,956 / 41,188 / 41,385 raw finite non-fill values
at 12/13/14 UTC exceed that ceiling. Default NetCDF masking hides those values.
The diagnostic explicitly reads raw values and reports this conflict; it does
not repair the input contract or silently declare those cells authorized. LSX
`PS` declares `[0,120000] Pa` and all its values lie within that range. `P` in FSF
is reduced pressure, not surface pressure, and is not used as a substitute.
FSF `WSF` is labelled m/s, so it is not a Pa/s boundary omega observation.
The actual LSX U/V comments say `10m AGL`, consistent with
the original `klaps-v5.0_/src/sfc/lapsvanl.f:1102–1111`. That label does not
collocate a 10 m wind with the material surface; an explicit surface-layer/frame
mapping is still needed.

## Evidence needed before changing the problem

| Quantity or choice | What is established | What is still required |
|---|---|---|
| Pressure geometry | 13 UTC LSX PS equals snapshot PS; adjacent hours exist | Bind temporal representativeness and surface analysis error |
| Surface kinematics | The boundary equation above; finite surface wind fields exist | Exact wind frame, effective sampling height and pressure-gradient metric; collocation at the physical surface |
| Physical face mapping | Existing sentinel and support exclusions are traceable | Actual terrain-intersected face/layer mapping; signed contributions to every incident row |
| Lateral and upper flux | Current proposal is copied/frozen there | Independently justified boundary values/errors at the actual finite pressure top and outer sides |
| Objective covariance | Legacy erru/tau are available algorithmic weights | Calibrated observation/background uncertainty and correlation, including Barnes/Vr shared evidence |
| Active/receiver residual limits | Arithmetic tolerances and old obstruction are known | Discretization/representation evidence independent of the obstruction |

`erru` is a prescribed level profile, overwritten by the later assignment in
`qbalpe.f:475–495`; `tau` is based on field/scaling magnitudes (`376–389`,
`550–587`). These are not measured error samples. The 10 m/s and 5 Pa/s gates are
maximum changes, not covariance or permission. Valid COM does not establish a
calibrated air-motion uncertainty; the existing canonical sigma contract does
not retroactively certify legacy COM.

The configured Barnes radar weight is an assumed radial-velocity scale (2 m/s),
not a Pa/s COM uncertainty. The existing
[Barnes source/lineage record](CP06_A_BARNES_SETTINGS_20260911.md) also identifies
`aerr` as a dummy in the vertical-wind path. Use the original Vr and its Barnes
analysis as correlated evidence, not two independent observations. Preserved COM
producer values do not supply the missing uncertainty propagation.

## Next bounded implementation sequence

1. Bind the above physical boundary inputs to the same actual case, including
   wind frame/height, FSF metadata interpretation and uncertainty provenance.
2. Map only justified physical boundary variables into the pressure operator.
   State fixed versus adjustable faces, units, both incident rows, prescribed
   target or prior error, and total increment caps **before** computing a candidate.
   Rebuild D/G/A, geometry and compatibility checks if this changes the domain.
3. With independently specified active/receiver limits, apply the coupled
   necessary conditions, then shared-face and subset capacity constraints.
   Only a feasible policy proceeds to a predeclared weighted optimization.
4. Validate the stored total correction and downstream native state. Production
   implementation remains small Fortran routines. Diagnostics may remain outside
   production. No clipping, mean forcing removal or arbitrary interior source.

The first step is selected; steps 2–4 are not claimed complete. No presently
available uncertainty evidence permits relaxing the receiver interval today.
This decision makes the missing physical information explicit rather than
mistaking a solver retry or a new aggregate statistic for progress toward ON.

## Local evidence and limits

The isolated PR32 worktree retains `scratch/pr32_validation/`:
`inspect_surface_evidence.py`, `surface_evidence.json`, `surface_evidence.log`,
and `obstruction_arithmetic.json`. The script reads the existing case index and
actual files without writing them. Snapshot SHA256 is
`96932e53e5f30bf3e9c307617765aaa7200750ec01d4ead6b45842faf97fa661`;
case-index SHA256 is
`a842a6db01e4ebec4c516262db7a3fe1c3d27bc70ed5c3ef00924b2a315667ba`.
This is actual input/lineage inspection and time-difference algebra, not a new
physical boundary solve, Intel build, independent uncertainty calibration or
full reproduction of the upstream producer chain.
