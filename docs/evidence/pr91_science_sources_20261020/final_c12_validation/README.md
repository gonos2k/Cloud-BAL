# C12 focused regression validation

The focused suite passed 55 unique pytest cases in 34.78 s. It ran the historical 19-file C10 focused list plus the C11 capture-writer regression. At test collection, the source-first test file had seven C12 cases, the C11 test file had two cases, and the remaining focused files contributed 46 cases. O0/O2 fixture subprocesses are included inside their pytest cases, not added as separate pytest counts.

The standalone `test_joint_qnb_transport.f90` also passed at pinned Intel O0 and O2 from separate clean `/var/tmp` directories. The O0 log preserves existing subnormal-conversion remarks and runtime array-temporary warnings; both runs ended with `PASS test_joint_qnb_transport`.

After the focused run, the owner corrected the source-first test's D3 input paths to use repository-pinned artifacts. The first run collected the seven-case source-first file at its pre-path-fix hash. After the owner froze the updated test at SHA-256 `9e8756b2d48774d5eaf692d016be46a09fb0286bf924bb169901549793cb249b`, its seven cases were rerun independently and passed in 10.93 s. The updated test now uses `validation/final_i/module_em.F` and `c12/inputs/solve_em_c7.F`; hashes are recorded in `source_pins.json`.

All compilation used `tests/intel_toolchain.sh` with pinned ifx 2026.0.0, strict floating point, and fresh `/var/tmp` scratch. The exact commands and raw stdout/stderr streams are preserved here. This is focused regression evidence only. It is not a native/model run, source validation approval, or physical approval; final freeze remains open pending the root's closed runtime evidence.

A second standalone O0/O2 capture preserved combined compiler/runtime stdout and stderr after the initial logs were found to contain only test stdout. Both fresh-scratch runs passed. The combined logs include the existing REAL32 subnormal conversion remarks and array-temporary runtime warnings; they are warnings from the established joint-store test and did not change either pass result.
