# Independent C10 code and evidence review — 2026-10-20

## Reviewed identity

The maintained transform is pinned to the immutable D3 `module_em.F` SHA-256 `dc21f48b29784f7ab6bbb6975ef541d184b31effa796b0e5aab51b16e80d406d` and C7 `solve_em.F` SHA-256 `412183300ea8dd6af028ac1a5254f937477b054db4eb1f5910a6bf974c3c5`. The current generator is SHA-256 `6cd06d2d81bfb829ff1703abaefb86483de89dd536b4a18d374a90da101e697e`; its current test is `3d07b17312c26514065d4587a7d6d57cc4f76bdbe74f87d47b7852506a7c292b`. The generated C10 module/solve pins are `af54a8bd951e47407f6900dbfd4b16396cd6fc30753bb32437fd46c45b86be4c` and `dd3d8436ec6e7712ea8b62a33502acf89832f2d8a9f45969f84968f06ff78ca6`.

The C10 selected-object overlay receipt is SHA-256 `751283f094c12c6841933c0a9726a4ff4d9948609ab87ea1a15a6a9b5d65bc55`; it records pinned Intel `ifx 2026.0.0`, a partial overlay (`full_clean_build=false`), and `model_run=false`. Its executable remains external and is bound by SHA-256 `286b1c538deb8e83a7456134c301930620d2fc072ac4001e8a82df47dcd77b8d`.

## Source and test inspection

C10's transform starts from D3 source rather than the C8/C9 transformed endpoint. The C10 source-stage cloud `joint_moment_store` retains D3 strict mean-mass semantics without the premature volume-number argument. The later joint consumer still supplies volume bounds to the existing final paired store. The transform captures the old REAL64 horizontal-diffusion increment, evaluates the existing diffusion routine against the full source-prepared Q/N fields under the recorded RK1 geometry, and applies the new-minus-old diffusion difference once. Its cache checks require paired channels and matching step/footprint identity. Candidate construction remains downstream of the prepared diffusion/donor pass.

The test pins D3 and C7 source hashes and checks the transformed call ordering, source-stage versus final-store options, and captured diffusion replacement expression. Its four cases include an operator fixture at O0/O2 and a T2 fixture at O0/O2. The latter exercises the existing shared core with the recorded intermediate: D3 mass-only storage produces R32 `34784CDA/4C529864`; the same intermediate fails strict dual-product volume validation; the existing final store with volume bounds and normal-Q adjustment succeeds as `34784CDB/4C529864`. This verifies the helper contract for those exact operands. It does not establish that native C10 reaches the same state or that the complete physical update conserves globally.

## C9 failure separation

The archived OFF and COUPLED C9 receipts both show `INCOMPLETE`, rc=1, one completed POST_KDM6 step, and first failure at T2. The same captured T2/RK3 pair-1 cell `(106,55,6)` source endpoint is rejected by the C8 strict continuous volume gate at stage 3 before C9's prepared diffusion replacement. This is a C9 failure and does not establish C10 behavior.

## Regression and runtime limits

The integrated pinned-Intel regression passed 50 unique pytest cases in 25.20 seconds. The C10 four-test module is included. O0/O2 fixture builds are nested subprocesses, not additional pytest cases. The separate standalone joint Q/N transport O0 test remains a separate PASS record. Commands, logs, compiler pins, and per-test hashes are in `focused_regression_c10.json` and its adjacent command/log files.

C10 OFF and COUPLED 240-second runs are recorded as RUNNING by the root update. The live identity snapshot binds their external run directories, preflight hashes, source receipts, namelist/input hashes, PIDs, and the C10 build/executable. There are no closed C10 receipts here, so this review makes no timestep, final-state, failure, or completion claim. Runtime outcome, paired closure, and scientific approval remain open.
