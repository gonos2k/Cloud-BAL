# CP01 native mass/frame contract

Status: **COMPLETE / PASS** for the bounded CP01 contract and small tests. This is an adapter design,
not a writer implementation, native round-trip, or operating approval.
The actual 2026-08-16 13 UTC file identifies REAL_EM V4.6.0, C-grid, HYBRID_OPT=2,
MP_PHYSICS=37. Binary/options hashes and source gaps are in
[CP01 execution record](CP01_EXECUTION_RECORD_20260907.md).

## Analysis grid and downstream initialization

The user confirmed the existing workflow:
`pressure-level analysis -> WPS -> real (model-level initialization)`.
Cloud-BAL's primary adjustment therefore remains on pressure levels. Every
variable consumed by an analysis operator must be available at this stage with
its value, unit, mass basis and provenance; downstream initialization cannot
retroactively supply a missing analysis input. The WPS writer/reader contract
must explicitly carry the analysis outputs required by `real`.
Native staggering, EOS and KDM6 are downstream handoff and
validation contracts, not a requirement to move the analysis onto model levels.
Unresolved native provenance does not block independent pressure-level physics
implementation; it does block claims of validated native initialization.

The selected downstream microphysics is KDM6. Number and volume variables used
by Cloud-BAL analysis must likewise be represented on pressure levels, not
deferred until `real`. For all KDM6 variables, distinguish analysis inputs,
WPS-carried outputs, and fields reconstructed during `real` or later physics.
Neither six-species sufficiency nor auxiliary-field initialization may be
assumed without tracing the actual writer, reader and initialization code.

### Pressure-level handoff implementation

The existing LAPSPREP WPS writer emits `TT/UU/VV/RH/HGT/PSFC/PMSL` and, for
hotstart, `QC/QI/QR/QS/QG`. Cloud liquid is `QC`, not `QL`. It does not emit
the analyzed omega/w or KDM6 number/volume fields.

The optional `vapor_mixing_ratio` argument now writes `QV` in kg vapor/kg dry
air, including the caller-supplied surface slab. It never derives QV from RH
or fills an absent vapor input with zero. Omitting it preserves the legacy
RH-only interface. LAPSPREP now supplies it when `wps_output_vapor=true` in
`lapsprep.nl` (default false), using `SH/(1-SH)` and surface MR g/kg → kg/kg.
This path requires complete SH, MR_SFC, T3 and T_SFC read/coverage contracts,
even with legacy enforcement disabled, and forbids pressure-level SH fallback.
It is tied to the named LAPS producer mapping, not authenticated arbitrary-file
units or a coupled canonical full candidate. Legacy units attributes can be blank.

The read-only KLFS `METGRID.TBL.ARW.OML` has `QV -> FLAG_QV`. The accessible
KIM reference `dyn_em/module_initialize_real.F` also requires `use_sh_qv=true`
for direct QV vertical interpolation; its Registry default is false. Competing
SH input takes precedence in that reference. Production namelists and tables
were not changed, and the reference is not authenticated to the installed
production binary.

The actual caller passes a synthetic NetCDF regression with test grid/date
support and unused-format stubs (`tests/run_lapsprep_vapor.sh`). The six
pressure-level field checks exclude the extra surface slab; required-field
validation failures return a nonzero exit. O0/O2 QV fixture bytes match.

Remaining handoff checkpoints: connect the coupled canonical candidate (not
just the existing LAPS inputs); verify metgrid QV/SH flags and the selected
real interpolation path; independently recompute the final model-level state.
KDM6 number/volume initialization and omega/w handoff remain separate open items.

## Two mass bases, never an implicit switch

| Path | Primary mass | Water convention | Allowed interpretation |
|---|---|---|---|
| Existing pressure diagnostic | `A*cell_dp/9.80665` | represented dry-air ratios; `md=mtot/(1+rt)` | Fixed total pressure-cell mass; optional species coverage must be reported |
| Proposed native hybrid | `(MU+MUB)` and hybrid coefficients, converted from Pa with explicit native g/metric | dry-air ratios under the selected private MP37 profile | Native dry mass is already dry; no second division by `1+rt` |

In the diagnostic path, increasing `rt` at fixed pressure geometry decreases
the diagnosed `md`. It is not dry-mass conservation. In the native path, internal
phase transfer keeps `md` fixed. New water is a declared analysis increment;
physical pressure/EOS reconstruction remains necessary and is not accomplished
by preserving MU/MUB alone.

`A_Q [kg]` is the signed external analysis increment in the represented water
species. It includes only the declared `(rv,rc,ri,rr,rs,rg)` support, weighted
by the accepted dry mass; incomplete support is reported and missing species
are not zero. `A_M [kg dry air]` is a separately authorized external dry-air
increment, default zero. It excludes water loading, pressure-coordinate
reconstruction, and any inferred `MU` tendency. `A_E [J]` is the signed
external energy increment under the named convention
`CLOUDBAL_MIXTURE_ENTHALPY` below. It includes dry sensible and six-species
sensible/reference enthalpy in the before/after state difference. It excludes
internal phase-transfer, sedimentation, boundary-flux, kinetic, geopotential,
and native compressible-total-energy terms. A reduced cell enthalpy residual
cannot populate a full native total-energy PASS.

These three analysis ledgers are separate from transport, sedimentation,
boundary flux, and internal phase-transfer ledgers. In particular, phase
transfer is not latent heat to apply to temperature a second time, and
`h_diabatic` is not a J-valued `A_E` substitute. Unknown optional species are
not silently treated as verified zero water.

## Native dry-pressure algebra

Using bottom-to-top eta and `mu=MU+MUB [Pa]`:

```
pd_interface(k) = C3F(k)*mu + C4F(k) + P_TOP
dp_dry(k) = -(C1H(k)*mu + C2H(k))*DNW(k)
area(i,j) = DX*DY/(MAPFAC_MX(i,j)*MAPFAC_MY(i,j))
md(k,i,j) = area(i,j)*dp_dry(k,i,j)/g_native
```

This dry hydrostatic coordinate pressure is **not** the full physical pressure
`P+PB` used by EOS. Interface difference, coefficient thickness, and column sum
are separate algebraic checks. A future native adapter must preserve their
relationship after changes and remapping, not merely relabel pressure-level cells.
The area formula is an adapter candidate, not a complete face-flux metric or a
verified host mass integral. Upstream 4.6's physics `AREA2D` helper actually
uses `DX*DY`; its map-factor formula is disabled by `#if 0`. The actual input
has neither `AREA2D` nor `DX2D`. The source-level native integration metric is
the named `NATIVE_DYNAMICS_FLUX_METRIC`: its continuity equations carry
`MAPFAC_MX*MAPFAC_MY` in horizontal `MU` divergence, face inverse factors for
U/V, and `1/MAPFAC_MY` in `ww` (`module_small_step_em.F:1071-1130`; scalar
fluxes use `msftx*rdx`/`msftx*rdy` in `module_advect_em.F:11977-11983,
12555-12583`). The active physics field is a separate named
`AREA2D_ACTIVE_PHYSICS=DX*DY` m2 field from
`module_physics_init.F:5769-5802`, only on the active non-restart branch.

The source flux factors imply the scalar horizontal integration weight

```text
A_native_metric = DX*DY/(MAPFAC_MX*MAPFAC_MY)   ! m2
```

because it exactly cancels the `MAPFAC_MX*MAPFAC_MY` multiplier in the source
`MU` divergence. The independent asymmetric-map oracle
`scratch/cp01_final_binding_vpoe3vby/native_mass_metric_receipt.json` records
exit 0 for this weight and rejects the active `AREA2D=DX*DY` weight; its scope
is boundary-flux and interior-face algebra only, with
`native_timestep_assessed=false` (receipt SHA-256
`ecd455e16a3b22fd017abb29267328595e6153f6f23c5e02c233e4d75b37c657`). Thus the source-derived integration weight
is named and numerically checked, while `AREA2D` remains a distinct physics
field.

The oracle source is `tests/test_native_mass_metric.py` (SHA-256
`e60709256bd4e459ea94eb288f7424ec25a1289fd8ce2ed8940d3f87152f6223`) and its
hybrid helper is `tools/check_native_hybrid_geometry.py` (SHA-256
`5fe582684b35c3db0eba00975367dfcca2d0a7e11cba7a4e1f4b2b68af8af59f`).

This does not prove source-to-operational-binary equivalence, restart
provenance for the serialized metric arrays, or a complete native timestep
mass budget. The remaining ambiguity is runtime binding of this source-derived
weight, vertical/time integration and the active gravity constant. A CP02
numerical receipt must bind the chosen metric, `dp_dry`, gravity, source/build/
input hashes, and independently recompute `m_dry_cell`; the algebra receipt
cannot by itself replace the source contract or certify native execution.
The weight also does not collapse the face terms (`muu`, `muv`, `msfuy`,
`msfvx_inv`) into a scalar. Boundary loop ranges, `MU_TEND`, and exterior fluxes
remain separate terms, while `ww` and vertical continuity require their own
reconstruction and receipt.

The accessible KIM source pins `g=9.81`, `R_d=287`, `R_v=461.6`,
`c_p=1004.5`, `c_v=717.5`, `c_pv=1846.4`, `c_liq=4190`, `c_ice=2106`,
`p0=100000 Pa`, and `t0=300 K` at
`share/module_model_constants.F:17-39` (SHA-256
`5b80377fecdc18a5f0ad38d3b6c15cfc86ad5d76701adbbbb08a08698d0f7062`). Its
`epsilon=1.E-15` is numerical, not the canonical water molecular-weight ratio.
With `USE_THETA_M=1`, `phy_prep` uses
`th_phy=(t+300)/(1+(R_v/R_d)*qv)`, `p_phy=p+pb`,
`pi_phy=(p_phy/p0)**(R_d/c_p)`, `t_phy=th_phy*pi_phy`, and
`rho=(1/alt)*(1+qv)` (`module_big_step_utilities_em.f90:4699-4725`); that
intermediate `rho` is the moist-air preparation value. Before microphysics,
`solve_em.F:3665` calls `moist_physics_prep_em`, which resets
`rho=1/(al+alb)` at `module_big_step_utilities_em.f90:5398`; KDM6 receives
that field as `DEN=rho` at `phys/module_microphysics_driver.F:2527-2554`.
The inspected `solve_em.F` source hash is
`6e52d3018a9418d2635a9a5624fe903631e9b5d904151280c384e35a43099f8f`.
The latter dry-density handoff is the relevant KDM6 `DEN` meaning and must not
be inferred from the earlier `phy_prep` value. Hybrid pressure reconstruction
separately uses `qtot` and the `P+PB` coordinate (`:1036-1135`). These are named
host source formulas, distinct from the pressure-level canonical gas-only EOS
below.

The diagnostic tool requires explicit `--gravity`. Upstream WRF defines 9.81;
canonical currently defines 9.80665. The modified binary constant is unverified.
Do not globally replace either constant or infer a native mass/height equivalence.
Upstream tag v4.6.0 resolves to `0a11865f97680fdd6865b278ea29d910e5db3ed7`.
References: [WRF constants](https://github.com/wrf-model/WRF/blob/0a11865f97680fdd6865b278ea29d910e5db3ed7/share/module_model_constants.F),
[REAL_EM initialization](https://github.com/wrf-model/WRF/blob/0a11865f97680fdd6865b278ea29d910e5db3ed7/dyn_em/module_initialize_real.F#L3683),
[physics area helper](https://github.com/wrf-model/WRF/blob/0a11865f97680fdd6865b278ea29d910e5db3ed7/phys/module_physics_init.F#L5326).

The pinned upstream [microphysics packages](https://github.com/wrf-model/WRF/blob/0a11865f97680fdd6865b278ea29d910e5db3ed7/Registry/Registry.EM_COMMON#L2815)
do not define MP_PHYSICS=37. The user has now selected KDM6, and the accessible
reference tree `../KIM-meso/KIM_RDPS_MODL_V2026.2` defines package `kdm6scheme`
with `mp_physics==37` in `Registry/Registry.EM_COMMON:3238`. Its driver calls
`kdm6` at `phys/module_microphysics_driver.F:2535`. This identifies the reference
scheme, not equivalence to the operational init/forecast binaries. Source/build
binding and downstream initialization policy remain necessary for native closure.

## Adapter mapping and missing contract pieces

| Canonical meaning | Native field / transformation | Current restriction |
|---|---|---|
| absolute temperature K | serialized `T` is dry perturbation potential temperature; `THM` is moist perturbation for USE_THETA_M=1 | [Named-file binding](CP01_THETA_BINDING_20260909.md) pins T0=300, Rd=287, Rv=461.6 and proves the 2573532-cell stored relation; use physical P+PB for absolute-temperature conversion |
| physical pressure Pa | `P+PB` | Not MU/MUB or dry interface pressure |
| geopotential m²/s² | `PH+PHB`, vertically staggered | Model gravity and interpolation must be explicit |
| u / v, m/s | U x-face / V y-face | No averaging-based claim of divergence preservation |
| geometric vertical velocity m/s | W vertical face | WPS path presently has no w/omega output |
| omega Pa/s | no lossless WPS mapping | `omega=-rho*g*w` only under declared tendency/advection approximation |
| rv, rc, rr, ri, rs, rg | QVAPOR, QCLOUD, QRAIN, QICE, QSNOW, QGRAUP | Modified scheme species/number concentrations and denominator remain to be pinned |
| dry column mass | `MU+MUB` plus hybrid coefficients and source-derived `A_native_metric=DX*DY/(MAPFAC_MX*MAPFAC_MY)` | No `/(1+rt)` correction; algebra receipt is not a native executable/timestep receipt |
| domain, quality, support | explicit sidecar contract required | Missing native records do not mean metadata survived |

The retained `wrfinput_d01`/namelist branch is source/runtime-bound for this
serialized mapping: `USE_THETA_M=1`, `MP_PHYSICS=37`, and `HYBRID_OPT=2`, with
input SHA-256
`f0ccee31f6f7214c9d7b5ccf19e0ae55d9fe43751e0fcffbcaedfc6080a052e1` and
`real/namelist.output` SHA-256
`6893755a3c8ec19f2abdf03c00f79d9a961092b1f1c2c95f3704eb455e0b0095`.
`Registry/Registry.EM_COMMON:207-211` maps `th_phy_m_t0` to file `T` and
internal `t` to file `THM`; `module_initialize_real.F:4897-4918` saves the dry
perturbation before converting the selected internal field. The exact stored
relation, in float32 operation order, is

```text
THM = (T+300f) * (1f + float32(461.6f/287f)*QVAPOR) - 300f
```

for all 2,573,532 cells in the retained receipt
`scratch/cp01_theta_binding_hgb_gam_/receipt.json`. Thus the file mapping and
branch are known. This does not claim full executable/source equivalence or a
native energy/mass numerical receipt.

Current canonical ingest reverses the pressure levels, converts `sh/(1-sh)`,
and uses dry density for hydrometeor concentration. LAPSPREP now also converts
concentration with `rho_d=p/[Rd*T*(1+rv/0.622)]`, not the former approximate
moist-gas denominator. Its later omega/w approximation separately uses
`rho_g=rho_d*(1+rv)`. LAPSPREP's host `Rd` and gravity are retained, so this fixes
the mass basis without asserting identical constants or native geometry.
Both branches must still be compared from the same pre-QBAL input; an
operational absolute patch is not a lossless adapter.

The inspected local WPS writer and METGRID tables have no mapped vertical-wind
input. In the accessible KIM reference, `Registry/Registry.EM_COMMON:182–184`
distinguishes physical `w` (m/s) from `ww` (mu-coupled eta-dot, Pa/s).
The latter is not pressure-coordinate omega merely because the units match.
`module_big_step_utilities_em.F:676–775` reconstructs `ww` from native mass
continuity; bypassing that reconstruction is not an approved handoff fix.
CP06-B must verify the native reconstruction against the accepted pressure
analysis, with the actual real executable, source/build and input mode pinned.
This read-only trace does not establish coverage of every native input path.

## Frame, boundaries and locality

- Native U/V staggering and WPS grid-relative header do not establish the
  upstream analyzed-wind frame. Unknown frame is a rejection for wind changes.
- Rotation must use an explicitly oriented transformation and inverse, tested
  with uniform earth-relative wind and a nonzero rotation angle. No angle or
  zero rotation may be guessed from a field label.
- Top flux and bottom `dps/dt + v_s·grad(ps)` must belong to the same model cycle,
  valid time and frame. Copied interior or manufactured boundary has no
  observational authority. Stored P_TOP is not proof of a zero-flux boundary.
- Pressure diagnostic adjacent partial-face support is the pressure-interval
  intersection, not average cell thickness. The pressure-diagnostic balance
  now uses sparse cross-level intersections in D/G, component labeling and final
  residuals. Native C-grid face DOFs, mass metrics/map factors and remap remain
  separate CP03 work; this is not native compatibility approval.
- No-authority state is a valid no-op. Missing required input, uncertain units,
  species coverage or frame must reject the candidate, not shrink the domain.

## Exit evidence still required

Modified-host source/registry/constants and MP_PHYSICS=37 definition; complete
species/number-field coverage; actual upstream frame and boundary contract;
independent partial-face/thin-cell and asymmetric mapping tests. The small
hybrid algebra diagnostic supplies only one part of these requirements.
CP01 cannot close and CP02 cannot claim a native handoff from this document alone.

## Follow-up: upstream LW3 source frame

The local `klaps-v5.0_/src/include/main_sub.inc:48–51` sets all four
`l_grid_north*` constants true, including `l_grid_north_out`. The selected
`src/wind_openmp/main_sub.f:110` includes that file. Its output-rotation branch
at line 521 requires `.not. l_grid_north_out`, so that source configuration
leaves analyzed U/V grid-relative at the LW3 writer (lines 727–756).
`src/lib/conversions.f:1144–1214` supplies the rotation and inverse; in its
convention `u2=u1*cos(a)+v1*sin(a)`, `v2=-u1*sin(a)+v1*cos(a)`.

This is source-level evidence, not a new authentication of the completed Barnes
binary or a new release test. The actual 13 UTC `final_ordered` LW3 attributes
do not encode a frame. The receipt `scratch/cp01_frame_trace.ig53avsk/receipt.json`
pins seven source files and that input before/after, without changing them.
Its scope explicitly leaves binary/source equivalence and FSF frame unresolved.
Do not turn these source constants into automatic observational authority.

The adapter contract should therefore carry a producer/build-bound frame
receipt; an unknown or conflicting frame must reject wind changes. A WPS
GRID_RELATIVE header is consistent with this source configuration but cannot
establish that the particular upstream bytes passed through it.

## Modified-host source locations discovered in binaries

Static inspection finds `KIM-meso_v0.9.5` in the current forecast binary's
embedded `set_timekeeping_alarms.inc` path, and `klbg_v0.9.4.1` in the init
binary's corresponding path. Exact paths and Build IDs are retained in the
CP01 execution record and `scratch/cp01_host_trace.hibfq2e0/receipt.json`.
These are external build-path clues, not accessible source pins or proof of
incompatibility. Both modified trees and their build relationship are needed;
substituting one upstream WRF tag for both is not an acceptable source receipt.

## Standalone cloud-thermodynamic column transaction

`saturation_adjust_column` uses explicit, fixed dry-air mass (kg) to weight
internal vapor/liquid/ice changes. Pressure is in Pa, temperature in K and
species in kg/kg dry air. All selected cells commit together; any failure
leaves every state vector unchanged and returns an empty budget. Unselected
values are opaque, including missing values. A valid empty selection is a no-op.

The cloud-only cell/column APIs specialize the six-species mixture law below
with zero precipitation. Their budget reports signed species kg and sensible/
phase enthalpy J; positive phase change is not heating or an external energy
increment. They do not imply precipitation transfer, EOS refresh or native
energy closure. These APIs are not called by the normal pipeline.

## Pressure-level gas EOS and phase-policy boundary

The shared canonical EOS uses dry-air vapor mixing ratio `rv`:
`rho_d = p / [287.05*T*(1+rv/0.622)]` and `rho_g = rho_d*(1+rv)`.
Species concentration/flux uses `rho_d`; omega/w conversion and the current
pressure-thickness trajectory/loading approximation use `rho_g`. The former
`T*(1+0.61*rv)` conversion and dry-density pressure thickness are no longer used.
The helpers accept the canonical p/T/rv domain, including the stored float32
upper vapor endpoint. They compute from supplied T/rv on every call, not a cache.

This is a gas-only ideal EOS, not total condensate-loaded density or a native
EOS refresh. It does not update pressure, geopotential, mass tendency or copied
dynamic targets. The hydrostatic omega/w relation still omits pressure time
tendency/advection; native constants and model-coordinate metrics remain separate.

The mixture-enthalpy saturation APIs require an explicit liquid or ice surface
on every selected cell. Liquid exchange can cross 273.15 K without freezing
supercooled liquid. Ice exchange stays at or below 273.15 K; an infeasible warm
ice root is rejected atomically, not switched to liquid. Exhausting one reservoir
never authorizes exchange with the other. This replaces the initial-temperature
selector and its secondary-reservoir fallback. It is not mixed-phase equilibrium
or a KDM6 freezing/melting rate model.

In the accessible KIM reference, `module_microphysics_driver.F:2553` binds
`XLS=xls, XLV0=xlv, XLF0=xlf`: 2.85e6, **2.50e6**, 3.50e5 J/kg.
Do not confuse that argument with the unrelated same-named global XLV0=3.15e6.
KDM6 initializes its local `xlv1=cliq-cpv=2343.6` and uses temperature-dependent
latent feedback and rate/subcycle-dependent mixed-phase processes. Copying these
constants into the Cloud-BAL budget alone would not reproduce KDM6.

## Explicit six-species phase-transfer candidate

`apply_water_phase_transfer` and `apply_pressure_phase_transfer` accept prescribed
internal dry-mixing-ratio increments in the order `rv, rc, ri, rr, rs, rg`.
They do not select a saturation surface, infer a phase from temperature, or decide
the rates/amounts of condensation, evaporation, sublimation, melting or freezing.
Those require the caller's physical/provenance contract. In particular, a
conservative prescribed freezing increment is not proof that freezing is
physically permitted at that temperature or on that time scale.

For both saturation and prescribed transfers, use `T0=273.15 K`, `cpd=1004.5`, and species heat capacities
`[1846.4,4190,2106,4190,2106,2106] J/(kg K)`. Species reference enthalpies at T0
are `[2.50e6,0,-3.50e5,0,-3.50e5,-3.50e5] J/kg`. These reference-source constants
are fixed for the research convention; installed native binary provenance is
still unresolved. With `c_j` and `h_j0` denoting these arrays:

```
h_d(T,r) = (cpd + sum(c_j*r_j))*(T-T0) + sum(h_j0*r_j)
r_new = r + delta_r
T_new = T - sum(delta_r_j * [h_j0 + c_j*(T-T0)]) / (cpd + sum(c_j*r_new_j))
```

The finite-transfer solve preserves fixed dry mass, total water and this
isobaric mixture enthalpy, including condensate heat capacity and the temperature
dependence of latent enthalpy differences. The old reduced-enthalpy solver and
diagnostic have been removed, not retained as another physics path. This does
not assert numerical identity with KDM6 rates or native compressible total energy.

`saturation_adjust_mixture_cell` solves exchange with the explicitly selected
cloud liquid or ice reservoir. Other species remain unchanged but contribute
heat capacity. With transfer `e` from the selected reservoir to vapor,
`C = cpd + sum(c_j*r_j)`, `dc = cpv - cp_selected` and
`L(Ti) = h_v(Ti) - h_selected(Ti)`, the trial temperature is
`T(e) = Ti - e*L(Ti)/(C + e*dc)`. The bounded scalar root uses the existing
empirical water/ice saturation curves, not KDM6's `fpvs` or rate subcycling.
Temperature and vapor bounds are not reservoir exhaustion. The accepted root
is committed by the same finite-transfer kernel used for prescribed transfers.

Both pressure APIs share one candidate-publication routine and the same
`water_phase_budget`. They require all six species on the explicit support and
commits all selected cells together. It recomputes signed species kg and sensible/
phase J changes from final float32 values using input dry mass, gates storage
roundoff separately, and validates the final canonical state. Saturation also
rechecks its final vapor residual: the float64 root uses a 1e-11 kg/kg absolute
tolerance, while the storage gate brackets saturation over one float32 epsilon
of temperature and vapor. A remaining reservoir cannot excuse subsaturation.
External water
increments, overdraw, malformed selected inputs or temperature-range failure
reject the entire candidate. Unselected increments are opaque and unchanged
metadata/winds/pressure geometry/support are preserved. No silent clipping or
dry-mass recalculation is used to hide a failed budget.

The standalone pressure APIs do not refresh copied targets, terminal-speed
diagnostics or state-dependent forcing. Their caller must do that explicitly.

## Explicit pressure-thermo SHADOW route

`derive_column_physics` and `run_cloud_bal_pipeline` now accept the all-or-none
optional tuple `thermo_active`, `thermo_surface`, `target_rh`. Without it, existing
callers do not request thermodynamic adjustment; an empty mask leaves the usual
cloud/radar processing unchanged. Selected cells require valid six-species water
coverage. OFF remains an exact no-op. No operational configuration is enabled.

The ordered path publishes the radar hydrometeor proposal once, freezes its
analysis-increment diagnostic, applies internal saturation adjustment, and then
recomputes omega/w, loading and terminal-speed diagnostics from final stored
T/vapor/species. Original echo and reconstruction lineage are retained, rather
than inferred from generated fields. Loading uses only direct echo cells;
original authorized omega targets are preserved. Generated diagnostics retain
their uncertainty and never acquire dynamic authority. The existing empirical
terminal speed is not a validated PSD-based reflectivity-weighted operator.

The accepted six-species `thermo_budget` is separate from radar analysis and
interface-throughput diagnostics. A failure in thermo, localization or balance
rolls back the candidate and accepted thermo budget; the operational state is
always the input. Generated temperature/vapor cannot re-enter as pristine input.

The default remains one ordered pressure-level pass. Setting pipeline
`maximum_outer_iterations` to 2–32 instead requests a bounded, undamped fixed
point. Each trial evaluates radar density, phase partition and trajectory using
the preceding candidate's T/vapor/u/v/omega, but rebuilds precipitation, analysis
budgets, thermo and balance from the same immutable original state. Evaluation
states must retain the original pressure geometry and observation contracts.
No precipitation or wind analysis increment is accumulated between trials.

Acceptance requires exact equality of the five stored feedback fields on the
pressure domain, in addition to the existing stage gates. Quantization cycles or
cap exhaustion reject the candidate; a single pass makes no convergence claim.
This closes only a pressure-fixed evaluation map, not PSFC/geopotential/native
dry-mass coupling or physical time integration. Damping, physical rate selection,
native handoff and science promotion remain separate work. Accepted explicit
thermo outer results use schema 8 rather than the single-pass schema 7 identity.
The writer replays the bounded producer from immutable input before storing the
candidate and iteration metadata; this is not an independent solver oracle.

## Pressure-fixed analysis mass accounting

The pressure proposal now returns a separate `pressure_analysis_budget`, before
internal phase changes. For each represented species it records
`ma*ra-mb*rb = mb*(ra-rb) + (ma-mb)*ra`, plus dry-air mass change and the residual
of dry-air plus represented-water mass (global and maximum cell residuals).
Thus unchanged vapor mixing ratio does
not imply unchanged vapor mass after a pressure-fixed radar increment.
`accounted_cells` and incomplete-species coverage counts distinguish an empty
budget from complete represented coverage; missing condensate is not observed
zero. The accepted budget is cleared on pipeline failure and OFF is unchanged.
The same pre-thermo ledger records `enthalpy_change_j = sum(ma*ha-mb*hb)` using
the mixture enthalpy convention of the internal phase block. This includes the
dry-air and vapor contributions; it is an external analysis increment, not
latent heat to apply to temperature again. Its signed value is not an energy
conservation error. This ledger is neither transport nor native dry-mass/total-
energy conservation. Explicit thermo diagnostics carry it as described below;
native PSFC/EOS reconstruction and coupled outer convergence remain required.

## Pressure-thermo diagnostic serialization

The default no-thermo writer contract remains schema 5. An accepted nonempty
single-pass thermo request uses schema 7 (`real_radar_thermo_shadow_v2`), retaining
`DIAGNOSTIC_PROPOSAL_ONLY` authority. It stores background/candidate T and vapor,
seven-field value/valid/quality/source/time information, explicit support and
surface/RH, candidate dry mass, and separate analysis and internal-phase kg/J
budgets. Analysis metadata includes the ratio/denominator split, incomplete
coverage counts and cell/global mass residuals. Existing
background dry mass is not relabeled as candidate mass.

The writer does not widen general state equality. It reconstructs the pre-thermo
proposal from background T/vapor/cloud species and final precipitation (unchanged
by the selected saturation operation), checks the analysis ledger, then replays
the requested transfer and compares the accepted state and phase budget.
The separate Python verifier recomputes stored-array analysis increments,
water, mixture enthalpy and saturation constraints without importing
the Fortran implementation. No-echo still blocks precipitation and unrelated
diagnostic changes; it does not assert that cloud water or vapor must be zero.

Legacy schema 6 (`real_radar_thermo_shadow_v1`) remains readable, but neither
schema 5 nor 6 certifies a persisted analysis ledger. The new ledger's contract is
`pressure_fixed_represented_mixture_v1`; its numbers are not observation authority.

Schema 8 (`real_radar_thermo_shadow_v3`) adds
`pressure_fixed_feedback_producer_replay_v1`: configured cap, executed count,
convergence and per-trial maximum absolute changes of T/rv/u/v/omega. Differences
are computed in float64 from stored float32 values over `above_ground` cells.
The flat float64 attribute stores five components per trial, in that order;
units are K, kg/kg dry air, m/s, m/s and Pa/s. No mixed-unit residual norm is used.
The accepted last trial is exactly zero; preceding trials must be nonzero.
Unused in-memory history is zero and producer replay checks it as well.

Python checks the stored lineage structure plus the existing independent phase,
analysis and continuity identities. Its `outer_fixed_point_independently_validated`
remains false: it does not replay the complete radar/trajectory/balance map or
authenticate a producer's history. Independent final-map recomputation and
self-contained input/config provenance remain required before CP06-A closure.

This file is a pressure-level diagnostic proposal, not a complete native initial
state, a production generation, KDM6 rate integration, or science approval.
The pressure-fixed external analysis mass and six-species `A_E` policies are
defined above; full native coupled execution, runtime source/build identity,
and native total-energy closure remain separate requirements. Serialization does
not close those physical contracts.

Schema 8 may additionally carry `pressure_radar_reconstruction_v2`, the actual
`column_minimum_dbz`, and original precipitation phase/value-valid-quality-source
inputs. This complete group permits independent Python recomputation of final
rain/snow/graupel and each interface-throughput ledger category from stored final
T/rv/u/v/omega and original radar/geometry. A partial group is rejected; genuine
older schema-8 files remain readable without the independent-radar claim.
`radar_reconstruction_independently_validated` does not certify the entire outer
fixed point, a physical trajectory, finite-time mass transport or native handoff.
Version 2 uses frozen-source continuous-position layer segments and endpoint-only
bilinear deposition; the reference evaluates the endpoint analytically. Version 1
described the defective source-grid substep remap and is rejected by the new
reference gate rather than silently interpreted as version 2. Schema-8 files
without either reconstruction group remain readable without this claim.
Within-layer shear integration, physical trajectory and native validation remain
separate open requirements.

## Pressure-target uncertainty (2026-09-08)

Canonical schema 4 adds `omega_target_sigma`, one standard deviation in Pa/s.
Valid errors must be finite and positive, with matching grid/time/units and
usable provenance sharing dynamic evidence with the target. Missing error is
valid absence of authority; malformed declared error is rejected. Cloud type
and reflectivity do not manufacture an error estimate. Target permission is
separate from whether its innovation is numerically nonzero.

The observational research block assumes diagonal errors in the same pressure
coordinate and mass inner product as the existing balance objective. For
`B = beta*kappa_omega`, `R = sigma**2`, and innovation `d`, completing the square
in `delta**2/B + (delta-d)**2/R` gives proposal `B*d/(B+R)` and inverse metric
`B*R/(B+R)`. The normal solve and published correction use this same metric.
Manufactured-test authority retains its explicit old metric and remains barred
from the normal pipeline. A finite constant sigma is not an old-solver bypass.

New diagnostic files declare `diagonal_pressure_omega_v1` and persist sigma with
valid/quality/source/time metadata. Canonical-3 historical diagnostics remain
legacy evidence without this error-contract claim. Numeric sigma/source bits
alone do not prove calibration, frame conversion, independent observations or
uncorrelated errors; real dynamic-target and native/science approval remain open.

The default real-radar diagnostic writer still accepts copied boundaries only,
and its default validator disallows nonzero dynamic corrections. The uncertainty
stage alone did not close dynamic E2E; the subsequent explicit extension below
preserves that default restriction.

## Opt-in pressure candidate diagnostics (2026-09-08)

`pressure_analysis_candidate=.TRUE.` selects the exact
`pressure_analysis_candidate_v1` extension. It stores immutable original target
value/valid/quality/source/time, preserves physical boundary arrays without
retagging, and replays the pipeline before writing. The independent Python path
checks target identity, sigma authority, localization, final continuity and
increment residuals, solver response and acceptance. Physical input provenance
is not a claim that actual boundary observations or their frame were verified.
Default radar-only consumers remain unchanged and cannot accept this product
as their existing generation or operational output.

The positive fixture uses paired opposite omega targets matching a represented
interior-u divergence mode, with unchanged sigma=0.5 Pa/s and default gates.
The uncompensated single target remains a rejection regression. This is a
feasible-mode diagnostic round-trip, not arbitrary-target/parity closure, full
coupled outer-map validation, actual observations or native/science approval.

Joint schema-7/8 fixtures additionally exercise simultaneous T/vapor/cloud-water
and nonzero wind changes, with immutable operational output. The writer's
producer replay compares column/balance numerical receipts, not only final state
and outer history; a balanced but fabricated flux ledger is not valid lineage.
This remains pressure-fixed five-field feedback. Species-dependent balance
metrics and independent verification of the full nonlinear map remain open;
producer replay does not replace either requirement.

### Dry-air advective flux on pressure faces

`state_dry_air_mass_flux_divergence` computes signed net dry-air outflow in
kg/s on active cells using the existing pressure-face topology. Interior faces
interpolate the conserved carrier product `f_d * velocity`, where
`f_d = dry_air_mass_measure / pressure_mass_measure`; the pressure projection
and its metric are unchanged. Domain boundaries extrapolate composition from
the adjacent cell, an explicit assumption rather than an observed composition.
Condensate changes the represented dry fraction but supplies no dry-air
sedimentation flux. The routine rejects inconsistent stored dry mass.

This supplies `D F_d` only. Closing `dot(m_d) + D F_d` still requires a physical
mass tendency and boundary contract. The pressure-fixed analysis difference
`analysis_budget%dry_air_change_kg` must not be divided by an invented time interval or treated as dry-air
production. Native mass-coordinate reconstruction remains a separate step.

Joint pressure-candidate schemas 7/8 persist background and candidate `D F_d`
as float64 `kg s-1` arrays under `pressure_fixed_dry_advection_v1`.
`nearest_interior_composition` identifies the boundary assumption, and
`dry_air_mass_tendency_assessed=0` prevents a flux-only continuity claim.
The independent reader reconstructs pressure-overlap faces from stored geometry
and dry fractions from each stored state's mass measures. Historical artifacts
without the entire optional extension gain no independent dry-flux claim;
partial or malformed extensions are rejected.

Flux replay tolerances include a float64 roundoff bound based on the sum of
absolute donor contributions before interpolation/cell cancellation, not just
the signed net residual. For `n` incident contributions, the bound is
`2*gamma(n+10)*sum_abs_donors`, with `gamma(k)=k*u/(1-k*u)` and `u=eps64/2`.
This accounts for independent arithmetic ordering and the producer's cell-mass
normalization. It is a numerical replay allowance, not a physical budget or
forecast acceptance tolerance.

## Pressure-level hydrostatic geopotential increment

`hydrostatic_geopotential_increment` integrates the change in `p/rho_total`
between fixed pressure centers, using a trapezoid in `log(p)`:
`deltaPhi[k+1]-deltaPhi[k] = mean(delta(p/rho_total))*log(p[k]/p[k+1])`.
The canonical ideal mixture gives
`p/rho_total = Rd*T*(1+rv/epsilon)/(1+rv+rc+ri+rr+rs+rg)`.
All species are explicit dry-air mixing ratios; the routine does not fill
missing condensate with zero. It leaves its output untouched on rejection.

The lower represented center is the declared zero-increment reference. This
is not a measured surface anchor. Adding this increment to an original Phi
would preserve that original column's discrete hydrostatic residual rather
than rebuild its absolute geopotential. It does not preserve native dry mass,
reconstruct PSFC or impose the nonhydrostatic model's coordinate relation.
The distinction between full-mixture density and native dry hydrostatic
coordinates follows [ARW equations 2.15–2.16 and discussion](https://www2.mmm.ucar.edu/wrf/users/docs/technote/v4_technote.pdf).

`apply_pressure_hydrostatic_increment` now attaches this increment to a pressure
candidate using explicit geopotential support and reference-level arrays. A
selected column must name its lowest represented center as the fixed original
Phi reference, have complete usable mixture/Phi inputs, and retain original
pressure geometry and unadjusted Phi values/quality/source. Empty requests also
check pressure geometry identity before returning a no-op. Any mathematical increment outside the
authorized support rejects the whole candidate, before float32 rounding. Only
Phi values/source bits change; the reference and outside-support state remain
unchanged. The stored column must retain increasing Phi with height.

The pipeline accepts these two explicit request arrays together, applying the
stage after thermo and before localized balance. Neither `thermo_support` nor
`hydro_support` grants this permission. Every outer trial starts from original
Phi, so increments never accumulate across iterations. Omitted requests preserve
the old path, OFF preserves the original, and failed candidates retain no request.
`SOURCE_COLUMN_PHYSICS` records derived Phi; it grants no new wind authority.

Pressure-candidate diagnostic schemas 7/8 can now persist the optional
`pressure_hydrostatic_increment_v1` contract: background/final Phi with field
metadata, explicit support and one-based lowest-center references (zero in
inactive columns). The producer replays the request before creating the file;
missing requests still require unchanged Phi. Historical diagnostics without
this extension acquire no Phi-validation claim.

The independent Python verifier recomputes the increment from saved pressure,
temperature and all six water species, including final float32 storage. It
checks complete selected columns, mathematical support before rounding, fixed
references, provenance and monotonicity. Phi changes belong in the overall
change mask, not in the separate column-physics mask. Manufactured sources do
not gain diagnostic authority through this extension. These checks establish
the represented pressure increment only, not a full-state scientific gate.

The reader still discards surface topography after domain construction. A
physical surface anchor, total-energy/native dry-mass closure and WPS/real
handoff remain separate work. Stage-local balance geostrophic diagnostics still
start with adjusted Phi; they must not be interpreted as original/final metrics.

The optional `pressure_geostrophic_original_final_v1` diagnostic now compares
immutable original and final Phi/u/v using the same pressure geometry and
validation region: balance support union explicit Phi support, plus one
same-level four-neighbor halo intersected with the represented domain. Hidden
wind/Phi changes outside their declared supports are rejected. The writer
computes the pair before creating a file; Python independently replays both
RMS values from the stored arrays. Historical files receive no new claim.
This is a force-residual diagnostic, not a geostrophic acceptance threshold,
coordinate-provenance certificate, full energy measure or native/science gate.
In particular, legitimate convection is not forced into geostrophic balance.

The v2 geostrophic diagnostic preserves that requested validation support and
adds a separate `geostrophic_stencil_support`, requested/evaluated cell counts,
and an explicit partial-coverage flag. Only terrain geometry can remove cells
from the evaluated subset; invalid represented data remains an error. Original
and final RMS values refer to full states on the evaluated subset, not full
requested coverage. A nonempty request with no evaluable cells is rejected.
The v1 reader contract remains strict and backward compatible. Neither version
grants native or scientific acceptance, including when evaluated RMS decreases.

### Isolated pressure-candidate to WPS array mapping

`cloud_bal_wps_adapter` maps a complete canonical candidate into an explicitly
supplied WPS inventory. Pressure coordinates must match exactly after hPa/Pa
conversion; either monotone order is supported without sorting or dropping
levels in memory. Because the legacy writer skips levels above 100100 Pa,
such levels are permitted only when the validated candidate `above_ground`
mask is false at every cell on that level. Any represented cell causes
rejection; the adapter never shrinks the analysis domain to obtain acceptance.
Candidate T/u/v, Phi divided by 9.80665, vapor and five hydrometeors replace
represented pressure cells. Dry-air mixing ratios are copied without another
mass-denominator conversion. Candidate PSFC and surface air temperature are
mapped; supplied subterranean fills, surface vapor/winds/height, SLP, skin
temperature and snow cover are retained. Missing ancillary arrays are not
synthesized. RH is retained but is not authoritative when explicit QV is used.

The caller must explicitly declare the candidate wind frame; this version only
accepts matching grid-relative winds and does not rotate them. This declaration
is not independent frame provenance. Mapping has no I/O, and failed mapping
preserves the existing output inventory. Isolated tests pass its output through
the existing WPS writer and independently read the records in both level orders.
The operational caller is unchanged. Actual producer/writer metadata binding,
omega handling, modified-host source and real/native initialization remain open;
this array bridge is not a full native product or FG1 completion.


## WPS reference wind-rotation ordering — 2026-09-11

The official WPS v4.6.0 reference first interpolates U/V onto their target
staggerings, rotates each source contribution to Earth-relative winds using
its source projection, and finally rotates to the destination grid frame.
On the C grid, each rotation obtains the cross-component by masked averaging
of adjacent staggered points. Equal Lambert projection parameters therefore
do not establish that the two discrete rotations cancel. A wind readback must
preserve the interpolation/rotation order and the participating masks.

Source locations are `process_domain_module.F:1279,1409,814` and
`rotate_winds_module.F:23–71,225–257,334–362`, retained with URL/SHA-256 in
[scratch reference sources](../scratch/cp02_wps46_reference_o_li4mqe/SOURCES.json).
This is a source-reference constraint on the comparison method. The retained
operational executable has no matching build receipt; numerical agreement
with its outputs and native divergence preservation remain unverified.


The subsequent [saved-pair U/V reconstruction](../scratch/cp02_wps_scalar_interp_nfjuake1/WIND_INTERPOLATION_ROTATION.md)
at 100000 Pa measures interior RMS errors of 8.63e-5 and 9.52e-5 m/s after
both rotations, compared with 7.02e-4 and 7.98e-4 m/s from interpolation
alone. The comparison excludes two edge cells, includes supplied below-ground
values, and assumes valid interpolation masks for the checked finite slabs;
operational modified masks are not serialized. This supports the discrete
rotation ordering for that case, but does not close all-level masks, native
vertical interpolation, or divergence/mass preservation.
