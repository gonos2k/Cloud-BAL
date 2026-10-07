# PR68 KDM6 velocity and rate contract

## Contract

`slope_kdm6` computes terminal speeds from the distribution parameters as `pvtr * rslopeb * denfac` and the corresponding species constants. Its `vt` mass channels and `vtn` number channels are speeds in m/s. Sedimentation uses inverse-time rates, `speed / delz` in s⁻¹, to select minor steps and calculate per-layer fluxes.

The research patch gives slope outputs distinct `terminal_velocity_mass` and `terminal_velocity_number` arrays. At each sedimentation refresh point, `kdm6_velocity_rates` derives separate `mass_velocity_rate` and `number_velocity_rate` arrays. The terminal speeds remain unchanged, and mass fluxes use the mass rates while number fluxes use the number rates. The six `work1/workn` arrays keep their independent use by diffusion and condensation calculations elsewhere in KDM6.

No floor or replacement value is applied during conversion. Zero terminal speed remains zero rate; invalid or zero layer thickness is not silently hidden by the helper.

## Call-site inventory

The captured PR67 combined research source and the pinned original fixture each contain seven `slope_kdm6` calls. Three feed sedimentation transport and are followed by a rate refresh: the initial rain/graupel/ice evaluation, each rain/graupel minor-loop reevaluation, and each ice minor-loop reevaluation. Four other calls supply distribution calculations outside those transport refreshes. All seven write to the named terminal-speed arrays in the research patch. `work1` is also independently assigned by `diffac` and `conden`, so it is not a valid persistent velocity container.

| Role | Original fixture lines | Captured PR67 source lines |
| --- | ---: | ---: |
| Initial rain, graupel, and ice speeds plus rate refresh | 1047 | 1118 |
| Rain and graupel minor-loop refresh | 1152 | 1223 |
| Ice minor-loop refresh | 1218 | 1312 |
| Other distribution or process calculations | 1355, 1550, 2735, 2826 | 1463, 1658, 2850, 2941 |

Pinned original fixture: `tests/fixtures/kdm6_wrapper/module_mp_kdm6.F`, SHA-256 `02c9dc1f6711c9785d3c5841cbf2c14ebc454fa4628466407ae7f8879e965c5a`.

Captured PR67 combined research source: `/var/tmp/pr67_budget_capture_20261007/source/module_mp_kdm6_combined_research.f90`, SHA-256 `9efc09257a46102073b6d5a3d7cd12eb9ecd485526bc6e9cb349e4b2b037680d`. The exact research delta is [the patch artifact](evidence/pr68_velocity_contract_20261007.patch).

## Validation scope

`tests/run_pr68_velocity_contract.sh` requires the captured source hash above, applies the patch in a fresh `/var/tmp` build directory, checks all seven slope call arguments and the three refresh/wiring points, checks that terminal-speed conversion does not mutate `work1/workn`, extracts the patched helper, and compiles/runs its direct unit-contract test with the pinned Intel profile at O0 and O2. The run summary is [the validation receipt](evidence/pr68_velocity_validation_20261007.json).

The helper accepts the full `delz(ims:ime,kms:kme)` bounds while rates and velocities cover only the active domain; this preserves halo indexing. The Fortran test checks that mapping using halo sentinels and nonuniform layer thicknesses, separate mass and number channels, preserved terminal-speed inputs, three successive minor-loop refreshes, equivalent m/s and cm/s representations, zero flux for absent mass/number moments despite nonzero speed, and the exact zero-speed case. The transport wiring checks confirm that the rate arrays feed the current-source substep limit and mass/number flux expressions. This is a direct rate-kernel and source-wiring contract, not a full model no-rain case or a full-model microphysics budget/scientific check.

The maintained 7,424-node Graphify snapshot exposes `kdm6`, `kdm62d`, and `slope_kdm6` nodes in the pinned fixture, which helped navigate the call relationships. That snapshot indexes the fixture, not the captured PR67 combined source; the latter and the pinned fixture remain the source authorities for this patch. Graph freshness is not runtime validation.

## Guarded matched native runs

The corrected patch also updates the PR67 process observer to capture `mass_velocity_rate(:,:,4)` after the ice minor-loop refresh. It formerly read `work1(:,:,4)`, which is no longer the transport-rate array after the refactor. The observer correction changes only the diagnostic capture; it does not alter transport calculations.

### Strict O2 matched pair

The strongest paired check uses fresh baseline and candidate KDM6 objects compiled with the same pinned Intel `CLOUD_BAL_REPRO_FLAGS` contract (`-O2 -fp-model strict -no-ftz`, with big-endian data conversion), then replaces the KDM6 member in otherwise identical copies of the captured combined archive and relinks against the same host objects and dependencies. The source, object, archive, executable, expanded compiler/link argv, and guarded run receipts are retained under `/var/tmp/pr68_velocity_native_20261007/matched_o2/{baseline,candidate}`.

Both one-rank 20-second runs exited 0. Each receipt reports 101 unchanged inputs and 16 outputs passing the isolation guard, with all output files single-link. The physical and observer products match byte-for-byte between the fresh baseline and candidate: geometry, transition stages and masks, KDM6 pre/post traces, process capture, and wrfout. RSL logs, launch-environment captures, and runtime-library listings differ across the two directories. This is scoped bitwise parity for the recorded model products under the strict O2 profile, not a full host compiler-closure or scientific acceptance result.

The matched O2 wrfout still fails the existing reflectivity safety condition. At `2026-08-16_12:00:20`, both baseline and candidate have 25 nonfinite reflectivity cells with the same mask SHA-256 `f8750861800823e492c163be0a9bd698701e97beeb865f767dbffb4ce705e448`; all 25 overlap positive rain mass with zero rain number. The KDM6 post trace also has one positive-cloud-water/zero-cloud-number cell. These identical failures are not repaired by this velocity refactor and are not a PASS.

The receipt-bound same-call six-water accounting is also identical for baseline and candidate. It reports `-4.92401757921875e8 kg` six-water storage change, `4.9893142755044574e8 kg` mapped precipitation increment, and `6.529669628570735e6 kg` focused residual. This is a one-call diagnostic, not whole-scheme water or energy closure.

### O3 exploratory pair

A separate candidate used the captured host's `-O3 -fp-model precise -ftz` selected-object flags. The corrected O3 candidate preserves geometry, transition stages/masks, and the KDM6 pre-call trace, but its post-call trace and wrfout differ from the retained combined PR67 run. The decoded traces contain no NaNs in either run. The differing post-call fields and maximum absolute differences are: TH 25 cells (6.104e-5), Q 411 (9.313e-9), QC 694 (9.779e-9), QR 689 (2.328e-10), QI 866 (1.164e-9), QS 490 (1.164e-9), QG 210 (1.164e-9), NN 589 (1.94304e5), NC 96 (4.26432e5), NI 129 (499.44), NR 326 (1.953e-3), BG 203 (1.307e-12), and DIAGRHOG 64 (3.052e-4). `TH` is WRF potential temperature; actual temperature is `TH*PII`. These are observed differences, not a precision diagnosis. The first O3 attempt also used a stale process-observer field; that attempt is retained separately and is not used for the corrected observer comparison.

For the corrected O3 process capture, 840 stage records decode with no NaNs. Against baseline, the ice-rate observer has 543 unequal cells (maximum absolute difference 3.803e-10); first-substep ice state has 110 unequal values (2.328e-10 maximum), first-substep flux 521 (9.095e-13), and accumulated fall 546 (9.095e-13). The strict O2 pair's corresponding products are byte-identical. The O3 comparison remains non-neutral and its cause is not inferred from the magnitude of the changes.

The corrected O3 candidate provenance is captured source SHA-256 `9efc09257a46102073b6d5a3d7cd12eb9ecd485526bc6e9cb349e4b2b037680d`, patched source SHA-256 `aeda1032e6255fda5404a48a6a698020ea914215d8e2851f8d6f8b5bb1930ce2`, object SHA-256 `1c170a5a77f532fcb843dccec2a0b71c8427c0702960ee301d02cc4306fe6e29`, archive SHA-256 `5d6b240df7e377f0dd0df365ddeac4b2d418f6b4632eb4cdbc1d7ccafc7e2a66`, and executable SHA-256 `9559499836a37cf70f4e43f69bf67a3e6c7687246405b2021ea23c94f06abdfa`. Its expanded compiler and link argv and guarded run receipt are in `/var/tmp/pr68_velocity_native_20261007/revised_o3/`. The O2 baseline and candidate identities and receipts are recorded in the machine-readable validation receipt.

## Manufactured wrapper failure

The whole KDM6 manufactured wrapper is a separate check and remains a failure. I rebuilt the same O0 harness against both the unmodified captured PR67 source (SHA-256 `9efc…680d`) and the candidate source (SHA-256 `97e9…bfdaa`), with the same test source (SHA-256 `94f578ca51656fad7f3f816ceec305a47f3394acbd0e67cc0d0a36dd7b388c1c`) and pinned Intel profile. Both runs exit 12 at density 1 in the harness's positive-number assertion and print the same failed state. This establishes that this assertion failure is present in the matched baseline harness too; it is not evidence that the velocity patch caused it. The failing candidate and baseline `run.log` files and complete build/run logs, source copies, and executables are retained under `/var/tmp/pr68_velocity_wrapper_candidate_20261007/` and `/var/tmp/pr68_velocity_wrapper_baseline_20261007/`; their runtime log hashes are in the validation receipt. The assertion has not been weakened.

The direct rate-helper contract tests pass at O0 and O2 in `/var/tmp/cloud_bal_pr68_velocity.DAzSaj`; the generated helper receipt is `validation.json` with SHA-256 `26229e389b6446d71e9b797747a10b172b5e185a46d3451b6b01001aa4787443`. The curated receipt at `docs/evidence/pr68_velocity_validation_20261007.json` records the helper, matched native runs, wrapper control, and failure hashes without being overwritten by subsequent helper runs. These scoped checks do not establish full-model physics closure or scientific approval.

## Open item

This patch is a research artifact against the captured PR67 combined source. The maintained WRF source and the original fixture remain unchanged. A later integration must rebase these named arrays and helper into the selected production source and run the native model validation suite.
