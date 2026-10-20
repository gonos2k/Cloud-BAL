# C11d OFF T2/RK3 first-failure replay

The closed 40-second C11d OFF diagnostic run completed T20, entered T2/RK3, then stopped at the virtual-donor guard. Its receipt-bound failure capture identifies pair 1 at `(i,j,k)=(233,62,1)`. The capture is preserved as `../pr85_joint_source_failure_c11d_off.raw.gz`; `../c11d_off_receipt.json` binds the raw and compressed payload hashes.

`kernel_c10_embedded.f90` is the `pr87_horizontal_diffusion64` module extracted from pinned C10 `module_em.F` (SHA-256 `af54a8bd951e47407f6900dbfd4b16396cd6fc30753bb32437fd46c45b86be4c`). It is the native embedded REAL128-internal helper, not the separate maintained REAL64 fixture. `driver.f90` loads the captured REAL32 stencil and geometry words by bit pattern, calls the helper for the captured cell, and applies the C10 REAL64 source update in the same order. It was compiled and run with `tests/intel_toolchain.sh` and the pinned Intel reproducible flags.

Replay outputs exactly match the captured helper and source results:

- Prepared diffusion Q/N: `3B39C82BC6F72E40` / `3DEEDC08DA77C3AC`.
- Later source plus cached diffusion delta: `3EAA8DB6FDF0014D` / `41255E05FAD1937D`, exactly the captured old diffusion Q/N.
- After adding `Dprepared - Dold` in REAL64: source sums Q/N are `0000000000000000` / `3DF0000000000000`.
- Virtual donor Q/N: `0000000000000000` / `3D2B7A7AA1B95EA2`, or Q=`0`, N=`4.881150365991468e-14`.

The Q cancellation leaves positive N, so this is an orphaned pair at the captured endpoint, not a negative value or underflow. This identifies the arithmetic failure at that cell; it does not establish a model-level repair or validate a proposed next transform.

C11d's full compressed `pr85_joint_moment_stages.raw.gz` and C10 OFF 240-second artifact are byte-identical (SHA-256 `a54e4f4fa315dd2c25509f48d892af12389f20b05cec6df5dd01077348d8429c`; 1,350,197,000 uncompressed bytes, 485,643,877 compressed bytes). The C11d run has one completed T20 state, then the T2/RK3 failure; this comparison is diagnostic-only and does not claim run success. C11d was OFF-only; no COUPLED C11d coordinates are implied.
