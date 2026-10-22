# PR99 pressure wind transfer audit

Status: **OPEN**. The fixed-omega pressure producer replay rejects the current candidate before any balance iteration. No PR99 pressure candidate was exported to WPS or validated by WRF.

## Candidate identity and scope

The exact C1 pressure-level COUPLED candidate used by the native preflight is `/var/tmp/pr81_joint_thermo.HbL5ry/O2/joint_candidate.nc`, SHA-256 `135c2315d0953182d248ff650ad50fcab7c0b21075b208e693a04fd7f8487ef1`. It was produced by `tests/run_pr81_joint_thermo_retained.sh` from `/var/tmp/pr78_cp06a_spatial.V9LYrN/O2/coupled.nc`. The PR78 file is an upstream support input, not the final C1 candidate. PR94's current-generation HYDRO control used that upstream file as support and left U/V/omega unchanged (candidate SHA-256 `97a98c5bb05a8dc70528c2b6c025ae8cb359ed46f23b7d3c28941535f71ae9d6`).

The dry-flux comparison below is candidate-minus-background wind correction on the candidate dry carrier and pressure geometry, across 1,294,696 above-ground cells. It does not assess closed mass-wind balance or native WRF's internally diagnosed vertical wind.

| Component | RMS (kg/s) | Max absolute (kg/s) | L1 (kg/s) |
| --- | ---: | ---: | ---: |
| Horizontal U/V | 40.6543 | 9,937.7341 | 449,132.606 |
| Pressure omega | 2.0560 | 594.9383 | 28,791.415 |
| Combined | 41.0190 | 9,983.0764 | 448,333.475 |

Horizontal and omega terms oppose one another: their separate L1 sum exceeds the combined L1 by 29,590.546 kg/s (6.19%). Omega is 6.41% of horizontal L1. The split reconstructs the combined field within `1.82e-12 kg/s`. Thus, U/V-only export omits a measurable, partly cancelling component; this does not assign the full combined residual to omega.

The bounded diagnostic and full statistics are in [pr99_pressure_transfer.py](tools/pr99_pressure_transfer.py) and [c1_pressure_candidate.json](docs/evidence/pr99_pressure_transfer_20261022/c1_pressure_candidate.json). A synthetic decomposition regression passes with the CP06-A state-force tests.

## Fixed-omega policy

`balance_operator_config%fixed_omega_for_export` defaults false. When explicitly enabled, it withholds omega authority from both the general balance operator and background continuity/force operator. The PR81 retained driver accepts `CLOUD_BAL_FIXED_OMEGA_FOR_EXPORT=1` as a scoped opt-in for replay. Default research behavior is unchanged. Existing regression tests cover a compatible nonzero U/V-only correction and an incompatible omega-only residual with exact rollback.

The exact PR81 retained producer-chain replay (pinned Intel O2, same hash-bound inputs) rejected before any balance iteration. Connected control component 9 has support only at pressure level `k=3`; its volume-weighted residual sum is `-401.5942950` against weighted absolute scale `1047.325094` (ratio `0.3834`). The configured component-mean compatibility check therefore fails before CG (`SOLVER_INCOMPATIBLE_RHS`, zero iterations). With omega fixed, the exported U/V degrees of freedom cannot remove this component mean. No pressure correction was applied. The bounded replay receipt is [fixed_omega_pr81_receipt.json](docs/evidence/pr99_pressure_transfer_20261022/fixed_omega_pr81_receipt.json).

## Native U/V projection proposal

The separate native branch projects only the additional COUPLED-minus-HYDRO U/V increment onto the layer-wise nullspace of archived `calc_ww_cp` horizontal dry-flux divergence, using the HYDRO state as the nonzero reference. Controls are only internal U/V faces whose two donor columns lie within the fixed five-cell QC buffer. The observed increment is zero outside those faces; pressure, dry-mass carrier, thermodynamics, QC, W, and all other fields are preserved. This defines the transfer contract around the native consumer without mapping pressure omega directly to W.

The pinned consumer replay used the C1 `calc_ww_cp` object and the projected initial-condition input SHA-256 `10aff32bf15887a43141efbb1b14945234e8bbce741a89904d328fb3b1d75cb3`. The proposal used 196 fixed columns and 364 internal control faces per layer. Across 39 layers, the continuous linear residual L2 fell from `1262.370` to `8.08e-10`; the stored REAL32 proposal retained the archived consumer result to RMS `4.71e-8 Pa/s`, maximum absolute `4.12e-6 Pa/s`, with the top face exactly unchanged. These are initial-condition consumer results, not a native model tendency comparison or momentum validation. The capture lacks the exact T32 U/V/MU/C geometry snapshot, so native runtime tendency validation remains open. Bounded evidence: [projection_delta.json](docs/evidence/pr99_native_consumer_20261022_projection_delta.json), [archived consumer replay](docs/evidence/pr99_native_consumer_20261022_PROJECTION/replay.json).

## Validation boundary

Pinned Intel regression checks passed: `tests/run_contract_regressions.sh` and `tests/run_background_continuity_balance.sh` (checked/O0 and optimized/O2). The focused Python diagnostic/projection suite passed 13 tests. The archived consumer checks the proposal's initial `ww` effect, but no live WPS handoff, native model tendency comparison, forecast, or science authorization is claimed.
