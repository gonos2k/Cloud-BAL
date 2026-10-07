# PR67 negative QC completed-boundary audit

## Finding

The 23,494 negative QC values at the first KDM6 call are already negative at completed RK states. In the exact KDM active window (`i=2..233`, `j=2..281`, `k=1..39`), 21,441 first appear after RK1, 1,139 after RK2, and 914 after RK3. No negative QC cells are present before RK1 in the pinned transition masks. The per-cell mask timing agrees with the raw host observer after `rk_update_scalar`, diabatic handling, and the flow boundary.

For all 23,494 cells, the observer terms reproduce the native binary32 RK update and match the captured `AFTER_UPDATE` QC value exactly. Reconstructed scaled advection, combined tendency, and old/new mass denominators also match their captured values. Every old and new denominator is positive. This locates the completed-state boundary and verifies the update arithmetic; it does not identify a single physical process as the cause.

| First negative state | Cells | Advective tendency negative | Physical tendency negative / zero / positive | Still negative with advection omitted | Still negative with physical term omitted |
| --- | ---: | ---: | ---: | ---: | ---: |
| RK1 | 21,441 | 21,331 | 10,361 / 2 / 11,078 | 10,338 | 21,330 |
| RK2 | 1,139 | 1,109 | 138 / 168 / 833 | 137 | 1,108 |
| RK3 | 914 | 492 | 0 / 914 / 0 | 566 | 914 |

The omission columns are binary32 component screens using the captured RK equation. They are not independent physical interventions or a face-flux conservation replay. For RK3, 566 cells have a negative RK reference `base_q`; the `qc_before` value is nonnegative because the RK3 reference and current-state values differ. These results do not support a blanket advection-only or PBL-only attribution.

The KDM window is stable across `AFTER_UPDATE`, `AFTER_DIABATIC`, and `AFTER_FLOW_BDY` for each RK stage. The wider transition-mask totals are 163,244 / 399,233 / 23,539 at RK1 / RK2 / RK3; the 1,718 / 4,088 / 45 cells outside the KDM window are introduced by the flow-boundary stage. They are not part of the 23,494 KDM-entry negatives.

## Source interpretation and remedy scope

In the generated WRF source `dyn_em/module_em.F`, `rk_scalar_tend` (around lines 1096–1442) computes the scalar source tendency; at RK1 it can add horizontal diffusion when `diff_opt=1` and `mix2_off` is false. Its vertical-diffusion branch runs only when `bl_pbl_physics=0`; this case uses PBL option 11, so that branch is gated off. Afterward, `rk_update_scalar` (around lines 1587–1799) forms `tendency = advect_tend*msfty + sc_tend` and applies the RK base value, time step, and old/new dry-mass denominators. The captured aggregate physical tendency can still include multiple source contributions. The observer did not capture face-by-face advection fluxes.

The separate run3 per-channel columns are not used for process attribution. The SHCU and NC-SHCU channel values include invalid/uninitialized records (2,279 and 2,299 candidate rows, respectively), and the channel decomposition does not close. The aggregate physical tendency passed to the RK update is used instead. Since that aggregate includes multiple source terms, this evidence does not justify changing PBL mixing, advection, or the scalar update. No floor, clipping, damping, or other negative-value correction is proposed from this audit.

## Capture, controls, and limitations

- The observer source is an isolated generated `solve_em` copy under `/var/tmp/pr67_negativeqc_20261007/source_channels`; maintained WRF source and operational inputs were not edited.
- It was compiled and linked in fresh scratch paths with the pinned Intel 2026.0 `ifx` / `mpiifx` profile from `Cloud-BAL/tests/intel_toolchain.sh`. GNU, gfortran, and ifort were not used.
- The isolated source delta from the PR64 generated QC observer is preserved in [the observer patch](pr67_negative_qc_observer_source_delta_20261007.patch). Source SHA-256: `54c2697158a7d6efb307ba90956a17c4607cc5a7fb4a82fc3a18d974f704abed`; object: `c558e42adf8f1be82b56a5f30f22626accd72bc339255bb7a1f1bb81134e03bb`; updated archive: `8169576bf5fa0616223c00c97d2d8e370026e76d9516e8ad8e91a81379aac0cd`; linked executable: `835a0567c9caf4843358e40076f3a82ac25143de28d6d8bcec9a3fc09fe5f7df`.
- Run3 used the 101-file declared input subset. The run receipt reports return code 0, unchanged inputs, isolated outputs, and single-link outputs. The replay additionally binds the live `wrf.exe` to its unchanged receipt input hash and the separately linked executable hash.
- The observer `wrfout`, `namelist.output`, KDM6 pre/post captures, and transition masks/stages are byte-identical to the pinned PR65 run. The observer and baseline input hashes are retained in the JSON evidence.
- The first guarded launch was retained as a failed attempt: it exited 127 because the WRF HDF5 library path was missing. The successful run sourced the pinned compiler/MPI environments and added the established WRF `lib` and `lib64` paths. No inputs were changed by the failed attempt.
- The replay reads the raw event rows, transition masks, and KDM6 pre-state; it checks per-cell state sets at each RK boundary, all captured update terms, the binary32 equation, and the native post-update values. Extraction limitations remain: no face fluxes, and no closed per-process source decomposition.

## Reproduction

From the Cloud-BAL repository root:

```sh
python3 tools/pr67_negative_qc_replay.py \
  /var/tmp/pr67_negativeqc_20261007/run3 \
  /var/tmp/pr65_pbl_lineage_20261007/run_sharednc_postcapture_pinned \
  --expected-executable \
  /var/tmp/pr67_negativeqc_20261007/link_channels/main/wrf_pr67_negativeqc_channels.exe \
  --observer-source \
  /var/tmp/pr67_negativeqc_20261007/source_channels/solve_em_pr67_negativeqc_channels.f90 \
  --output docs/evidence/pr67_negative_qc_completed_boundary_20261007.json
```

The JSON is the machine-readable replay result. Hashes for the source, object, archive, executable, compiler command, run command, and raw observer are listed in the receipt and audit record; transient build and run artifacts remain under `/var/tmp/pr67_negativeqc_20261007`.

The focused replay guards pass with `python3 -m unittest tests/test_pr67_negative_qc_replay.py` (3 tests). Register this test file in the PR67 integration suite.
