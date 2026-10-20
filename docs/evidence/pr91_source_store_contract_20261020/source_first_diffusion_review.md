# PR91 C9 source prepared diffusion review

Review date: 2026-10-20. Read-only review of the current C9 transform and emitted Fortran source, plus the corrected C8 scope caveat. No C9 implementation source was changed by this review.

## Reviewed identity and validation

- Transform: `tools/pr91_source_first_diffusion.py`, SHA-256 `610a23955d9f9e9dab5813a41d6cef1652d9b2574b058f4e9b878d89aa61ecc3`.
- Focused tests: `tests/test_pr91_source_first_diffusion.py`, SHA-256 `8ee2d677309f8abe7d10da91c5b5e669e1ed559d916e683bc529416368c0aa64`.
- Current transformed source regenerated from the pinned C8 module and C7 solve: module SHA-256 `226e64ca5dc30cbaa801bb8d4e736755ec9b0ac0e1227b0992c96f4c61db0e7f`; solve SHA-256 `9f1c9f0c9993c1c623aed92988f4e8016c49c8ad14c11e38d41a62bec27b63cf`.
- The live generated pair is also preserved at `/var/tmp/pr91_c9_candidate_20261020_final/` with those same hashes. The earlier `/var/tmp/pr91_c9_candidate_20261020/module_em_c9.F` is stale (hash `f5c6bdba…`) and must not be treated as the final candidate.
- `python3 -m unittest tests/test_pr91_source_first_diffusion.py`: 3 tests passed, including pinned Intel O0/O2 operator checks. `python3 -m unittest tests/test_pr91_source_store_contract.py`: current 4 tests passed. An earlier C9 test run failed because its harness supplied a null actual argument; that harness was corrected before this passing run.

## Source review

The producer cache stores the actual `horizontal_diffusion64` output from the original RK1 field for channels QC, QNC, QI, and QNI. It derives the cache and existing precision correction from the same producer call, scalar field, geometry arguments, and active bounds. The producer records timestep (initialized/reset in `solve_em`), RK stage, and the six active bounds; cache validity is reset at each RK1 step and set only when each channel is captured. Current producer optional-presence checks parenthesize the `.NEQV.` terms.

The consumer first initializes full-field prepared Q/N arrays from the current state, then writes every source-first endpoint across the active update footprint. It calls the `horizontal_diffusion64` interface only after that endpoint pass, using the saved RK1 `muts` snapshot and the same `c1h/c2h`, `xkhh`, map factors, grid spacing, and cached active bounds. The consumer verifies the captured bounds are contained in the prepared-source update footprint. Q/N channel selection is consistent: p1 uses cache channels 1/2 and p2 uses 3/4.

The replacement arithmetic is consistent with the existing residual: `later residual + (Dold64 - Dold_R32)` represents non-diffusion tendency residual plus `Dold64`; adding `Dprepared64 - Dold64` leaves non-diffusion residual plus `Dprepared64`. The correction is added once to `qs64/ns64` before the existing timestep/carrier formula forms virtual donors. The source-prepared diffusion correction is logged separately in `pr85_joint_source_diffusion.raw`, so total source representation deltas must not be described as solely REAL32 storage rounding.

The frozen source confirms scalar advection is held in `advect_tend`, not `scalar_tends`; `pr87_later_*` is formed from `moist_tend/scalar_tend` minus the captured coupled tendency, and does not add `advect_tend`. The later residual includes the R32 horizontal diffusion change, optional QC diabatic tendency, and applicable boundary tendency edits. The old review claim that scalar advection enters this residual was retracted and corrected in the parent review.

## Scope and remaining gates

The producer only captures the old diffusion term when MP=37, RK1, `diff_opt=1`, and `mix2_off=.FALSE.`. The C9 source-first path fails closed if a required cache channel is absent. This is valid for the intended C7 configuration only if those settings are part of the run contract; configurations with disabled or different horizontal diffusion are not supported by this transform as written.

The replacement applies only over the captured native diffusion support. In the reviewed specified-domain path, source endpoint values are prepared across the consumer interior and the unchanged boundary donor ring remains the existing boundary state. The result is not evidence that diffusion was recomputed over a full domain including boundary cells. No global conservation claim is made by this review; the standalone tests verify the synthetic operator replacement and its closed-support sum only.

The focused standalone test compiles the separately maintained `tools/pr87_horizontal_diffusion64.f90` kernel and donor arithmetic, not the native candidate kernel or the entire transformed host source. This fixture uses REAL64-internal operator arithmetic. The C9 generated module (`/var/tmp/pr91_c9_candidate_20261020_final/module_em_c9.F`, SHA-256 `226e64ca5dc30cbaa801bb8d4e736755ec9b0ac0e1227b0992c96f4c61db0e7f`) embeds the native `pr87_horizontal_diffusion64` implementation at lines 871–940 with REAL128-internal arithmetic. The fixture checks the manufactured operator replacement expression and closed-support sum, but is not an exact native-kernel replay and supports no bitwise/native arithmetic claim. Root-owned pinned Intel native compilation remains the gate for fixed-form integration. No model run, physics validation, or runtime conservation conclusion is established here.

## C8 caveat correction

The adjacent C8 review now distinguishes interior from boundary-ring checks. Interior post-endpoint `source_sum64` receives `prepared_donor_is_safe` only; it does not receive `joint_moment_is_valid64` or the pair-1 volume bounds there. The unchanged boundary donor ring separately calls `joint_moment_is_valid64`. The C8 test count is recorded historically as 3 at the original review and 4 at the current rerun.
