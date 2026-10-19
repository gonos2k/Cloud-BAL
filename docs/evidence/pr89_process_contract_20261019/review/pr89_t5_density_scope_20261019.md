# PR89 T5 density evidence scope — 2026-10-19

## Captured failed-call data

The C1 OFF `pr85_joint_source_failure.raw.gz` record for `SOURCE 1 2 151 187 37` directly records the source pair, base pair, carriers, and candidate. It shows old/new carrier `95000`, base Q/N zero, source Q `6.050904193090068e-18`, source N `2.836211114367672e-2`, candidate Q `4.246248455315979e-22`, candidate N `1.990323541576933e-6`, and printed dry density `0.1140736`. The `FULL 5 1 2 151 187 37` row is also list-directed and prints `dt=6.666667` and the same rounded density. Those rows do not preserve the exact REAL32 density or dt bit patterns.

The corrected source-bound test dt is `6.666666507720947` (REAL32). The earlier test literal `6.666667_real32` rounded to a different value.

## Exact density witness and limit

The C1 `PR85QND2` stage trace at timestep 5, `PRE_RK`, and cell `(i,j,k)=(151,187,37)` records `DEN=0.11407360434532166`, REAL32 bits `3de99f6c`. The observer computes this field with `pr85_dry_density_from_al_alb` from `AL/ALB`. This is an exact witness for the pre-RK density at the target cell. It is **not** the density bit pattern directly captured from the later RK1 joint update that failed: the failure ledger lacks `AL/ALB` operands or a bit-exact `drydensity` field, and the pre-RK trace is a separate stage sample. Do not describe the pre-RK DEN as the exact failed-call input or claim a full-cell replay with exact rho.

The contract counterexample is still established for the source-derived Q/N endpoint with an explicitly labeled positive-density adapter. Exact failed-call rho is not required to establish the mismatch between strict host PSD storage and the actual KDM6 consumer's positive, subthreshold inactive-ice acceptance.

## Evidence identities

- C1 OFF receipt: `/var/tmp/pr89_OFF_120s_c1_20261019/receipt.json`, SHA-256 `4bca8dc76092e012fe732c8d68e951b3b45dd875752e5156e8db77f163bd4271`.
- C1 OFF source-failure ledger: `/var/tmp/pr89_OFF_120s_c1_20261019/run/pr85_joint_source_failure.raw.gz`, SHA-256 `f35bfdd67441be72b04b3de0eff491b2366bd444587b67d7db41827156ffd359`.
- C1 OFF stage trace: `/var/tmp/pr89_OFF_120s_c1_20261019/run/pr85_joint_moment_stages.raw.gz`, SHA-256 `513067757b00e8c2c0b1208cfe723093dd492afd154f30e1b2e9541986f50453`.
- Stage observer source: `scratch/pr89_process_contract_20261019/Cloud-BAL/tools/pr85_joint_stage_observer.f90`, SHA-256 `ea50fe2b380d2d5572da42f97261afe19eabdfef194edbfa5e4abc6360ee33bb`.
