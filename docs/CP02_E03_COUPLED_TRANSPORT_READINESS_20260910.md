# CP02 E03 coupled transport readiness

## Execution plan refresh — 2026-09-14

The [model-dynamics experiment](CP02_MODEL_DYNAMICS_INCREMENT_EXPERIMENT_20260914.md)
now has accepted actual pressure-analysis O0/O2 results and unchanged-scalar
WPS/metgrid/real comparisons. Native W transfer v1 remains rejected at the
near-terrain support boundary. Source-bound surface reconstruction v2 now passes
actual Intel consumption and corrected independent readback under its declared
fixed-geometry contract. These results do not close #4/E03 or
replace the original coupled validation requirements.

The [CP02 plan](CLOUD_BAL_FINAL_GOALS_CHECKPOINTS_20260907.md#cp02--실행통합-기반-upstream--full-ifx--off결합-후보-native-왕복)
retains all six requirements. Carry forward #1/2/3/5/6 evidence within its recorded
source/input/configuration scope; #4 and E03 remain open. Physical cloud-omega
implementation and CP06-A isobaric validation precede acceptance of the actual
coupled candidate through WPS→metgrid→real. Reuse that same bound readback in
CP06-B; its additional integration/startup requirements remain separate.

The [12/15 UTC OFF preparation](../scratch/cp02_native_12_15.B4Lwmh/RUN_REPORT.md)
records metgrid/real exit 0, a 12 UTC initial state and 12→15 UTC boundary coverage,
with unchanged source inputs. This pins the copied executable identities, not
metgrid's exact build source. It does not establish a forecast, a physical omega
driver or actual coupled candidate ingestion. Existing observations are already
available and consumed; missing physical generation/authority must not be
reported as missing observation files.

The [cold-guard full-host diagnostic](../scratch/cp02_native_current_run_95gbqi4y/RESULT_RUNTIME.json)
passed the previous cold-rate location but stopped in radar reflectivity with
positive rain and zero rain number. A private `do_radar_ref=0` run (lightning off)
then stopped in graupel melting; its [receipt](../scratch/cp02_native_no_reflectivity_engdfdhc/RESULT_RUNTIME.json)
verifies all 86 input hashes and exact initial W preservation. Neither run
completed the first timestep. This diagnostic switch does not initialize the
missing number moments or establish physical cloud omega.

## Defined graupel diagnostics and melting domain — 2026-09-14

The [melting patch](../patches/kdm6_graupel_melting_domain.patch) requires positive
available density before the entire graupel melting mass/heat/volume update.
It also changes partially assigned `ProgB_param` diagnostics to `INTENT(INOUT)`:
the caller initializes them and repeated calls retain the same cell's values.
The existing [initialization patch](../patches/kdm6_diagnostic_initialization.patch)
removes the earlier read of an undefined output. No density prior is added;
a retained positive density is a numerical cache, not proof of observed moments.

[Fresh Intel O0/O2 module tests](../scratch/cp02_graupel_defined_o5ecgopm/RESULT.json)
pass seven cases. The original fails two warm small-mass/zero-volume cases;
five logged controls, including small mass with defined volume, match exactly.
The candidate's logged O0/O2 results agree. Existing final trace-mass padding
remains; full-routine trace-mass conservation is not claimed. A numerator-only
melting guard failed the reproducer and was not promoted. The [melting-only full-host run](../scratch/cp02_native_melt_defined_4curzml2/RESULT_RUNTIME.json)
and [actual 12 UTC run](../scratch/cp02_native12_trajectory_37p85rc5/RESULT_RUNTIME.json)
both stop at nonzero `pgevp/rhox`; no first timestep is complete. The maintained
patch now also restricts enhanced melting, deposition/sublimation and
evaporation rate generation to available density, retaining coupled changes.
[The extension's 11 O0/O2 fixtures](../scratch/cp02_graupel_process_domain_46pn5bao/RESULT.json)
pass, with case 8 reproducing the prior evaporation failure and ten logged
controls unchanged. Full-host validation of the extension is underway;
CP02 #4 remains incomplete.

## Cold inactive-rate correction — 2026-09-14

The [maintained three-rate patch](../patches/kdm6_zero_graupel_volume_rate.patch)
now extends the warm guards to cold `pgdep` using the existing initialized
`bgdep`. A dry, condensate-free cold fixture reproduces the original floating
invalid at line 2611 in fresh pinned Intel O0/O2 full-module builds. Both
candidates pass all four cases, with unchanged logged controls; see
[the bounded result](../scratch/cp02_cold_clear_nvvvj7kw/RESULT.json).
The earlier cold fixtures passed the original and did not reproduce this
failure. This extension is not a new full-host run, moment initialization
contract, physical omega driver or CP02 #4 completion.

## Unit-corrected native diagnostic trio — 2026-09-14

The [unit-corrected runtime receipt](../scratch/cp02_unit12_runs/RESULT_RUNTIME.json)
binds the OFF, HYDRO, and LIQUID trajectories to the same pinned Intel host
(`wrf.exe` SHA256
`de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168`) and
the same 8-rank/1-thread execution profile. Each case has matching 88-file
input manifests, exit 0, and the three requested histories at 12:59:40,
13:00:00, and 13:00:20. Every output has 253 numeric variables and zero
nonfinite numeric values.

The host provenance includes the seven-predicate
[`kdm6_number_mass_domains.patch`](../patches/kdm6_number_mass_domains.patch)
and the paired
[`kdm6_number_basis.patch`](../patches/kdm6_number_basis.patch) plus
[`kdm6_ccn_initialization.patch`](../patches/kdm6_ccn_initialization.patch).
The pinned O0/O2 full-module, CCN-entry, number-density invariance, and
23-field metamorphic successes are recorded in
[`RESULT_UNIT.json`](../scratch/cp02_host_unit_contract_x3bcr8ui/RESULT_UNIT.json).

This is unit-corrected trajectory evidence only. It does not establish a
physical cloud-omega driver, absolute continuity closure, full water/energy
closure, or CP02 acceptance. Earlier no-unit native attempts remain pilot-only
failure/comparison evidence. The separate [model-dynamics increment
experiment](CP02_MODEL_DYNAMICS_INCREMENT_EXPERIMENT_20260914.md) defines the
covered-interior increment contract and native W handoff; its requirement #4
remains **INCOMPLETE**, and the original six CP02 gates remain unchanged.

## Requirement evidence refresh — 2026-09-11

The [six-requirement evidence matrix](../scratch/cp02_requirement_matrix_20260911/CP02_REQUIREMENT_MATRIX.md)
now uses the final original-producer receipts and current source review.
Requirements 1, 2, 3, 5, and 6 have evidence for their stated private execution
scope; no additional producer cycle or operational filesystem certification
is required merely to repeat those CP02 checks. Requirement 4 remains open:
the actual coupled candidate must traverse the native mapping with its
required variables, masks, frame, mass basis, and vertical-velocity semantics.
These scoped findings do not change the whole CP02 or E03 completion status.

## Current native vertical-velocity readback — 2026-09-11

The retained paired-input run `scratch/cp02_native_pair_047e21yq` completed
metgrid and real with exit 0. Direct readback of its hash-verified
`real/wrfinput_d01` finds `W(1,40,282,234)` finite and exactly zero everywhere;
`WW` is not serialized. The paired pressure-side diagnostic was retained as a
reference and was not consumed by either executable. Successful native output
therefore does not establish transmission of the analyzed/candidate omega.
The existing `RESULT.json` records this readback against the native file hash.

`HORIZONTAL_MAPPING.md` in that same run rules out crop-only and exact half-cell
averaging. The subsequent [scalar reconstruction](../scratch/cp02_wps_scalar_interp_nfjuake1/SCALAR_INTERPOLATION.md)
at the 100000-Pa slot gives TT/RH/GHT RMS differences of 4.78e-5 K,
2.47e-4 %, and 1.16e-4 m using the configured reference interpolation and
header source radius. It includes below-ground supplied values; it is not a
terrain-masked comparison or a proof of the operational executable's exact
source revision. The [subsequent U/V reconstruction](../scratch/cp02_wps_scalar_interp_nfjuake1/WIND_INTERPOLATION_ROTATION.md)
also supports the two-rotation sequence at that slot, with interior RMS
residuals of 8.63e-5/9.52e-5 m/s. Operational masks, boundary behavior, and
all-level wind mapping remain unverified. Full mask/frame/mass closure and the explicit vertical-
velocity handoff remain required. The physical replacement of empirical cloud
omega must reach that handoff; a reference sidecar alone cannot complete it.

The accessible KIM reference dynamics already separates the relevant physical
operations in `dyn_em/module_big_step_utilities_em.F`: `pg_buoy_w` (2419–2499)
adds vertical pressure-gradient and moist-loading terms to a momentum tendency;
`diagnose_w` (1270–1361) uses geopotential tendency, old/new geopotential, a time
step, hybrid mass, and the terrain boundary. These are reference equations to
assess for the physical replacement, not an implemented Cloud-BAL driver. A
single thermodynamic snapshot does not supply the missing tendency or time
evolution, and a chosen multiplier converting buoyancy to velocity would be a
new closure requiring justification. No such multiplier was added.

The subsequent bounded evaluation in
`scratch/pg_buoy_w_native_B7itWZ/RESULT.json` executes the exact extracted KIM
`calc_cq` and `pg_buoy_w` bodies on retained OFF/HYDRO native operands. Fresh
pinned Intel O0/O2 builds and all four runs exited 0; both saved output arrays
are byte-identical across optimization levels. An independent float64 algebra
comparison is retained separately. The prepared caller's species indexing and
vertical array stride were corrected before any execution; the source routines
were not changed. This establishes reproducibility of this momentum-tendency
contribution, not a full native timestep, new omega, or cloud causal effect.

Date: 2026-09-10

Scope: bounded engineering review of the canonical full-state payload, stage
adapters, pressure-level WPS mapping, and the existing ungrib writer. This is a
read-only source audit. No Fortran/build source was changed, no compiler was
run, and no physical product was regenerated.

## Verdict

E03 coupled transport remains **OPEN**. The maintained path is a validated OFF
transport and a research pressure-level mapper; it does not yet carry an
approved coupled candidate through WPS, metgrid, and native initialisation.

The existing OFF behavior must remain unchanged. In particular, exchange v1,
the three OFF adapters, and the OFF early return in LAPSPREP must not be
renamed or treated as coupled-candidate evidence. The current CP06-A input
readiness record is explicit that the available 13 UTC state has
`dynamic_target_authorized=0`, zero valid target cells, and zero valid sigma
cells. It is not an experiment approval.

## Current path and concrete gaps

`cloud_bal_stage_payload.f90:223-265` validates the canonical state,
field-level validity masks, quality/source bits, longitude, and identity. The
identity includes stage, generation, valid/reference times, grid, vertical and
wind conventions, and four SHA-256 lineage fields. It does not include an
authority receipt, target derivation/QC/clock/uncertainty contract, explicit
species or mass-basis contract, or candidate execution identity. Radar LOS is
required to be absent. Most critically, `validate_payload` rejects
`dynamic_target_authorized=true` at lines 260-263 because v1 has no authority
registry.

`cloud_bal_stage_context.f90:44-55` rejects dynamic identities and recognizes
only the existing stage/mode contracts. `cloud_bal_lapsprep_adapter.f90`,
`cloud_bal_balance_adapter.f90`, and `cloud_bal_deriv_adapter.f90` each retain
the OFF/no-target-sigma contract. The balance adapter runs `MODE_OFF` and
requires exact input, candidate, and operational state equality.

`cloud_bal_pipeline.f90:168-211` accepts only `MODE_OFF` or `MODE_SHADOW`,
requires observational target authority in the configuration, and rejects
manufactured target provenance. There is no coupled-candidate ingest path that
binds an authority receipt to the state before execution. The target/sigma
checks in `cloud_bal_state.f90:901-980` remain useful fail-closed validators;
they do not create observational authority by themselves.

`cloud_bal_wps_adapter.f90:27-47` defines `pressure_wps_fields` as numeric
pressure, T, height, wind, RH, QV, five hydrometeors, PSFC/SLP, skin
temperature, snow cover, valid time, grid ID, and wind coordinate. It has no
validity/quality/source arrays, above-ground or support masks, target/sigma or
omega, categorical fields, observation provenance, or pressure/dry-air mass
metrics. `map_pressure_candidate_to_wps` is transaction-safe in memory because
it maps into a local `work` object and assigns `mapped` only after validation,
but the metadata above is discarded. It requires `GRID_RELATIVE` and performs
no rotation.

`module_lapsprep_wps.f90:82-120` writes the legacy ungrib record. Its header
contains WPS geometry and a wind-relative flag, but no canonical identity,
source hashes, masks, support, target/sigma, mass basis, or candidate receipt.
The open at lines 194-200 uses `STATUS='REPLACE'`; a failed write can therefore
leave a partial or overwritten path. When hydrometeors are enabled, surface
QC/QI/QR/QS/QG slabs are explicitly set to zero at lines 456-605. A coupled
contract must either require valid surface species or record and validate this
fill policy; it must not silently present the zeros as observed candidate data.

`lapsprep.f90:1177-1220` preserves the canonical OFF identity and only assigns
mapped process arrays after all checks. The later path calls the legacy ungrib
writer. There is no Cloud-BAL WPS/metgrid/native reader that can reconstitute
the complete canonical state. `read_real_shadow_state` in
`cloud_bal_real_netcdf.f90:93-480` reads LAPS NetCDF products, while
`read_lco_evidence` at lines 56-90 keeps COM as separate legacy evidence and
does not assign target or sigma. The current native auxiliary inspection is not
a writer round-trip verifier.

The lost information is material: canonical moisture is dry-air basis and has
the order vapor, cloud water, cloud ice, rain, snow, graupel; canonical
pressure geometry includes pressure and dry-air mass measures; and canonical
state contains above-ground, observation-support, hydrometeor-support, field
quality/source, and boundary masks. WPS carries only numeric slabs. Omega is
not represented in the WPS bridge. Native `MU/MUB`, staggered `U/V`, `P/PB`,
`PH/PHB`, potential-temperature, and native `ww` conventions require explicit
conversion and must not be inferred from WPS arrays.

## Minimum implementation boundary

The following is the smallest coherent transport extension; it is a design
boundary for later implementation, not an approval of any target.

1. Add a versioned coupled payload or sidecar contract instead of loosening
   exchange v1. It must bind candidate kind, run/generation ID, cycle and
   valid/reference times, source/input/configuration hashes, executable/runtime
   pins, authority-receipt hash, target derivation/QC/frame/uncertainty IDs,
   species order and denominator, pressure/dry-mass metric IDs, vertical order,
   and wind frame. Retain all canonical field masks, source/quality bits,
   supports, boundaries, target/sigma, and explicit LOS presence/absence.

2. Add a separate coupled stage context and adapter. It must verify the coupled
   identity and receipt, require the existing positive finite sigma and
   resolved-target checks, invoke the approved candidate pipeline, and publish
   only a complete output transaction. Existing OFF adapters remain unchanged
   and continue to reject dynamic input.

3. Add a coupled WPS writer wrapper and metadata sidecar. Keep
   `output_ungrib_format` for the legacy/OFF path. Candidate output should use a
   fresh generation directory, no-clobber creation, post-close hashes for both
   data and sidecar, and publish only after all checks succeed. The sidecar
   must record Pa-to-hPa pressure conversion, geopotential-to-height gravity,
   dry-air moisture basis, six-species mapping, QV-over-RH precedence, surface
   fill/mask behavior, geometry, mass basis, and the fact that omega is not in
   the ungrib carrier.

4. Add a metgrid/native reader and independent verifier. It must validate the
   sidecar/data hashes and identity, then check QV/SH/RH precedence, all six
   species, temperature reconstruction, pressure/geopotential, staggered wind
   placement and frame, masks, time, and native dry-mass metrics. Native `ww`
   must remain distinct from pressure omega.

Rollback must cover map, write, metgrid/native conversion, and readback. On any
failure, no candidate seal or final generation may be published and the input
and prior output namespaces must remain unchanged.

## Work allowed before CP06-A

Structural preparation can proceed without target approval:

- preserve and regression-test the existing v1/OFF payload and adapter matrix;
- exercise a v2 schema with OFF or explicitly non-authoritative structural
  fixtures, including identity, provenance, mask, species, frame, time, and
  mass-basis mutation rejection;
- test mapper atomicity, six-species mapping, QV/RH precedence, frame
  rejection, pressure-level remap, no-clobber output, sidecar/data hash binding,
  partial-write cleanup, and stale-identity rejection;
- use synthetic native layout fixtures only to test dimensions, units,
  staggering, masks, and conversion fail-closed behavior; and
- add old-LAPS-only and missing-sidecar negatives that cannot be mistaken for a
  coupled candidate.

These fixtures must carry authority `NONE` and must not be passed to an actual
coupled run.

## CP06-A and CP06-B prerequisites

This section describes the existing v3 target-driven experiment. The user's
subsequent requirement is a dynamical/physical replacement of empirical cloud
omega, not acquisition of an external omega observation by default. That
replacement needs an explicit forcing equation and boundary conditions before
its calculated output can enter the candidate path. Re-integrating continuity
from unchanged analyzed U/V is a kinematic diagnostic, not a cloud dynamical
driver; changing the dry-mass weighting after thermo does not add the missing
momentum or heating equation. Source flags and sigma alone cannot close this
gap. These findings do not weaken the native round-trip requirement below.

Actual execution remains blocked until CP06-A supplies an approved case and
exact input identity, a nonzero observation-derived target, positive finite
sigma, source hashes, observation clocks, frame/QC/dealias/fall-speed and
uncertainty provenance, allowed variables/support, and fixed thresholds,
iterations, tolerances, and reference definitions. The same pre-QBAL state
must produce OFF, hydro+thermo, and the actual coupled candidate with
independent target-fit, positivity, water/enthalpy, EOS, mass, support,
residual, and rollback checks.

Only after that may CP06-B exercise the same approved candidate through
WPS→metgrid→real/native and independently verify the native arrays, masks,
frame, time, mass basis, and provenance. Existing LGT/COM evidence, an input
flag, or the current OFF matrix cannot substitute for this authority.

## Evidence and exact hashes

The readiness source record is
`docs/CP06_A_INPUT_READINESS_20260910.md`; it states “NOT READY FOR AN ACTUAL
COUPLED RUN” and requires an explicit exchange/writer/validator extension.
Relevant source and record hashes at review time are:

| Path | SHA-256 |
|---|---|
| `src/common/cloud_bal_stage_payload.f90` | `4bb69f7d21643a17617e903fc1570dde198215d35b80fc1e5f0c8b006b20316a` |
| `src/common/cloud_bal_stage_context.f90` | `e08fb711c8be9bba2f2f162c97c62518a9b2d784157910628160479b74637a46` |
| `src/common/cloud_bal_lapsprep_adapter.f90` | `74cd6339780ba54ba9ea68800163c955d3726f652d2dfec41b85d1a9a07e4f35` |
| `src/common/cloud_bal_balance_adapter.f90` | `9e55f7785b84b485ebb4f07cfc80f0401a7655d2dddffa34f3a40b9509907d00` |
| `src/common/cloud_bal_deriv_adapter.f90` | `fa9171779d4917a1dbb5d0c0a896a89833687fe6a9ddf6a6f7ab0b449068a221` |
| `src/common/cloud_bal_wps_adapter.f90` | `f063f9b3605fe2504b6d364f858cef82605105a0888825cd795ea03c7c65eacb` |
| `src/common/cloud_bal_pipeline.f90` | `188a2e1b9f467c6fa28e8f317e493975ddaf8dfbf5100398867666bbb6f2b478` |
| `src/common/cloud_bal_state.f90` | `0347dc140d3940013cf72d26a2d142980d0a8b2f0a1af1c55ed5f0305fffa9d5` |
| `src/common/cloud_bal_real_netcdf.f90` | `d0f683a3b0a226bf265003bc7e44ff4e70be19cff851b697e151d262c82f04cb` |
| `src/lapsprep/module_lapsprep_wps.f90` | `b60b05236fac32e490b1dcde18cfe848012098658a4d4514542e1888ad708c39` |
| `src/lapsprep/lapsprep.f90` | `ecbc899afdc0dcc85bbe3559cb8157f95db263e678635ea5580274373cd1f8c4` |
| `docs/CP06_A_INPUT_READINESS_20260910.md` | `92ec89d170b3a6af6e3add950fc2b51c0449adbc3dce58646a255c232e746e7a` |
| `docs/CLOUD_BAL_CHECKLIST_20260907.md` | `fae2e99e19b9a6c4ac76bd1bd25d7700bff2fcbbc5fe2912059a766da8cb35f6` |
| `docs/CLOUD_BAL_FINAL_GOALS_CHECKPOINTS_20260907.md` | `eff3a821967df4ad27babace622f91bacb11dc2f31f7f1cb63074c0bfa700230` |
| `docs/NO_GO_CLOSURE_CHECKLIST.md` | `501273927796bfdb077b28f229a73cfd31616bd5318424b9f88fe5cddb8ae7c5` |

The E03 completion condition remains the checklist requirement at
`docs/CLOUD_BAL_CHECKLIST_20260907.md:385-392`: full OFF and actual coupled
candidate WPS→metgrid/native round trips with field, mask, time, geometry, and
mass-basis verification.

## Existing sidecar reuse — 2026-09-11 inspection

The LAPSPREP candidate path already writes `${CLOUD_BAL_WPS_OUTPUT}.shadow.nc`.
An additional sidecar implementation is not needed for fields it already
preserves. Existing HYDRO/LIQUID artifacts contain above-ground/observation/
hydrometeor support masks, cloud provenance, omega/boundary fields, pressure
geometry and dry-air mass measures. The previous native input manifest omitted
these adjacent sidecars.

[Exact retained WPS/sidecar inventory](../scratch/cp02_wps_create_new.EsG4m1/EXISTING_SIDECARS.json)
is a retrospective association, not a newly attested native execution. Reuse
these diagnostics for the pressure-side reference and bind both files in the
next native execution's existing input manifest. The stage payload already
preserves LCO cloud_omega_evidence separately.

Material gaps remain: wind value fields lack per-cell valid/quality/source in
the diagnostic, its trajectory frame remains INPUT_WIND_NATIVE_UNRESOLVED,
and no pressure-side mass measure establishes native dry-mass mapping.
WPS/sidecar pairing by filename alone is insufficient. Do not replace these
gaps with another duplicate schema or relabel them as absent observations.

The [candidate WPS final-OPEN fix](CP02_WPS_CREATE_NEW_20260911.md) prevents
replacement after the existing preflight check; pair binding/publication and
native readback remain open.


## Native W startup setting — 2026-09-11

The paired `real/namelist.output:2049` contains `USE_INPUT_W = F`. Moreover,
the current KIM `start_em.F:1508–1524` replaces W when both surface extrema
are below 1e-6 m/s even if that option is true. A future accepted cloud W
with zero surface velocity therefore needs an explicit startup preservation
path as well as an ingest before `real` writes the native file. Merely adding
an OMEGA WPS record or enabling the namelist option does not close E03.
See the [source and setting review](../scratch/cp02_native_pair_047e21yq/OMEGA_HANDOFF_REVIEW.md).

The private one-line preservation patch passed the extracted startup-branch
O0/O2 tests and a fresh strict Intel host build. Its manufactured full-host
run then failed in KDM6 `radar_init` at `1./xam_g`, before initial W output.
The [runtime receipt](../scratch/cp02_native_w_host_startup_20260911/RESULT_RUNTIME.json)
therefore leaves full-host preservation unverified. Correcting the radar
mass coefficient must retain KDM6's cellwise graupel density; it supplies
neither physical cloud forcing nor native omega ingestion.

With that radar correction, the new full host writes initial W exactly equal
to all 2,639,520 input values, including the 3.5 m/s interior sentinel and
zero surface. The [retry receipt](../scratch/cp02_native_w_host_startup_20260911/RESULT_RADAR_RETRY_RUNTIME.json)
supersedes the unverified startup result for this manufactured periodic case.
The following first timestep aborts in KSAS `dtconv=tfac*tem/wc`; neither
a completed timestep nor physical cloud forcing is established.

The subsequent KSAS-guarded host again preserves the complete initial W
array and reaches KDM6 microphysics. It aborts at `1./lamdai(...)` in
`slope_kdm6`. Initial history contains positive ice mass above `1e-12 kg/kg`
in 249,166 cells with zero `QNICE`; `QNCLOUD`, `QNRAIN`, and `QIB` are also
all-zero, while `QNCCN` is populated. These are observed native-state values,
not proof that all upstream moment inputs are absent. The
[runtime receipt](../scratch/cp02_ksas_inactive_gnkh1dyg/RESULT_RUNTIME.json)
leaves moment handoff/initialization and the full timestep open. A numerical
division guard alone cannot establish a physical particle population.

A subsequent RED source review identified a narrower numerical repair:
[zero-number limit patch](../patches/kdm6_zero_ice_number_limit.patch).
The existing bounded inverse ice slope tends to `1/lamdaimin` as number
tends to zero. Two later lambda evaluations tend to zero before the existing
size clamp reconstructs number. Explicit zero branches preserve this order
and introduce no new constants; they do not validate the supplied moment
state. [GREEN full-module tests](../scratch/cp02_kdm6_ice_limit_iado8lli/GREEN_REVIEW.md)
pass six cases each with pinned Intel O0/O2, including both signed-zero
cases where the original aborts. The four other cases retain identical
reported results. The [fresh private host build](../scratch/cp02_kdm6_ice_limit_iado8lli/RESULT_BUILD.json)
and runtime-link checks pass. The [same-input run](../scratch/cp02_kdm6_ice_limit_iado8lli/RESULT_RUNTIME.json)
preserves all 2,639,520 initial W values and passes the ice-slope failure,
then aborts with floating invalid at `bgevp=pgevp/rhox`
(`module_mp_kdm6.f90:2695`, original `.F:2702`). The exact failing cell and
operands were not captured. All 86 input/static files remain unchanged;
the 20-second diagnostic and physical cloud omega implementation remain incomplete.

Source review confirms the first ice-slope call precedes ice nucleation and
freezing; the pre-slope number clamp preserves zero. The current bound KLBG
WPS intermediate contains no direct number/volume records. Retained LAPS
`pcn` is a mass-content field in `.lwc`; `lmd` is in a separate `.lmd` file
and takes the 10/12/18/25 micrometre cloud-type values assigned by `get_mvd`.
Neither is a supplied ice-number field. The
[input review](../scratch/cp02_ksas_inactive_gnkh1dyg/MOMENT_INPUT_REVIEW.json)
records file hashes and the background record inventory. The immediate
predecessor is the regional KLBG forecast through KL05/LFMPost, not the global
KIM GRIB input. `klps_lc05_make_init_00.csh:68–85` links the KLBG native
forecast into `KL05DAOU/background/wrfprd` and runs `lfmpost_wrfv3.exe`;
`klps_lc05_make_bndy_v4.csh:60` selects the resulting GRIB. The native/GRIB
13 UTC predecessor is not retained in the inspected workspace, so absence
of moments before LFMPost is unproven.

The retained postprocessed file
`scratch/upstream13.Sfb68E/lapsprd/fua/wrf/2622806000700.fua`
(SHA256 `fa719119f0bfa2b331b0b18d2e6b7f7f2d3f9c1eaa611d0530df49f632b4237e`)
has reference time 06 UTC and valid time 13 UTC. Its physical 3-D fields are
`ht,u3,v3,w3,om,t3,sh,rh3,lwc,ice,rai,sno,pic,ref,pty,tke`; no direct
KDM6 number/volume fields are present. It retains both `w3` (m/s) and `om`
(Pa/s), but their presence does not establish a coupled candidate or a
lossless conversion between them. Populated startup `QNCCN` likewise does
not prove source transport. This bounded finding does not require acquiring
the already available observations again.

The retained LFMPost source explains why the two vertical-velocity fields
cannot supply an independent pressure tendency. `wrfutil.f90:156–163`
averages adjacent native W faces; `interp.f90:136` interpolates W in log
pressure. Then `lfmutil.f90:595–601` computes
`OM = -p*W*9.81/(287.04*T*(1+0.61*SH))`. All source paths here are under
`klaps-v5.0_/src/lfmpost/`. A direct float32
[formula readback](../scratch/cp02_ksas_inactive_gnkh1dyg/FUA_OMEGA_FORMULA_READBACK.json)
matches 1,462,949 of 1,463,110 finite cells exactly; maximum absolute
residual is `1.1205673e-5 Pa/s`. This is evidence of the retained formula,
not authenticated producer-binary identity or a fitted acceptance tolerance.
Neither this approximate OM nor the pair `(W3, OM)` establishes the missing
pressure tendency/advection needed for a lossless candidate omega/W mapping.

The manufactured 20-second runs are early diagnostics of startup and supplied
state. They do not add a forecast-completion requirement to CP02. The open
CP02 requirement remains the original E03 contract: an actual coupled
canonical candidate consumed through the downstream path, with every required
field, mask, frame, time, and mass basis verified. The discovered moment-state
defect informs that input contract; the small W-preservation and selected-column
tests cannot replace it.

The existing `real` source already interpolates supplied `QNI/QNC/QNR` when
their flags are set (`module_initialize_real.F:2004–2062`). The selected
`METGRID.TBL.ARW.OML.KWW` has entries for those fields, but explicitly sets
`output=no` for `QNC`; it has no `QIB` entry. Thus direct source availability
alone would not complete the current auxiliary-moment handoff.

Missing-number reconstruction in `real` is currently enabled only for
Thompson and Thompson aerosol (`module_initialize_real.F:4789–4845`), not
MP37. Its `make_IceNumber` uses an ice density of 890 kg/m3 and a temperature
lookup, whereas KDM6 declares 500 kg/m3. Extending that scheme condition to
MP37 without a reviewed KDM6 initialization contract would change the assumed
particle population; it is not a neutral missing-input repair.


## Host build attribution — 2026-09-11

The sibling KIM host's existing build manifest was located and checked:
real/wrf executable hashes and configure.wrf match its entries, and eight
inspected source files match its recorded Git commit. This supersedes the
previous statement that no host build receipt was available. The
[comparison receipt](../scratch/cp02_native_build_manifest_tlyqvxi2/RESULT.json)
is selected-source attribution, not a fresh full build or dependency audit.
Metgrid's exact build source and actual candidate native ingestion remain open.

## One-point native QV reconstruction — 2026-09-11

At zero-based `(i=117,j=140,k=10)`, a float32 translation of the inspected
`integ_moist`, `p_dry`, and first-order log-pressure interpolation reproduces
native `QVAPOR=0.01284586451947689` exactly. The target dry pressure is
`79800.375 Pa`; final serialized `P+PB=80022.09375 Pa` is not used.
The [readback](../scratch/cp02_qv_readback.G24jgE/qv_readback.json) uses saved
native `MU+MUB` and hybrid coefficients to recover the target coordinate.
This is a conditional one-point mapping check, not independent reconstruction
of the full native mass field, all-variable acceptance, or a coupled round trip.

The [extended readback](../scratch/cp02_qv_readback.G24jgE/qv_readback_extended.json)
also reproduces native perturbation potential temperature exactly and cloud
water within one float32 ULP at this point. The other four hydrometeor source
brackets and outputs are zero, so they do not test nonzero transfer. RED
confirmed the point-specific source-level selection and the separate real.exe
hash binding. Surface forcing skips one source slot; the independent 500 Pa
near-surface zapping test removes none here.

Extending that column to all 39 levels gives maximum absolute residuals of
`2.51457e-8 kg/kg` for QV, `9.15527e-5 K` for native perturbation potential
temperature, and `7.27596e-12 kg/kg` for cloud water; see the
[column readback](../scratch/cp02_qv_readback.G24jgE/qv_readback_column.json).
These are measured discrepancies, not a fitted acceptance tolerance. The
four other hydrometeor columns remain all-zero and need nonzero coverage.

The [U/V column readback](../scratch/cp02_uv_readback_k5m7p2/UV_READBACK.json)
uses adjacent mass-column dry pressures at the actual horizontal staggered
locations. Across 39 mass levels at `(i=117,j=140)`, 27 U and 28 V values
match exactly; maximum absolute residuals are `9.536743e-5 m/s` and
`7.826090e-5 m/s`. This retains the conditional recovered-native-mass scope
and does not establish boundary handling or whole-grid acceptance.

Nonzero QI/QR/QS/QG coverage was then sampled at each species' source maximum,
chosen before reading native residuals. The three resulting columns cover
39 levels each. Maximum absolute residuals are `4.65661e-10`, `5.82077e-11`,
`9.31323e-10`, and `9.66247e-9 kg/kg`, respectively; see the
[corrected species readback](../scratch/cp02_qv_readback.G24jgE/hydrometeor_nonzero_readback_fixed.json).
The initial rain discrepancy came from the scratch reference assuming the
first pressure level was above terrain. Reproducing the actual surface
moisture integral and underground pressure handling removes that discrepancy;
the original result remains preserved. No model code or acceptance tolerance
was changed for this comparison.
