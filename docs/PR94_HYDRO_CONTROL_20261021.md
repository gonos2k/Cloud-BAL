# PR94 current-generation HYDRO control

## Result

The current-generation HYDRO input passed independent prelaunch review and a 600-second native control was launched with the original C4 executable. Its forecast result is pending. It comes from the retained PR81 same13 joint thermo/density/Phi producer configuration with the background-continuity and force stages disabled. It uses the same 13Z real-reader inputs, support masks, thermodynamic equations, density prior, hydrostatic correction, and outer-iteration count as the retained joint producer. The produced candidate keeps U, V, and omega bitwise equal to the background.

The corrected final receipt is in the final2 evidence directory. The table below is generated from its JSON bindings; the receipt-file hash identifies the JSON receipt, while the wrfinput hash identifies the initialized model input.

| Artifact | Path | SHA-256 | Size (bytes) |
|---|---|---|---:|
| Receipt file | `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr94_physics_20261021/Cloud-BAL/docs/evidence/pr94_hydro_control_20261021/current_generation_final2/hydro_native_input_receipt.json` | `967a481070c37286f6aef8d616679583f1c86afb7dd60ac64f1d411977eba39b` | 3778 |
| Initialized wrfinput | `/var/tmp/pr94_hydro_current_inputs_20261021d/wrfinput_d01.moment` | `46760bdf03e42cbc8e1f5b415e1b304b535d369689f95a421a287d1eb90b679c` | 376278396 |
| Boundary input | `/var/tmp/pr94_hydro_current_real_buildcwd_20261021/wrfbdy_d01` | `885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7` | 51979816 |
| HYDRO candidate | `/var/tmp/pr94_hydro_current_O2_buildcwd_20261021/build/hydro_candidate.nc` | `97a98c5bb05a8dc70528c2b6c025ae8cb359ed46f23b7d3c28941535f71ae9d6` | 188477536 |


The comparison contract marks this as a current-generation control and records the two configuration switches. The boundary contract hash is checked against the staged boundary file by the final receipt writer. A bounded source comparison in `historical_vs_current_provenance.json` compares T, QVAPOR, hydrometeor mass fields, PH/PHB, winds, and pressure between current and historical raw and initialized inputs. It confirms that current raw and initialized inputs are not copies of the historical PR78 inputs; it also records fields that remain equal. The selected chain uses the same PR84 v2 moment policy body, with only a separate HYDRO source binding and provenance receipt.

The input-preparation work did not launch a forecast. After independent review and executable, profile, resource, and disk guards, root launched the forecast separately; the run is pending a closed completion receipt. The input receipt binds the original frozen boundary and exact current-generation HYDRO input; it does not confer scientific authority.

## Producer and configuration

The source is [the retained PR81 driver](../tests/pr81_joint_thermo_retained.f90), calling `run_cloud_bal_pipeline` in `src/common/cloud_bal_pipeline.f90`. Its `configure_trial` sets `MODE_SHADOW`, eight outer iterations, precipitation transport off, background continuity on, force refinement on, and the v2 density prior on at weight 0.5 with maximum increments of 5 K and 0.005 kg kg-1. The driver reads the same real shadow background as PR81 and takes the analysis, thermo, liquid-surface, and geopotential-reference supports from its retained same13 `coupled.nc` artifact.

The pipeline already provides the HYDRO branch for a caller that supplies `analysis_support` but sets `background_continuity_prior=.FALSE.`: it passes the thermo/geopotential candidate through without balance adjustment. Setting `force_prior_enabled=.FALSE.` skips `apply_background_force_prior_refinement`. The PR94 driver at [pr94_hydro_current_generation.f90](../tests/pr94_hydro_current_generation.f90) makes only those two configuration changes, omits the background-control, validation-shell, and force-support optional inputs, and asserts exact U/V/omega identity. It does not change equations, constants, support masks, source inputs, thresholds, or prior weights.

Both profiles were built and compiled with the working directory set to their fresh scratch `build` directory, using the pinned Intel toolchain from [intel_toolchain.sh](../tests/intel_toolchain.sh); the profile receipt records the actual build CWD. Earlier attempts compiled from the repository CWD and are excluded from this validation chain. O0 and O2 produced byte-identical candidate files (SHA-256 `97a98c5bb05a8dc70528c2b6c025ae8cb359ed46f23b7d3c28941535f71ae9d6`). The O0 run emitted Intel runtime warning 406 notices about array temporaries during diagnostic writing; it completed successfully with `PASS_PR94_CURRENT_GENERATION_HYDRO` and the same candidate hash as O2. No numerical gate or prior limit was relaxed.

## Input chain

The O2 candidate was mapped to the legacy WPS record format using the existing pressure-candidate adapter and writer. The hook retains background validity masks only after verifying exact equality with the source candidate masks; it imports the source candidate's `pressure_mass_measure` and `candidate_dry_air_mass_measure` so the canonical dry-mass contract is validated from authoritative product fields. An initial attempt to read validity masks directly through the Fortran NetCDF interface crashed; this was removed and replaced by the independent mask check. The corrected output passed readback for all 235 records.

That WPS file was run through the retained pinned Intel metgrid executable and passed same13 readback. The resulting `met_em` file was passed to the retained pinned Intel `real.exe`; its same13 real-input readback passed. The readback receipt describes only NetCDF validation and does not assert process execution. A separate `real_execution_receipt.json` binds the actual `mpirun -n 1 ./real.exe` command, wrapper exit code 0, executable SHA-256, real log SHA-256, new-run-root absence of `wrfinput_d01` before launch, generated output SHA-256 afterward, and unchanged pre/post source-input manifests. The existing PR84 v2 moment initializer then created the current HYDRO initialized input under a separately scoped policy receipt. The PR84 policy body is unchanged: the validator restores the PR84 schema/id and original authorized-source list, removes the HYDRO binding, and requires full JSON equality with the pinned PR84 policy, in addition to checking the original policy SHA. The HYDRO policy adds only its separate source-input authorization and provenance binding.

## Evidence

Bounded JSON receipts, profile files, and hashes are in [the final current-generation evidence directory](evidence/pr94_hydro_control_20261021/current_generation_final2/), [the superseded current-generation receipt set](evidence/pr94_hydro_control_20261021/current_generation/), and [the earlier historical PR78 evidence directory](evidence/pr94_hydro_control_20261021/). Large model inputs and candidate arrays remain in their external scratch locations; each manifest records their paths, SHA-256 values, and sizes without copying them into the repository.

Key evidence statuses are:

- Current producer O0 and O2: `PASS_PR94_CURRENT_GENERATION_HYDRO`; candidate bytes identical; exact wind identity passed.
- WPS adapter output: `PASS_PR94_HYDRO_WPS_READBACK`, 235 records.
- Metgrid: `PASS_SCOPED_SAME13_PINNED_INTEL_METGRID_READBACK`.
- `real.exe`: `PASS_SCOPED_SAME13_REAL_READBACK`.
- Moment initialization: `RESEARCH_PRIOR_CREATED` with PR94 HYDRO policy bound to the source stage receipt.
- Final current-generation input: `PASS_HYDRO_NATIVE_INPUT`, with the shared boundary hash verified.

Earlier in this task, a historical PR78 HYDRO candidate was also confirmed as a genuine actual product. Its background fields and masks match the PR81 candidate family, but its candidate thermodynamics and prior predate PR81's joint thermodynamic/density/force producer. That historical receipt is not the selected current-generation control, is not bound by this receipt, and must not be used to attribute CPL-HYDRO differences solely to force/balance. No wind-subtraction candidate was created.

The maintained KLAPS50 and Cloud-BAL Graphify snapshots were not changed in this task; this evidence records artifact and runtime-input provenance, not a graph refresh or scientific validation.

## Forecast status

The selected run is `scratch/pr94_physics_20261021/runs_on_lustre/HYDRO_600s_c4_current` under the KLAPS50 root. It uses original C4 executable SHA-256 `20aaa6058797e7d1ec7a874ae92ed44f9ac19876ef2f14477b5eedb6a1ae44be`, initialized input `46760bdf03e42cbc8e1f5b415e1b304b535d369689f95a421a287d1eb90b679c`, and the shared boundary recorded above. A launch is not a completed control or evidence of physical benefit. The continuity and force-prior switches change together, so their individual effects are not identified.
