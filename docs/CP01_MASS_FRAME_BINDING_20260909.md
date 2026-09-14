# CP01 mass/frame evidence binding — 2026-09-09

Scope is CP01 items 2 and 5 only: mass basis, EOS/metric meanings,
frame/rotation, boundary authority, and the `w`/`omega`/`ww` distinction. It
does not implement the reader time check, native first call, or CP06/07 science.

## Decision

The pressure-fixed/native separation and fail-closed frame/boundary contract
are documented. The accessible KIM source now binds named host constants,
the `USE_THETA_M=1` T/THM branch, the active `AREA2D=DX*DY` physics branch,
and the native C-grid flux metric carried by `MAPFAC_*` factors. The source
flux algebra identifies `A_native_metric=DX*DY/(MAPFAC_MX*MAPFAC_MY)` and the
asymmetric-map oracle checks its boundary/interior cancellation. The trace
does not prove that every restart/configuration or operational executable uses
that source-derived weight. That is an explicit runtime/source-build receipt
requirement, not a reason to call the source meanings unknown. An operation that needs a native
kg mass, native total-energy conservation, or physical boundary authority
still remains without authority or is rejected until its named receipt exists.
Missing authority is not a verified zero, smaller domain, or physical boundary;
no native/forecast promotion follows.

Authoritative scope records:

| Record | SHA-256 | Use |
|---|---|---|
| `docs/CP01_CONTRACT_EXIT_MATRIX_20260909.md` | mutable read-time matrix; hash omitted | CP01 item 2/5 boundary and downstream split |
| `docs/NATIVE_MASS_FRAME_CONTRACT.md` | `b259c83f962633e940448dc4ba26a138fb9bedce4146b1fda504b9e28c31210f` | Mass/EOS/frame contract |
| `scratch/cp01_host_binding_audit.20260909/evidence.json` | `c5f1382daddcd9d2a8cea77b7d5e07ce554f2002f014bef642593822df489787` | Items 1–3 source/authority split |
| `scratch/cp01_frame_boundary_time_OWN_20260909.md` | `c2dd91847bf235fe017222434a49ec4df72388b545ab2fd692716bb4a9053049` | Item 5 source/negative evidence |

Source hashes and line numbers below identify the inspected snapshots.
The live reader is changing; its new time-contract receipt is recorded separately.

## Mass, EOS, units, and ledger binding

| Meaning | Contract and units | Evidence / authority limit |
|---|---|---|
| Pressure diagnostic mass | `m_tot = A * cell_dp / 9.80665` kg; `m_d = m_tot/(1+r_t)` kg dry air. This is fixed pressure-cell diagnostic mass, not conserved native mass. | `NATIVE_MASS_FRAME_CONTRACT.md:65-87`; canonical geometry/state receipts pass O0/O2, but this does not establish host mass conservation. |
| Native dry mass | `MU+MUB` is already dry; hybrid `dp_dry` is converted with explicit `g_native` and `A_native_metric=DX*DY/(MAPFAC_MX*MAPFAC_MY)`. Never apply a second `/(1+r_t)`. | `NATIVE_MASS_FRAME_CONTRACT.md:95-153`; source flux factors and asymmetric-map cancellation receipt bind the mathematical weight. Runtime source/build identity, restart provenance, gravity and full timestep mass closure remain required. |
| Native dry-pressure algebra | `pd_interface=C3F*mu+C4F+P_TOP`; `dp_dry=-(C1H*mu+C2H)*DNW`; `m_d=A_native_metric*dp_dry/g_native`. `AREA2D=DX*DY` is the separate active physics field. | This is a source-derived algebraic integration contract, not a native executable receipt. `pd_interface` is not physical EOS pressure; the CP02 oracle is algebra-only and explicitly has `native_timestep_assessed=false`. |
| Physical EOS pressure | Native EOS pressure is `P+PB`; serialized `T` is dry perturbation potential temperature, `THM` is moist perturbation for the selected `USE_THETA_M=1` branch, and `PH+PHB` is staggered geopotential. | [Named-file theta binding](CP01_THETA_BINDING_20260909.md) proves the source-expression mapping exactly for all 2,573,532 cells. `phy_prep` and hybrid pressure formulas are source-bound; full runtime/source-build equivalence remains separate. |
| Canonical gas EOS | `rho_d=p/[287.05*T*(1+r_v/0.622)]`; `rho_g=rho_d*(1+r_v)`, with `p` Pa, `T` K, `r_v` kg/kg dry air. Hydrometeor concentration uses `rho_d`; omega/w approximation uses `rho_g`. | `src/common/cloud_bal_state.f90:747-767,769-829`, SHA-256 `0347dc140d3940013cf72d26a2d142980d0a8b2f0a1af1c55ed5f0305fffa9d5`. This is gas-only canonical authority, not native EOS equivalence. |
| Water species | Canonical `(r_v,r_c,r_r,r_i,r_s,r_g)` maps to native `(QVAPOR,QCLOUD,QRAIN,QICE,QSNOW,QGRAUP)`, all kg/kg dry air. `SH` is converted as `r_v=SH/(1-SH)`; QV is not filled from missing RH. | `NATIVE_MASS_FRAME_CONTRACT.md:195-205`; WPS validation `module_lapsprep_wps.f90:141-147`, SHA-256 `b60b05236fac32e490b1dcde18cfe848012098658a4d4514542e1888ad708c39`. Selected private MP37 species/number definitions are bound in CP01_PRIVATE_HOST_PROFILE_20260909.md; actual input authority remains absent. |
| Analysis ledgers | `A_Q` is signed represented-water kg; `A_M` is signed external dry-air kg (default zero); `A_E` is signed J under the named `CLOUDBAL_MIXTURE_ENTHALPY` convention. Internal phase transfer, sedimentation, boundary flux, kinetic/geopotential, and native compressible-total-energy terms are separate. | `NATIVE_MASS_FRAME_CONTRACT.md:76-93,358-374`. The six-species mixture law is explicit; it does not become native total-energy authority or KDM6 `h_diabatic`. |

The pressure and native ledgers are separate state meanings. A candidate must
carry mass basis and denominator provenance; diagnostic mass cannot be relabeled
as `MU+MUB`, and absent optional species cannot become verified zero. The named
source metric is `NATIVE_DYNAMICS_FLUX_METRIC`: `msftx*msfty` multiplies the
small-step horizontal `MU` divergence, `msfuy`/`msfvx_inv` enter face U/V fluxes,
and `1/msfty` couples `ww` (`module_small_step_em.F:1071-1130`). The source
derivation gives `A_native_metric=DX*DY/(MAPFAC_MX*MAPFAC_MY)`; the active
physics field `AREA2D_ACTIVE_PHYSICS` is separately `dx*dy` m2 on non-restart
initialization (`module_physics_init.F:5769-5802`). The remaining issue is
restart/runtime provenance and source-to-binary use of that defined weight.
A CP02 numerical receipt must bind the chosen
metric, hybrid `dp_dry`, gravity, source/build/input hashes, and independently
recompute cell mass; it cannot replace the source contract. Complete native
coupling is CP06/07.

The source root is `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2`.
The accessible KIM reference pins `g=9.81`, `r_d=287`, `r_v=461.6`,
`cp=1004.5`, `cv=717.5`, `cpv=1846.4`, `cliq=4190`, `cice=2106`,
`p0=100000 Pa`, and `t0=300 K` at `share/module_model_constants.F:17-39`
(SHA-256 `5b80377fecdc18a5f0ad38d3b6c15cfc86ad5d76701adbbbb08a08698d0f7062`).
With `USE_THETA_M=1`, `phy_prep` uses
`th_phy=(t+t0)/(1+(Rv/Rd)*qv)`, `p_phy=p+pb`,
`pi_phy=(p_phy/p0)**(Rd/cp)`, `t_phy=th_phy*pi_phy`, and
`rho=(1/alt)*(1+qv)` (`module_big_step_utilities_em.f90:4699-4725`). This is
the intermediate moist-air preparation value. `solve_em.F:3665` then calls
`moist_physics_prep_em`, which resets `rho=1/(al+alb)` at
`module_big_step_utilities_em.f90:5398`; KDM6 receives that dry-density field
as `DEN=rho` at `phys/module_microphysics_driver.F:2527-2554`. Hybrid pressure
reconstruction uses all registered moist species as `qtot`
(`:1036-1135`). Registry binds MP37 to six mass species plus
`qnn,qnc,qni,qib,qnr` (`Registry.EM_COMMON:3238`, SHA-256
`b01855ed80569be04bbd99e43ea1672a60e35590db00145c839b8f74cfd9b07f`).
The inspected `solve_em.F` source hash is
`6e52d3018a9418d2635a9a5624fe903631e9b5d904151280c384e35a43099f8f`.
These source meanings are bound to the accessible reference; KLFS
source/build equivalence and the scalar runtime mass receipt remain separate.

The energy ledger has a concrete CP01 analysis convention. For dry cell mass
`m_d [kg]`, physical temperature `T [K]`, and
`r=(rv,rc,ri,rr,rs,rg) [kg kg-1 dry air]`,
`A_E_CLOUDBAL_MIXTURE_ENTHALPY` is

```text
h_d(T,r) = (1004.5 + sum(c_j*r_j))*(T-273.15) + sum(h0_j*r_j)  J kg-1 dry air
A_E = m_d * (h_d(T_after,r_after)-h_d(T_before,r_before))              J
c   = [1846.4,4190,2106,4190,2106,2106] J kg-1 K-1
h0  = [2.50e6,0,-3.50e5,0,-3.50e5,-3.50e5] J kg-1
```

The array order is the explicit phase-transfer order `(rv,rc,ri,rr,rs,rg)`;
the native field names remain `QVAPOR, QCLOUD, QRAIN, QICE, QSNOW, QGRAUP`.

`A_Q` is the signed represented-water kg increment, and `A_M` is the signed
external dry-air kg increment (default zero). These include only declared
support and their accepted dry-mass basis. They exclude internal phase
transfer, sedimentation, boundary flux, kinetic/geopotential, and native
compressible-total-energy terms. The host KDM6/dynamics convention is separate:
KDM6 source/sink rates are kg kg-1 s-1 and the Registry `h_diabatic` field is
K s-1 (`phys/module_mp_kdm6.F:563,2557-2610`; `Registry/Registry.EM_COMMON:1401-1403`).
No J-valued `A_E` is integrated into `h_diabatic` without an explicit pressure,
mass, map-factor and storage conversion. This closes the CP01 ledger meaning
without claiming native total-energy conservation.

## Frame, rotation, vertical velocity, and boundaries

The producer source sets `l_grid_north_out=.true.` at
`klaps-v5.0_/src/include/main_sub.inc:48-51` (SHA-256
`de80575d8b55410df704af7f02b0587281ea4fa4fb2164d87adb2f551597cdbd`), so
`src/wind_openmp/main_sub.f:521-537,727-756` (SHA-256
`aec65d9dc5ea8e2b4f2c49de73a8bbe65ef966247bbefcec64cc4870bc5b91ab`) bypasses
output rotation. `src/lib/conversions.f:1144-1214` (SHA-256
`baefcb5874ac2474a63756c80dac4ee2968588b5ccc3dd79380fba6105c27761`) gives the
sign convention. This suggests grid-relative U/V but is not arbitrary-LW3 authority.

Retained `262281300.lw3` is SHA-256
`715218e48058ef115f4b95aef2403d750b586da9818b74fd91e10be8662c80d6`; U3/V3/OM
are m/s, m/s, Pa/s and `valtime=reftime=2026-08-16T13:00:00Z`, with no frame
attribute. `cp01_frame_trace.ig53avsk/receipt.json` (SHA-256
`039eee2b0a02ef2f34bb670491a4c679a644dfbe2fedd84002e3e566ac74dc4a`) records
`FSF_frame=UNRESOLVED`, binary equivalence not re-established, and no science authority.
WPS writes `wind_grid_relative` at `module_lapsprep_wps.f90:627-658`, but no w/omega/ww.

The reader reverses LW3 levels and reads `om/u3/v3` with Pa/s and m/s at
`cloud_bal_real_netcdf.f90:184-237` (SHA-256
`01bf28b4b9e121e1443480130e2cb02d1364fdb72d69229b3fd30a3196fc81fc`). Normal
boundaries copy interior omega with copy/legacy bits (`:2645-2669`); the
validator preserves that status (`:2848-2863`). Physical boundaries require
Pa s-1, matching valid time, usable metadata, zero quality, and exactly
`SOURCE_BOUNDARY_CONDITION` (`cloud_bal_balance_operator.f90:2484-2526`, SHA-256
`9f460727d83a0b0ce428a10e5c51a76ebe358e5fc1b67bb8bf4d554569f47840`).

The numerical FSF path computes bottom `(PS_after-PS_before)/7200 +
USF*dPS/dx + VSF*dPS/dy`, sets top zero, and tags both manufactured
(`real_netcdf.f90:428-577`); its FSF surface-wind frame is unknown and has
numerical-test authority only. The time-reader implementation is outside this scope.

`w` (m/s), pressure `omega` (Pa/s), and native `ww` (mu-coupled eta-dot, Pa/s)
are distinct. Local conversion is only `w=-omega/(rho_g*g)` / inverse
(`cloud_bal_state.f90:769-829`); KIM reconstructs `ww` from native mass continuity,
so equal units do not imply equal variables (`NATIVE_MASS_FRAME_CONTRACT.md:144-152`).
Native `ww` equivalence is CP06-B/07 evidence.

## No-authority and rejection contract

Reject the candidate or make an atomic no-op when any of these holds:

- pressure-fixed mass is mixed with native `MU+MUB`, or a required runtime
  denominator, gravity, EOS, map metric, or species basis is not bound;
- frame is absent, conflicting, or unsupported; no rotation angle or zero
  rotation may be guessed from a label; `EARTH_RELATIVE` is not accepted by the
  grid-relative adapter;
- required boundary data, units, cycle metadata, usable source/quality, or
  complete declared species coverage is missing or nonfinite;
- copied interior or manufactured boundaries are presented as observational,
  or `P_TOP` is treated as proof of zero top flux;
- `w`/`omega` is converted without the declared gas-only approximation, or
  `ww` is substituted for pressure omega;
- malformed dimensions, level order, pressure/PSFC, grid spacing, NaN, or
  stale metadata would require shrinking the domain.

The current negative tests cover adapter metadata, boundary provenance, time,
units, and malformed mapping cases: `test_real_shadow_io_contract.f90`
(SHA-256 `3769ce00f96dfd565fc04636f9e135d8bab1d092c72106c11aaf06fd87d49aa`),
`test_pressure_wps_mapping.f90` (`4dba692cc67da833497d5b8f4d01049197461ab1c9af95d48703fd0c6ebc6f29`),
`test_pressure_transition_prior.f90` (`631bf4958f209f37259a69e6fa27ff0a3a359290cefaf096f6cea7d1c734d022`),
and `test_state_atomic_refresh.f90` (`5679311cafd75feadfd6afe16a21ac2d1ec30358379158b7f0b138724e29bd65`).
They prove their specific adapter/fixture cases. They do not yet establish
rejection of every runtime/source-build mismatch in the now-named host EOS,
metric, energy, or auxiliary denominator contracts.

## Producer/binary evidence and downstream disposition

KLFS init/forecast hashes and embedded source paths are retained in
`scratch/cp01_host_trace.hibfq2e0/receipt.json` (SHA-256
`8862d794b41040fed4f9191dbaf35c33b68ecc260c02776d5913f72783f7db92`), but it
declares `runtime_executed=false`, `external_paths_accessed=false`,
`mp37_definition=UNRESOLVED`, and `science_authority=NONE`. The fresh pinned
Intel wind build `scratch/upstream_wind_openmp_build.YGLtio` produced
`klps_anal_wind_openmp.exe` SHA-256
`0e4b97839cbacb049170cb60683bab9f16652e2370c457d76b0f904354ba84a4` using
`tests/intel_toolchain.sh` SHA-256 `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`.
The earlier private 13 UTC run in `scratch/cp01_private_wind_run.TAiW8G`
terminated with SIGSEGV before output and is not producer evidence. A later
isolated run completed with exit 0 in `/tmp/cp01w.DXCCNQ`; its post-run receipt
SHA-256 is `11dcca995bcc52ea36a1a0debc514d67911f7c2cd72faebe1729aa9bab9c9070`
and repository comparison receipt `scratch/cp01_lw3_compare_20260909.json` SHA-256 is
`5f08c157d852cfb1e05c66cebeab327950afb42bc4cc302a8c03844a3b2dbc67`.
It binds the current producer source/build, private configuration, 13 UTC
inputs, and fresh outputs: LW3 SHA-256
`2eb193f38e98a2501d7ce4a887eb88ef97d434a151af6ae560903503222008fa` and LWM
SHA-256 `c41cfaa8c08e8df86cb4078fe6dac31a3ab4c5efde27f7108901935548dc902e`.
The fresh LW3 has the same dimensions, variable set, attributes, and valid
masks as retained `final_ordered`, but U3/V3/OM differ numerically (max
absolute differences 2.8571081 m/s, 3.406354 m/s, and 0.4909158 Pa/s).
Therefore it is a named current-source producer result, not a byte-equivalence
receipt for the retained historical LW3. Its metadata still has no frame
attribute; source configuration suggests grid-relative output, while frame
authority remains conditional on the declared producer/build receipt.

CP01 item 2 now has precise source-level bindings for host constants, the
T/THM branch, `AREA2D`, the C-grid flux metric, the derived native integration
weight, and the `A_Q/A_M/A_E` conventions. Its remaining authority boundary is
runtime: source/build identity, restart metric provenance, active gravity,
complete native timestep continuity, and native total-energy conservation still
require named receipts. Item 5 has a precise grid-relative source interpretation
plus unknown-frame and copied/manufactured boundary no-authority behavior. The
matrix must retain no-authority for those runtime/science operations until
their evidence is accepted.
CP06-B/07 own native `ww`, C-grid metrics, full EOS/mass coupling, actual
host source/build equivalence, and end-to-end continuity; CP01 does not require those downstream physical results to close this documentary binding.

### Reference-time implementation evidence update

The isolated actual 13 UTC reader passed pinned Intel O0/O2 and independent
scoped review: `scratch/cp01_contract_snapshot.hvp19t_7/reftime_13z_receipt.json`.
It accepts matched 06 UTC FSF/FUA at valid time 13 UTC and rejects four specific
reference-time mutations. Direct analysis-product callsites were source-reviewed;
the mutation run covers the FSF/FUA/LW3 path. A separate session is changing the
live reader, so these tests do not validate the current live implementation.
Whole CP01 remains IN_PROGRESS / NOT_RUN.

### New wind producer frame binding (2026-09-09)

The fresh pinned wind build and private 13 UTC invocation completed, with
source/input/config integrity recorded in `scratch/cp01_lw3_success_20260909`.
The parent verified the durable manifest, then verified its refreshed version
including `frame_interpretation_receipt.md`. Current compiled frame control is
`src/upstream/wind_openmp/main_sub.f` SHA256
`9bc4773852c48573f114f2ed2085a7ef4188ac774c21685aa287103f95fdebcf`, not the
older upstream driver. The hashed include fixes grid-north input/analysis/output
flags true; the log confirms observation rotation to grid north, and the reverse
output rotation branch is disabled. The new U3/V3 and SU/SV therefore have a
source/runtime-bound grid-relative interpretation. OM remains pressure vertical
velocity, separate from native ww. This interpretation is scoped to this new
execution and does not validate physical background-input assumptions.

New LW3 SHA256 is
`2eb193f38e98a2501d7ce4a887eb88ef97d434a151af6ae560903503222008fa`.
Historical final_ordered U3/V3/OM differ (RMS 0.1135018 m/s, 0.1524808 m/s,
0.0395943 Pa/s); no historical lineage or explicit NetCDF frame attribute is
established. The earlier SIGSEGV run is a retained failed attempt, superseded
only for the claim that fresh private generation is feasible. Whole CP01 is
not promoted by this producer receipt.

### Independent remaining-contract review

Luna high review verified the listed source/test/receipt hashes but found that
the named negative tests do not establish rejection of every host/canonical
mass, EOS, metric, energy or denominator mismatch. The list above is a required
contract, not blanket evidence that all its cases are implemented and tested.

| Convention | Canonical or diagnostic evidence | Host acceptance authority |
|---|---|---|
| Gravity | Canonical 9.80665 m/s2; native diagnostic explicitly uses 9.81 | Requires the named host source/build and metric binding; diagnostic value alone is insufficient |
| Gas EOS | Canonical Rd=287.05 and epsilon=0.622; native replay declares Rd=287 | Host thermodynamic variables and constants must be bound together; numeric coincidence is insufficient |
| Cell mass/area | Pressure-fixed A*dp/g and water correction are separate from native dry MU+MUB; source-derived native weight is `DX*DY/(MAPFAC_MX*MAPFAC_MY)` | Source flux factors and asymmetric-map cancellation are bound; runtime source/build, restart provenance, gravity and timestep closure remain required; unknown/mixed bases reject |
| A_E | Signed J under explicit `CLOUDBAL_MIXTURE_ENTHALPY`, with six-species sensible/reference terms | Meaning and units are bound; it remains separate from KDM6 `h_diabatic` and native total-energy acceptance |
| MP37 auxiliary denominator | Registry kg(-1) and m(3) kg(-1) establish dimensions | Explicit denominator and initialization provenance are required; stored zeros alone confer no authority |

The existing native hybrid checker is a read-only diagnostic and always reports
`native_authority=NONE` and `promotion_eligible=false`; it is not a native-state
adapter or enforcement proof for a promotable candidate. A focused auxiliary
contract validator and negative cases are the next implementation work. Full
native first-call, continuity and science remain downstream checks.

### Verified live reader time contract

The live enum-policy reader SHA256
`e56dd13129d9e532cc2e071ad1a0ef3703282e0163f73df4a84586c2c56f2187`
is now verified by [the current receipt](../scratch/cp01_live_time_4kzu5zp2/receipt.json).
The historical `01bf28`, `a092e8`, and `c29f62` source snapshots above are not
relabelled as this implementation. The current suite returns exit 0 under the
pinned Intel profile, including existing O0/O2 contracts and byte-identical
SHADOW outputs. The new O0 mutations cover all seven direct analysis products
and six legacy-reference failures. Actual 13 UTC acceptance and three singleton
mutations use the same compiled reader in `scratch/time_contract_receipt.UOHjSf`.

Analysis inputs require reference and valid time to agree within 0.5 seconds.
Forecast inputs require a nonfuture reference, with FUA and FSF in the same
cycle within 0.5 seconds. Adjacent FSF boundary files retain their same-cycle
rule. No forecast-age window is inferred. Direct mode never reads FUA/FSF.
These timestamp checks establish neither producer frame nor physical authority.
All 56 captured source/tool files and six pinned 12 UTC inputs match their
recorded hashes after execution. CP01 whole remains IN_PROGRESS / NOT_RUN.

### Current reader named-error validation completed

Final evidence is `scratch/cp01_time_contract_snapshot.c29_13z/reftime_named_receipt.json`
with artifacts `scratch/reftime_contract.B3gJos` beneath that snapshot. The
historical directory name contains c29, but the tested reader hash is
`e56dd13129d9e532cc2e071ad1a0ef3703282e0163f73df4a84586c2c56f2187`, matching
live at parent review. Pinned Intel O0/O2 compiled with each fresh mode directory
as the actual working directory, recorded in build_cwd.log. Both accept actual
13 UTC valid data from matched 06 UTC FSF/FUA and assert exact errors for analysis
shift/missing/NaN, future FSF, future FUA and mismatched FUA cycle. Parent
rechecked source/input manifests and retained log hashes. Earlier optional-time
and 8oiHS2 artifacts are superseded for current-reader claims.

`tests/run_named_reftime_contract.sh` installs this narrow test recipe with the
live repository's workspace-root default; shell syntax is checked. The frozen
O0/O2 execution is the runtime evidence, not an unperformed new live launch.
Direct-product broad-suite coverage and the boundary same-cycle negative test
remain separate; no full CP01 or native physical-boundary acceptance is claimed.

### Tested-reader revision clarification (2026-09-09)

Earlier e56/current wording refers to the historical frozen time-policy
executions. Later e665a39b and 74533e1b tested revisions are separately bound
in `AUDIT_REMEDIATION_20260909.md` and its linked receipts. The latest finite
payload repair does not resolve QN denominator/startup or physical-boundary
authority. Do not transfer a historical receipt to an arbitrary live checkout.

### Final scoped disposition — 2026-09-09

CP01 is COMPLETE / PASS at the six original contract/test criteria. Earlier
IN_PROGRESS statements above describe historical receipts. See the final
CP01_CONTRACT_EXIT_MATRIX_20260909.md and completion audit. Native execution,
physical-boundary authority and final conservation remain downstream.
