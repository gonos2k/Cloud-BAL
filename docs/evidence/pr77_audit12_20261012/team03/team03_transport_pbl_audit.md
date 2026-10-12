# Team03/12 — upstream transport, PBL, and RK coupling audit

Date: 2026-10-12  
Scope: Shinhong PBL scalar transport, DEL carrier, QC/NC and QI/QNI coupling, scalar-tendency ordering, diffusivity/positivity, and the completed-state boundary between host processes.  
Cloud-BAL source snapshot: `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL`, HEAD `9701ef23f04576d875508a0882d0e0af67282587` plus frozen PR77 worktree. Read-only review; no source or receipt edits and no builds/reruns.

## Findings

### T03-1 — Shinhong QC/NC and QI/QNI shared transport exists only in the PR73 research source, not in the inspected hostcopy Shinhong source

**Class / priority:** Missing implementation in inspected host snapshot; P1 for a configuration requiring paired Shinhong transport.  
**Trigger:** `bl_pbl_physics=SHINHONGSCHEME` with active QNC and/or QNI scalar fields.  
**Evidence:** `/var/tmp/pr61_ccn_origin_20261006/hostcopy/phys/module_bl_shinhong.F:103-104` fixes `ndiff=3`; lines 202-217 pack vapor, QC, and optional QI only, and the entry signature at lines 9-29 has no QNC/QNI arguments. The matching host driver branch at `.../module_pbl_driver.F:1294-1330` passes QV/QC/QI and their mass tendencies but no QNC/QNI channels. The PR73 research copy at `/var/tmp/pr73_pbl_research/source_after/module_bl_shinhong_pr65.F:179-186,211-238,249-256,291-299` adds optional NC/NI channels and packs them into the common solve; its driver at `.../module_pbl_driver_pr65.F:1324-1332,1350-1376,1383-1414` gates and accumulates those rates. The research file hashes differ from hostcopy (`5fbe821…` vs `99f44db…` for Shinhong; `5044fb26…` vs `90336e30…` for driver), so this is a research implementation, not evidence that the read-only host source includes it.  
**Assessment:** In the inspected host source, Shinhong transports QC and QI but does not transport the corresponding NC and NI fields. Existing QNI handling elsewhere in the host driver (MYNN path) does not close this Shinhong branch. PR65/PR67/PR74 research evidence demonstrates a selected patched operator path, not host-source integration.  
**Uncertainty:** `/var/tmp/pr61_ccn_origin_20261006/hostcopy` is the requested retained host snapshot; this audit did not establish whether another unprovided production source tree contains the research changes.  
**Next check:** Bind the intended production/generated Shinhong source, driver, compiler input set, and archive member, then verify that the selected Shinhong branch passes and applies QNC/QNI rates exactly once.

### T03-2 — Shinhong’s implicit mixing matrix is DEL-weighted, not dry-air-mass-weighted

**Class / priority:** Archived same-call runtime/replay finding; P1 for a dry-carrier conservation claim.  
**Trigger:** interpreting conservation of QC/QI or specific NC/NI through the Shinhong vertical solve as dry-air-carrier conservation.  
**Evidence:** Research source `module_bl_shinhong_pr65.F:637` sets `DEL(k)=P3DI(k)-P3DI(k+1)`; its driver passes `P8W` as `P3DI` at `module_pbl_driver_pr65.F:1350-1354`. Moisture matrix coefficients at `:1301-1334` scale by `dt2/DEL` while using `dsig=P2D(k)-P2D(k+1)` and `xkzq` in the flux coefficient. Archived PR67 same-call evidence (`docs/evidence/pr67_pbl_samecall_carrier_20261007.json`, `docs/PR67_PBL_SAMECALL_CARRIER_20261007.md`) records exact agreement between operator DEL and captured P8W differences, but total DEL differs from the linked dry layer pressure by up to 60.60 Pa (1.86%). For the same matrix, replay reports dry-mass left residual `220,058 kg` (`8.77e-7` of dry column mass), versus DEL-weighted residual `984.8 kg` (`3.89e-9` of DEL-weighted column mass). Hybrid coefficients are static-linked to the captured input because retained `head_grid` layout checks failed; the evidence is not a live hybrid-coefficient capture.  
**Assessment:** The existing selected-matrix replay closes much more tightly in DEL measure than in dry-air measure. It does not establish a dry-carrier conservation pass; PR67 explicitly leaves that open.  
**Uncertainty:** This is a selected `(i,j)=(172,76)`, first-timestep research call with linked static coefficients, not a full-domain or clean-host validation.  
**Next check:** For production-bound coefficients and a completed call, construct/replay the operator using the same dry-air layer measure used by dynamics, and report per-column residuals for QC/QI/NC/NI on the same carrier. Preserve the existing DEL result as a separate diagnostic.

### T03-3 — PBL diffusion has no local fail-closed geometry or scalar-positivity gate

**Class / priority:** Static source limitation; P2 conditional robustness risk.  
**Trigger:** nonpositive/nonfinite P8W thickness, mass-level pressure difference, geometric spacing, or diffusivity; or negative/nonfinite scalar input.  
**Evidence:** `module_bl_shinhong_pr65.F:637` computes DEL without a local check. The moisture operator at `:1301-1321` divides by DEL and `dza`, forms flux coefficients from `dsig*xkzq`, and then solves via `tridin_ysu` at `:1387`; there is no local validation/rollback of those inputs or of the result before tendency reconstruction at `:1403-1444`. The viscosity floor/cap at `:1311-1314` applies only in one entrainment branch and is not a general finite/positive check. All channels inherit `ifvmix(:)=.true.` at `:599`.  
**Assessment:** With positive thicknesses, positive diffusivity, and finite inputs, this tridiagonal diffusion operator has the expected nonpositive off-diagonals and positive diagonal/row dominance in the archived selected matrix. That conditional M-matrix property supports nonnegative-input preservation for the closed QC/QI/NC/NI channels. It does not provide a general state positivity guarantee for invalid inputs, surface-forced vapor, or subsequent RK tendencies. PR67 tests/matrix evidence are scoped to one selected matrix.  
**Uncertainty:** Static absence of checks identifies the invalid-geometry trigger path, but no malformed-geometry execution was performed and no whole-domain matrix sweep was run.  
**Next check:** Add a focused, source-bound invalid geometry test and a nonuniform positive-input preservation check; separately retain the production solver’s rollback/failure behavior rather than clipping tendencies.

### T03-4 — QI and QNI enter separate host RK/advection paths with independently selected schemes

**Class / priority:** Conditional coupling gap; P2.  
**Trigger:** `moist_adv_opt` and `scalar_adv_opt` select different advection operators, or one path is positivity limited and the other is not.  
**Evidence:** Host RK calls `rk_scalar_tend` for moist fields with `config_flags%moist_adv_opt` at `/var/tmp/pr61_ccn_origin_20261006/hostcopy/dyn_em/solve_em.f90:2625-2667`; the scalar loop uses `config_flags%scalar_adv_opt` at `:3038-3077`. `rk_scalar_tend` dispatches among positive-definite, monotonic, WENO/WENOPD, and default scalar advection at `module_em.F:1269-1349`, and adds the chosen advection tendency before `rk_update_scalar` is called at `solve_em.f90:3121-3151`. In the PR73 Shinhong research extension, QI is still a moist tendency, while QNI is accumulated to `scalar_tend` once at `module_pbl_driver_pr65.F:1405-1414`; the host RK then advances the two through those distinct loops.  
**Assessment:** The PBL research matrix couples QI/QNI in one vertical solve, but the subsequent horizontal/vertical advection and RK advancement do not enforce a shared pair limiter or same selected scheme. This is a configuration-dependent risk, not a reproduced mismatch. No PBL/host same-candidate completed step establishes whether the selected run configuration triggers it.  
**Uncertainty:** The available PR74 and PR77 executions stop before a completed native KDM6 call/timestep; the audit did not infer a pair divergence or its origin from an entry-state mismatch.  
**Next check:** Capture the actual production `moist_adv_opt` and `scalar_adv_opt`, then compare same-stage carrier-weighted QI/QNI transport tendencies and post-RK pair admissibility under the exact configured options.

### T03-5 — Latest native state remains an entry-only domain; it cannot identify a PBL origin

**Class / priority:** Reproduced gate / evidence boundary; P1 for end-to-end acceptance.  
**Trigger:** treating a pre-microphysics entry state as proof of completed microphysics or attributing its first invalid pair to PBL.  
**Evidence:** PR77 integration progress (`docs/PR77_INTEGRATION_PROGRESS_20261012.md`) records the corrected KDM6-entry first violation as ice at `(i, call_lat_index, k)=(104,2,1)`, `Q_I=0`, internal number `4.20387925e-36 m^-3`, and public number `3.81730490e-36 kg^-1 dry air`; the KDM6 validator exits 128 before a completed physics call. It explicitly states the latitude is a wrapper call index and does not claim global-j mapping. PR74 QNI driver evidence (`docs/PR74_QNI_ACTUAL_DRIVER_MOMENT_COMPARISON_20261008.md`) has an earlier retained run/capture: actual Shinhong branch completion with 39 returned levels and one scalar-tendency addition per level, followed by KDM6 rejection before common paired-state preflight. That historical PR74 pretrace’s first classification is not substituted for the corrected PR77 runtime first failure.  
**Assessment:** No completed-state evidence is available after the failing first KDM6 call, so the relevant host process boundary ends at KDM6 entry. The PR77 first ice gap is not evidence that PBL created it; stage-bound origin evidence is absent.  
**Uncertainty:** PR74, PR67, and PR77 are distinct observer/research runs. PR67’s selected PBL call and PR74/PR77’s KDM6 entry are not a single bound candidate/cell history.  
**Next check:** Complete a source-bound candidate through one KDM6 return, then capture same-candidate PBL input/output, all RK stages, and KDM6 entry/return to localize the first pair-state transition.

## Coverage inventory and exclusions

- Read-only inspected host files: `phys/module_bl_shinhong.F`, `phys/module_pbl_driver.F`, `phys/module_physics_addtendc.f90`, `dyn_em/module_first_rk_step_part1.f90`, `dyn_em/module_em.F`, and `dyn_em/solve_em.f90` under `/var/tmp/pr61_ccn_origin_20261006/hostcopy`.
- Read-only research source: `/var/tmp/pr73_pbl_research/source_after/module_bl_shinhong_pr65.F`, `module_pbl_driver_pr65.F`; used only as research comparison.
- Existing evidence reviewed: PR65 lineage/NC records, PR67 same-call carrier report and JSON, PR74 common-moment/QNI actual-driver comparison report and JSON, PR77 integration progress and native-state receipt. Evidence outcomes remain attributed to their declared runs and source bounds.
- Maintained graph query: Cloud-BAL graph under `scratch/pr77_native_state_20261012/Cloud-BAL/graphify-out/graph.json`, 1,499 nodes/3,094 links. Query using graph-vocabulary terms `ice scalar transport state cloud pipeline` returned 322 nodes, mostly Cloud-BAL assessment/pipeline symbols. No PBL, QNC, QNI, or Shinhong nodes were present. Graph therefore did not represent the external hostcopy or research source used for this audit; it served only to locate maintained Cloud-BAL state/transport docs. No graph update was made because this was a read-only audit and no maintained corpus source changed. No graph delta is claimed; graph freshness is not runtime or scientific validation.
- Excluded: Team02 internal microphysics source mechanism/origin analysis; Team04 compiler/FP/build review; Team05 budgets; upstream startup/parallel FP policy; broad reruns, builds, source edits, and any inference of pre-PBL origin.

## Validation and status

Static source tracing plus archived evidence inspection only. No compilation or new runtime reproduction was performed. Strongest quantitative runtime evidence is the archived PR67 selected-matrix/PBL call replay; it is not same-candidate PR77 closure. Overall host/PBL paired-state closure remains open. Priority next step is production source/object binding and one completed, stage-bound native first call with same-carrier checks.
