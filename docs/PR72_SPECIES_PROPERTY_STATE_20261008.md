# PR72 species state and property admission

This change gives the KDM6 mass/number categories one shared admission rule before PSD and property work. Rain, cloud water, and ice use their mass/number pairs; graupel uses its mass/volume pair.

| Pair state | Classification | KDM6 behavior |
|---|---|---|
| mass = 0 and number/volume = 0 | absent | Valid. Rebuilt intercepts are set to exactly zero. |
| mass > 0 and number/volume > 0 | active | Paired admission only. Existing source formulas and independent PSD/property-domain checks still apply. |
| mass > 0 and number/volume = 0 | mass only | Rejected as unsupported for PSD/property use. |
| mass = 0 and number/volume > 0 | orphan | Rejected before PSD/property work. |
| negative or nonfinite component | invalid | Rejected before PSD/property work. |

No floors, cutoffs, clipping, or graupel density are introduced. The classifier distinguishes exact absence from small positive mass. Nonfinite and negative checks are separate branches so Fortran does not evaluate comparisons against NaN.

The KDM62D entry preflight checks all four current pairs. Before each of the seven `slope_kdm6` calls, one O(N) pass checks current pairs and the actual temporary mass/number arrays passed to that call. The two current-state intercept rebuilds and the late ice-property reconstruction also validate their local scalar pairs; scalar arguments preserve the caller's tile indices and avoid assumed-shape lower-bound remapping. Absent species receive zero intercepts, while active species keep the original intercept equations.

## Validation

`tests/run_pr72_species_property_state.sh` compiled in fresh `/var/tmp` directories with the pinned profile from `tests/intel_toolchain.sh` (IFX 2026.0.0). The final receipt records compiler, source, object, executable, and run-log hashes for 20 full-module executions: ten cases each at O0 and O2.

Both optimization profiles passed whole-module clear state, absent cloud, absent ice, absent rain, active-state comparison, and rejection of mass-only, number-only, negative-mass, and nonfinite-mass input. Returned hydrometeor pairs are checked to be either exact zero pairs or strictly positive pairs. Active `INPUT` rows from the native-fixed and transformed sources matched byte-for-byte at each optimization level.

The final composed source is native-fixed input SHA-256 `f396c9270791addcd4aed9fdc59f5a6d3f9287f1af8f759d3a0cbc36b1e78f85` followed by this transform, producing SHA-256 `1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819`. The exact source diff and run receipt are in `docs/evidence/pr72_species_property_state_20261008.patch` and `docs/evidence/pr72_species_property_state_20261008.json`.

## Scope and open behavior

This is a state-admission and property-safety result, not full physics validation. The strict rule can reject a transient or pending process state when it reaches a PSD/property consumer with only one moment populated; the source contains no explicit pending-transfer status that would authorize treating such a pair as active or absent. Resolving those process-stage states requires a source-supported transfer policy, not a numerical floor.

The earlier EOS-consistent graupel-absent fixture remains a distinct process-feasibility case. The causal receipt `docs/evidence/pr72_causal_eos_graupel_absence_20261008.json` records the PR70/PR71/native-slope-fixed outcomes; the slope-block nesting regression was introduced in PR71, and the native slope repair reaches the existing infeasible-moment rejection. The present matrix does not claim that this separate full-module case completes successfully.
