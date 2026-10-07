# PR65 retained-observation joint-candidate preflight (2026-10-07)

## Result

The real NE57 input supports a full-radar observation producer-stage trial, but the next phase/Phi/wind candidate is **BLOCKED** at its authority and admission gates. This is a preflight result, not physical approval. It retains all observations supplied by the reader and writes no candidate NetCDF.

The preflight loads the immutable 2026-08-16 12 UTC background, then independently calls the existing `derive_column_physics` observation producer. It does not infer a source increment from a final candidate. It also applies the existing one-column hydrostatic Phi postanalysis to that producer state as a research baseline; no phase exchange or balance/wind solve is run.

## Measured real-input evidence

The actual grid is `235 × 283 × 22`. The reader supplied 70,051 quality-usable radar echo cells. Cloud fraction and cloud type each had zero valid cells; there were zero usable cloud pairs above the configured threshold. No radar LOS set or samples were supplied.

The input had zero `omega_target` cells, zero valid `omega_target_sigma` cells, and zero target/sigma cells sharing observational authority. The full-radar producer completed with `STATUS_OK` and emitted 55,010 diagnostic `omega_target` cells, but still emitted zero sigma cells and zero authorized target/sigma overlap. Those radar-derived targets therefore do not authorize wind changes.

The independent column producer reported 70,051 changed cells, including 63,136 rain, 15,929 snow, and 13,687 graupel value changes. Its aggregate represented species changes were:

| Species | Change (kg) |
| --- | ---: |
| Vapor | 9.9125390601 × 10⁸ |
| Cloud liquid | 1.8380789663 × 10⁷ |
| Cloud ice | 1.0860372951 × 10⁴ |
| Rain | −5.6982007557 × 10¹⁰ |
| Snow | −7.2634396117 × 10¹⁰ |
| Graupel | −6.5844829602 × 10⁹ |

The existing Phi postanalysis assessed all 18 requested layers on the selected column and returned `STATUS_OK`. It changed zero Phi cells there; hydrostatic residual RMS stayed `45.311419733489466 m² s⁻²`. This only records the radar-producer/Phi research baseline. It is not the same final state as a phase-plus-Phi candidate.

## Exact blockers

- `physical_joint_candidate_contract` already provides the per-cell `source_increment` (external analysis A), `boundary_increment`, `phase_increment`, and `physical_tolerance` arrays. The full-observation producer gives a separate stage state and aggregate `pressure_analysis_budget` totals, but this case has no independently admitted per-cell radar-analysis values with an error bound and provenance to declare through `source_increment`. The aggregate totals alone do not provide that admission. Do not reconstruct the declaration from a final endpoint.
- The observational omega-target path tested here has zero valid `omega_target_sigma` cells and zero target/sigma authority overlap. The producer's omega targets are diagnostics. This preflight did not select or declare an alternative model-target/background-prior wind authority, so it makes no wind correction; missing sigma is not a universal prerequisite for every possible joint solution.
- Coverage facts for this input: no `radar_los` samples were supplied, and there were no usable cloud fraction/type pairs. These limit the observation coverage available in this case; they are not universal gates if another independently authorized analysis/background path is selected.
- The candidate inputs do not carry a selected common-air QC/NC policy with donor mass and number states, plus matched donor-face, boundary, limiter, and RK carrier/time terms. Cloud-BAL cannot infer that policy from the precipitation endpoint.
- Source and boundary authority remain undeclared. The preflight did not supply `source_increment` or `boundary_increment`, apply a phase exchange, or evaluate a physical joint contract.

The required gates for this candidate remain the independent per-cell analysis admission, source/boundary authority, and common-air moment policy. A wind adjustment would additionally need a justified, independently authorized wind/background uncertainty path. The PR64 observation-withheld phase/Phi result remains a separate scoped experiment and does not close these gates.

## Reproduction

Run `tests/run_pr65_observation_joint_preflight.sh`. It uses the pinned profile in `tests/intel_toolchain.sh`, compiles in a fresh `/var/tmp` directory, verifies actual input hashes before and after, and freezes source, runner, case TSV, Intel runtime, NetCDF configuration and link archive hashes around the run. The receipt records exact commands and all input identities. Its Intel/NetCDF runtime hashes cover selected compiler, configuration, and library files; this is a partial runtime dependency set, not a complete process loader closure.

The preserved run used ifx `2026.0.0` with the pinned O0 profile in `/var/tmp/cloud_bal_pr65_observation_preflight.SSGJYW`. The executable reported `preflight_status=BLOCKED` and exited zero to indicate that the evidence collection completed; this exit code is not a candidate pass. Full receipt and program output are in [the preflight receipt](evidence/pr65_observation_joint_preflight_20261007.json) and [the preflight log](evidence/pr65_observation_joint_preflight_20261007.log).

## Next admissible work

First obtain an approved per-cell radar-analysis declaration with error bounds and provenance for the existing `source_increment` array, separate from `phase_increment`, plus explicit source/boundary declarations. The selected common-air policy must identify QC and NC donor mass and number states, donor-face contributions, limiter and boundary terms, and the common RK carrier/time. If wind changes are part of the candidate, declare the chosen authority path: the observational target path needs valid source-matched `omega_target`/`omega_target_sigma`, while a model-target path needs its validated coverage authority; a background-prior route also needs its own approved uncertainty declaration. Re-run the complete retained-observation candidate only after the relevant authorities and inputs exist. Keep the O0 research baseline labeled separately from any approved O0/O2 candidate receipts.
