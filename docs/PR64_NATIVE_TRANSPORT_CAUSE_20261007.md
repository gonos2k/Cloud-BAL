# PR64 native QC/NC transport cause investigation

## Finding

The valid PR63 `run_transition_v2` capture shows QC remaining small and positive at `(172,76,1)` while NC is strongly negative after RK1 and RK2, then is zero at RK3. At POST_MICROPHYSICS, the selected cell is QC=`3.0767936e-7`, NC=0. The stage records establish a transient at the selected cell; they do not, by themselves, establish that the intermediate state violates physical closure.

| Checkpoint | QC | NC |
| --- | ---: | ---: |
| PRE_RK | 0 | 0 |
| RK1 | `1.6839790e-7` | `-1773.7578125` |
| RK2 | `2.5137101e-7` | `-3662.8056641` |
| RK3 | `5.0365270e-7` | 0 |
| POST_MICROPHYSICS | `3.0767936e-7` | 0 |

The transition record stores `max_negative_qc` separately from the selected target-cell QC/NC fields. For POST_MICROPHYSICS, global `max_negative_qc` is `-1.16914733894e-7`; selected target QC is `3.07679357547e-7` and selected target NC is zero. The global host-tile negative-QC count at RK3 is 23,539; `23494` is the KDM active-entry count. Neither count is a coordinate or a count for the selected cell. Per-cell update-cut values from `run_paired_v2b` belong to a failed run and are not used here.

## Source path

In the native driver, moist scalars are advanced by separate `rk_scalar_tend` and `rk_update_scalar` calls. QC is processed in the moist-scalar loop before NC is processed in the separate scalar loop (`solve_em_pr63.f90`, calls near lines 2647/2741 and 3052/3127). Each update combines the advection contribution and the non-microphysical scalar tendency, then applies the RK mass-coordinate update:

`tendency = advect_tend * msfty + sc_tend`

`scalar_new = ((c1*muold_total + c2)*scalar_old + dt*tendency) / (c1*munew_total + c2)`

Here `muold_total = mu_old + mu_base` and `munew_total = mu_new + mu_base`, formed in `rk_update_scalar` before the update loop.

These equations are implemented in `module_em.F` within `rk_update_scalar` (around lines 1700–1720). `rk_scalar_tend` constructs advection via the selected scalar advection routine, then accumulates horizontal and vertical mixing/diffusion terms. A fresh solve-only observer run on the unchanged archived advect member recorded target NC `advect_tend=-2.5722700e7` with `sc_tend=0` at RK1, and `advect_tend=-3.5411072e7` with `sc_tend=0` at RK2. The `msfty`-scaled tendencies and native mass-coordinate update reproduce the observed NC changes. This attributes the large negative NC tendency to advection at these stages; donor-face attribution remains open. The valid PR63 executable's archived `module_advect_em.o` is bound to the PR61 patched generated source SHA256 `a1dc18bce40f84ad709d38fbe7b0658590e587d42528b1124f9c8b7e9c1830fa`, not the maintained source-tree `module_advect_em.F`.

The first observer showed that the positive QC tendency predates scalar advection, but did not capture its input channels. A follow-up observer below resolves that channel attribution.

The observer run captured target tendencies and mass-carrier fields. At RK1/RK2, NC `sc_tend` is zero and its `advect_tend` is large and negative; the mass-coordinate carrier changes slightly between old and new values. QC's positive preexisting tendency and negative advection are both recorded, but their upstream source channels and donor-face contributions remain unmeasured. At POST_MICROPHYSICS the target is QC-positive/NC-zero, while a different cell contributes the global negative-QC minimum. No floor, clipping, or artificial omega was added.

## Runtime and provenance limits

The historical valid-v2 binary/archive remains the authoritative baseline. An initial observer run used a direct `.F` compile and a mismatched floating-point profile; it is retained as a separate failed-equivalence attempt. The solve-only observer archive retained the historical advect member exactly and reproduced the valid transition-stage, geometry, KDM pre/post, history, and model-output file hashes. The observer solve object is a new object; no whole-host clean build or recovered historical solve-object identity is claimed. Native donor-face values are not yet captured.

Two compiler commands in the early attempt used the workspace as their current directory and created compiler-generated module/interface files there. Only those exact newly created untracked byproducts were removed; subsequent compiler invocations used fresh `/var/tmp` working directories. The maintained WRF source was not modified.

## Follow-up QC channel capture

A separate guarded run added a small observer immediately after `first_rk_step_part2`; it writes the target `moist_tend(P_QC)` and QC/NC physics channel arrays. At `(172,76,1)`, RK1, the captured `moist_tend(P_QC)` is `0.0024263537488877773`. `rqcblten` has exactly that value; `rqccuten`, `rqcshten`, `rqcncuten`, and `rqcnshten` are zero. The active options are `BL_PBL_PHYSICS=11`, `CU_PHYSICS=37`, and `SHCU_PHYSICS=0`. `module_state_description.F` defines `SHINHONGSCHEME=11`; `module_physics_addtendc.F` handles that PBL case by adding `RQCBLTEN` directly into `moist_tendf(P_QC)` through `add_a2a`.

The same run has `DIFF_OPT=1`, while this `first_rk_step_part2` source enters both its vertical- and horizontal-diffusion block only when `DIFF_OPT=2`. Those diffusion calls are therefore skipped. Together, the runtime channel values and source branch establish that the `+0.0024263537488877773` pre-advection QC tendency is the PBL `rqcblten` contribution in this case. The recorded value is in the native tendency units accumulated by `add_a2a` and consumed by the carrier-coordinate RK update; it is not a standalone mixing-ratio rate. This identifies the tendency channel; it does not resolve the internal PBL parameterization process that generated `rqcblten`.

The follow-up used a new observer solve object and executable, kept the valid-v2 archive and archived `module_advect_em.o` unchanged, and ran with a fresh guarded input tree. The ten listed baseline stage, geometry, KDM, history, log, namelist, and model-output artifacts match byte-for-byte. The small observer patch in `docs/evidence/pr64_qc_channel_observer.patch` applies to the hash-bound PR63 generated solve source; patch replay reproduced the compiled source hash. The compile, archive, link, and run-guard command records are under `docs/evidence/pr64_qc_channel_*`; focused replay is `tools/pr64_qc_channel_replay.py`. Compiled/runtime identities and captured values are in `docs/evidence/PR64_QC_CHANNEL_SOURCE_20261007.json`. No maintained WRF source was changed. The earlier source-tree compiler byproduct incident is recorded above; this follow-up compile used a fresh `/var/tmp` working directory.

**Disposition:** target NC RK1/RK2 tendency is attributed to scalar advection; the preexisting positive QC tendency is attributed to the active PBL QC channel. Individual NC donor-face values and the internal origin of the PBL tendency remain open. Full-physics validity remains FAIL/OPEN.
