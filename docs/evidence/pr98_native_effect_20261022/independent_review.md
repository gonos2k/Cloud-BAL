# PR98 native-effect independent peer review

**Status: GO, with no remaining analyzer or publication blockers found.**

Reviewed the regenerated native-effect analyzer, report, capture package, and result after resolving two correctness issues found during review: native support mapping initially missed the history crop origin, and some diagnostic arithmetic initially subtracted/summed R32 arrays before promotion. The final analyzer maps history-mask index `[k,j,i]` to source Fortran mass indices using origin `(i=2,k=1,j=2)`, checks the translated active bounds, and has a pinned composition-anchor test (`target_i0=133,target_j0=15` maps to allocated capture index `(138,0,20)`). Before/after and component arithmetic now promotes R32 snapshots to float64 before subtraction and summation; focused cancellation tests exercise both paths.

Validation:

- `pytest -q tests/test_pr98_native_effect.py tests/test_pr98_native_capture.py`: **14 passed**.
- `py_compile` passed for the analyzer and capture reader; `git diff --check` passed.
- All nine checksums in the public capture evidence manifest verify.
- Independently checked all 36 native `h/b/net` squared-norm identities; all pass within float64 tolerance.
- Regenerated RU assembled and MUDF norms match root's independent raw-array anchors: RU HYDRO/COUPLED L2 `24361.966164037` / `41212.460610699`; MUDF HYDRO/COUPLED L2 `6.893418422` / `147.642661311`. The corrected support remains 613 mass cells and 16 mass columns; union supports are 769 U faces, 767 V faces, and 629 W faces.
- The amended report clarifies that HYDRO disables continuity and force priors together, so C−H measures their combined wind treatment. This matches the PR94 HYDRO control documentation and receipt: `background_continuity_prior=false` and `force_prior_enabled=false`. The report's decision is appropriately scoped: do not scientifically approve the added COUPLED correction based on the measured native indicators; preserve frozen C1 as a diagnostic baseline. It retains `FAIL_OPEN` physical approval and `NOT_EVALUATED` forecast/observation skill.

The source interpretation remains bounded: raw native RU/RV/RW arrays are not acceleration or energy norms; MUDF is the observed combined `DMDT+MU_TEND` output with no separate flux closure; `advance_mu_t` implementation source is inspected but not bound as a compiled override; selected operator pieces are partial, and the vertical-diffusion branch emitted no snapshots under `bl_pbl_physics=11`. The capture is a receipt-bound partial source-mapped Intel overlay, not a clean full-model build. These are documented limits, not blockers for the diagnostic claim.

Final reviewed SHA-256 pins (report wording amendment rechecked; analyzer and evidence are unchanged):

- `tools/pr98_native_effect.py`: `985b40b93f4cf1f7dc0246efa9f837d621a06b52e6d49171f05f92c5c82459d5`
- `docs/PR98_NATIVE_EFFECT_20261022.md`: `23948a478c457f0c5287218fe10af04f38972c391d46bd6844c3e796f1e11279`
- `docs/evidence/pr98_native_effect_20261022/native_effect.json`: `84b6f4e20891cf8d66e705e7d4aa15eafa2bedff016db25b75fdbc2722350f43`
