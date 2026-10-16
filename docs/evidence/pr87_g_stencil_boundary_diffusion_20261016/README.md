# Manufactured G diffusion boundary witness

This is an offline numerical possibility witness for independent QG/BG horizontal diffusion evaluations. It is not a diagnosis of a V41 model cell.

The center is empty. Each of its four horizontal neighbors has positive REAL32 state with exact dyadic `QG = 900 * BG`; the saved receipt lists the exact R32 bit patterns. Geometry and diffusion coefficients are positive and exactly one. The exact common linear stencil is the sum of those neighbors and therefore has ratio 900.

The pinned helper was compiled with both `CLOUD_BAL_FREE_FLAGS` (O0) and `CLOUD_BAL_REPRO_FLAGS` (O2) from the copied pinned Intel toolchain script. Both profiles produce identical output: `Qdot/Bdot = 900.0000000000001`; `Qdot` is one binary64 ULP above the exact Q sum. The exact rational sums and helper bits are recorded in `receipt.json`.

Files: `witness.f90` is the driver; `pr87_horizontal_diffusion64.f90` is the exact helper source; `O0.stdout`/`O2.stdout` are run records; `build_manifest.json` records compile profiles; `intel_toolchain.sh` contains the pinned toolchain/profile definition. No executable is archived.
