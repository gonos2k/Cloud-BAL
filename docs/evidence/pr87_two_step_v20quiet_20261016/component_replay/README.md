# V20 quiet rain component replay

This is a source-pinned **offline single-column replay** of the V20quiet failure at timestep 2, cell `(i=109, lat=5)`, KDM6 sedimentation substep 1. It does not complete a model timestep. The replay holds the captured mass and number sedimentation rates fixed; a real Q change before KDM6 would recompute native slope and velocities.

## Evidence

- V20quiet ended `INCOMPLETE`, return code 128, after 1 completed step(s); its fatal was `PR87 rain sedimentation packet rejected`. The archived failure record has 39 contiguous levels and is hash-bound in `receipt.json`.
- Direct helper replay under pinned Intel ifx O0 and O2 returns `valid=F`. Exactly k=19 fails its strict rain cone; the other 38 levels pass.
- The exact V19 offline conversion evidence supplies specific public N `0.17328609526157379` and Q `5.0788977190574514e-11`. `joint_moment_store` returns adjustment code 2 and Q `5.0788980660021465e-11` (REAL32 bits `2e5f5f4e` → `2e5f5f4f`, one ULP upward); specific N remains unchanged. At k=19 the strict upper N bound rises from `0.09953904705024956` to `0.09953905384986361`, taking the captured N from 1.9195e-9 above the bound to 4.8801e-9 below it. Converting that N to the helper's volumetric N with REAL32(N*rho) reproduces the captured k=19 helper input bitwise.
- With that Q-only state change and the original captured rate arrays held fixed, all 39 levels pass the strict cone and the exact frozen sediment helper returns `valid=T` in O0 and O2. This tests helper representability and transfer handling only; it does not reproduce the changed native velocity calculation.

## Q/N packet ledger

The exact helper ledger row is in `selected_markers.txt`; the named fields and raw values are also in `receipt.json`. Proposed and approved Q packets are `1.9106500157332767e-02` and `1.9106499854938220e-02`; proposed and approved N packets are `1.5567707254668348e+05` and `1.5567658770902231e+05`. The helper reports residuals Q `4.7755227609814696e-10` and N `-1.0263818273415382e-02` after its REAL32 state update and ground transfer. These are helper-local packet diagnostics, not a model-wide conservation claim.

The earlier trial at `replay_i109_lat5_t2_n1_joint_store/receipt.json` passed volume N to the specific-N store API. It is retained and marked `EXCLUDED_INVALID_UNITS` in the receipt; none of its outcomes are used here.

## Reproduction pins

`receipt.json` binds the V20quiet run/build/source receipts, exact 40-line failure capture, V19 volume-conversion evidence, frozen KDM6/helper source hashes, joint-store module hash, generated driver, and O0/O2 compiler/compile/stdout hashes. No executable or full model arrays are included.
