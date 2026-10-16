# PR87 native state-cycle investigation

> Historical initial cycle diagnosis and earliest candidate runs. Current runtime
> status is maintained in `PR87_TWO_STEP_COMPLETION_20261016.md`.

## Finding

The original native diagnostic directly confirmed the host-cutoff transition: six subthreshold QC cells with positive QNC after `POST_KDM6(1)` became number-only orphans after generic host cleanup and persisted to `FOGDES_INPUT(2)`. At `(230,70,3)`, QC changed from `8.4692146629095078e-9` to zero while QNC remained `2021875.875`; `rsl.out.0000` recorded that same FogDES rejection. The diagnostic observer's cleanup summary sampled k=1:39, while the actual zero-out call reaches k=1:40.

The producer-side candidate then bypassed only the second QC/QI/QR/QG cutoff for the KDM6 moisture call, preserving the KDM6 joint cleanup and validator. In the closed 40-second OFF and COUPLED runs, every cloud-cycle summary from `POST_KDM6_FULL_TILE(1)` through `FOGDES_INPUT(2)` reports zero mass-only and number-only cells; the cleanup observer uses the exact k=1:40 extent. At the probe coordinate, QC/QNC remain bitwise unchanged from `POST_KDM6` through `FOGDES_INPUT(2)`. Both runs later stop at the timestep-2 RK source-only check: the source-only failure ledger reports 582 infeasible cells in each arm. There is no FogDES reject marker in those runs. Each has one completed 20-second timestep and only a timestep-2 `PRE_RK` state, so neither is a completed two-timestep validation.

The effective `namelist.output` confirms `MP_PHYSICS=37`, `MP_ZERO_OUT=2`, `MP_ZERO_OUT_ALL=0`, and `MP_ZERO_OUT_THRESH=9.9999999E-09`. This establishes the direct host-cutoff cause in the diagnostic run. It is not a scientific approval or a clean full build: the original diagnostic uses a source-mapped partial native overlay, completes timestep 1, and aborts during timestep 2 FogDES. The cleanup candidate passes that FogDES boundary and fails later as recorded above.

## Native call and cleanup sequence

In the pinned candidate source, `solve_em.F` writes `POST_KDM6` immediately after `microphysics_driver` returns (around line 4135). The subsequent `moist_physics_finish` block calls `microphysics_zero_outb` for moisture arrays when `mp_zero_out > 0`, then calls `microphysics_zero_outa` for moisture arrays under the same flag (around lines 4174–4223). The stage dump is before both calls.

The effective diagnostic namelist directly prints all four settings above. In the matching WRF v4.8 `Registry/Registry.EM_COMMON`, the defaults for `mp_zero_out_all` and `mp_zero_out_thresh` are 0 and `1.e-8` (around line 2608–2609). In `phys/module_microphysics_zero_out.F`, `microphysics_zero_outa` loops over moisture species other than `P_QV` and sets values below the threshold to zero (around lines 30–63). Its scalar-array calls in `solve_em.F` are inside `IF (config_flags%mp_zero_out_all > 0)`, so the observed zero flag means QNC is not passed to the zero-out routine. `microphysics_zero_outb` clamps moisture boundary values to nonnegative values; it is not the small-value cutoff.

The next first-RK PBL driver call passes tile bounds and `k_start:min(k_end,kde-1)` into `pbl_driver` (`module_first_rk_step_part1.F`, around lines 1363–1364). The KDM6 branch calls `bl_fogdes_qn` with those tile bounds (`module_pbl_driver.F`, around lines 2332–2344). The helper loops over `i=its:ite`, `j=jts:jte`, and `k=kts:min(kte,kde-1)` (`module_bl_fogdes.F`, around lines 235–238). In diagnostic v2, `POST_KDM6_FULL_TILE` and `FOGDES_INPUT` report `i=1:234`, `j=1:282`, `k=1:39`. Its `POST_HOST_CLEANUP` observer call also capped the vertical extent at `k=39`, so that log is only a physical-level subset: the actual generic cleanup routines receive `k_start:k_end`, which reaches `k=40`. All six orphan coordinates are within the logged cleanup subset and the FogDES physical support, so this bound distinction does not change the observed cause. The corrected candidate observer records the exact cleanup extent separately.

The diagnostic receipt reports one completed model timestep, maximum observed timestep 2, and an abort on the second FogDES call. The candidate run receipts similarly record one completed timestep; their first complete timestep has a full Q/N/B audit, while timestep 2 has a `PRE_RK` record only. The four negative QV samples in that unfinished `PRE_RK` state are diagnostics on an incomplete state, not a completed-state admission failure or a negative cloud-pair finding. The source-only ledger and fatal logs identify the later failure separately from FogDES.

## Saved candidates

The machine-readable saved-state replay is [post_kdm6_cycle.json](evidence/pr87_state_cycle_20261016/post_kdm6_cycle.json). It records the PR86 compressed input hashes, active bounds, and six exact matching candidates. The original native diagnostic and its first-call identity check are recorded in [runtime_cycle.json](evidence/pr87_native_cycle_20261016/runtime_cycle.json). The later OFF/COUPLED candidate cloud-cycle traces, source-only failure counts, receipts, and exact probe values are in [candidate_cloud_cycle_40s.json](evidence/pr87_native_cycle_20261016/candidate_cloud_cycle_40s.json). The all-field stage audits are [OFF](evidence/pr87_native_cycle_20261016/completed_state_audit_OFF_40s.json) and [COUPLED](evidence/pr87_native_cycle_20261016/completed_state_audit_COUPLED_40s.json); both are correctly marked `INCOMPLETE` after timestep 1. The source-derived Intel O0/O2 host-cutoff replay is in [native_cycle_o0_o2.json](evidence/pr87_native_cycle_20261016/native_cycle_o0_o2.json), with method and scope in [PR87_NATIVE_CYCLE_REGRESSION.md](PR87_NATIVE_CYCLE_REGRESSION.md). The optional REAL32 storage-policy kernel tests are captured in [joint_storage_ifx_o0_o2.json](evidence/pr87_native_cycle_20261016/joint_storage_ifx_o0_o2.json); this unit test result is not a native model result.

| i | j | k | POST_KDM6 QC | POST_KDM6 QNC |
|---:|---:|---:|---:|---:|
| 230 | 70 | 3 | 8.46921466e-9 | 2,021,875.875 |
| 231 | 126 | 15 | 6.08270057e-9 | 1,452,137.5 |
| 159 | 162 | 4 | 4.89478680e-9 | 509,498.594 |
| 141 | 167 | 3 | 4.27826308e-9 | 1,021,359.938 |
| 168 | 184 | 7 | 5.13682608e-9 | 1,226,326.75 |
| 37 | 249 | 16 | 7.85803422e-10 | 187,596.719 |

For both PR86 arms the checkpoint has zero direct `QC=0, QNC>0` cells, while all six listed positive-QC cells are below the configured cutoff. The listed coordinates and values match exactly between those two saved states; this does not claim the complete state arrays are identical. In the separate native diagnostic run, these six cells are observed to become orphans after the host cutoff.

## Reproduce

```bash
python3 tools/pr87_stage_cycle.py \
  --off /var/tmp/pr86_budget_response_20261016/OFF/run/pr85_joint_moment_stages.raw.gz \
  --coupled /var/tmp/pr86_budget_response_20261016/COUPLED/run/pr85_joint_moment_stages.raw.gz \
  --threshold 1e-8 \
  --output docs/evidence/pr87_state_cycle_20261016/post_kdm6_cycle.json
```

The parser reads the stream-form stage records and extracts only timestep-1 `POST_KDM6` QC/QNC arrays. `python3 -m unittest tests.test_pr87_stage_cycle` checks the compressed record reader and prediction labeling.

## Source and run identities

The candidate source was read from `/var/tmp/pr85_native_joint_candidate_20261015v17/source`. SHA-256 identities:

- `dyn_em/solve_em.F`: `afd8e7a1180a523f86784d1740dcdbc4a9736c7bc1caeec6f1f46e4f6e4440dc`
- `dyn_em/module_first_rk_step_part1.F`: `de0d6f270dbd2a8aea8bcadcbb6690fc3fc57e2fd4a14261916fb9bbd4dbf880`
- `phys/module_pbl_driver.F`: `7868add7fe350337f1cba15987fbfdc1dffd47523a421294b973ada4db585eaa`
- `phys/module_bl_fogdes.F`: `aee27ecc6f259e94dfbb7cc8dad2ebd8cd97432d31363e268d1fedffa84bcc7d`
- WRF v4.8 `phys/module_microphysics_zero_out.F`: `a57268701b424b07a604ce93f733314183a29bfb39e7e6283f92f8668808fa4f`
- WRF v4.8 `Registry/Registry.EM_COMMON`: `4c8174711ed7ce50d4e04c3849254a77cbc963161aa42d6326ace4cf1fe0c700`

The OFF and COUPLED run receipt hashes are `c444c850f866f94bd8c0bd0c9e912bc608f8cc72d49b09a8ac4a5362b1253db9` and `0ff6c9234c92faa43793af2968ba1f38e4ebfc17433d2af733ba37225f036b81`, respectively. The stage stream hashes are in the JSON replay.

## Graphify coverage

Graphify was used for read-only navigation. The latest prior Cloud-BAL snapshot (PR86, 10,620 nodes, 19,063 edges, 924 communities) does not include the pinned candidate-source copies and runtime stage records used for this investigation. That extraction boundary limits graph-level navigation of the native driver path; the pinned source files, effective namelist, stage arrays, and runtime observer records are authoritative here. The parent task will refresh the maintained corpus separately; graph freshness is not runtime or scientific validation.
