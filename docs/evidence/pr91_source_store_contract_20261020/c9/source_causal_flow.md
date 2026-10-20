# C9 source-first diffusion evidence

## Scope and status

This directory records the generated C9 source pair, its manifests and build receipt, and a focused pinned-Intel fixture. The C9 transform changes the operator state/order used for source-first cloud pairs: after the physical endpoint is stored, the existing `horizontal_diffusion64` operator is evaluated on the complete prepared Q and N fields under the cached RK1 geometry. Its result replaces the old-state diffusion contribution through one signed delta. No tolerance, precision, core transport algorithm, or graupel change is introduced.

The selected-object Intel overlay build passed; see `native_overlay_build.json` and compile logs. The root reports the separate native 240-second run is **RUNNING**. This evidence makes no native-run completion or outcome claim. The focused test passed (three tests; O0 and O2 compiler executions) using the pinned profile.

## Captured D3 causal chain

At T10, RK3, cloud pair 1, cell `(130,182,2)`, the actual D3 host capture showed both the baseline and source-first attempts failed at failure stage 3 (volume). The source-first attempt had `SOURCE_FIRST_PAIR_FALLBACK` enabled. For graupel pair 5, the capture showed stage 2; the existing G-only probe returned no rejection, so this is not evidence to alter graupel physics.

The D3 trace’s source-first virtual donor, formed before air transport, had Q/N mean `4.188790526204144e-15`, below the minimum `4.18879052734375e-15`; its volume upper-bound residual was `-0.51518464`. The already-stored physical source endpoint `qb/Nb` passed the existing store checks unchanged. This localizes the captured contract mismatch after endpoint storage, when later rates are assembled with the previous-state diffusion term.

The later Q/N payload used by this path is the existing producer’s `moist_tend - coupled_source` residual. Air advection is calculated separately with `air_tendency` and applied after virtual-donor construction; it is not part of this later residual or the source-prepared diffusion delta. C9 retains that ordering and applies the existing air contribution once.

## C9 operator/order equation

Let `R_later` be the existing non-air later residual, `D_old` the producer-captured R64 diffusion rate evaluated on the old state, and `D_prepared` the same existing R64 operator evaluated on the complete stored-source-prepared field. The prior path included `R_later + (D_old - D32_old)` where `D32_old` is the stored R32 contribution. C9 adds `D_prepared - D_old` once, giving `R_later + D_prepared - D32_old`; thus the existing precision correction remains while the diffusion state matches the prepared source endpoint. The source endpoint itself is not locally clipped or repaired.

The diagnostic ledger `SOURCE_DIFFUSION_DELTA_DT_PRESSURE` records signed `dt*(D_prepared-D_old)` sums, L1 sums, and maxima separately for each source-first pair and Q/N channels over the active captured bounds. Units are pressure-coordinate mixing-ratio increments (mixing ratio times the model’s pressure-coordinate timestep); the existing operator rates are mixing ratio per model-time unit. The producer cache identity records timestep, RK step, and six active bounds; the consumer checks the identity and requires both Q/N old-cache channels for each selected pair.

## Reproduction and provenance

Run `python -m unittest -v tests/test_pr91_source_first_diffusion.py` from the Cloud-BAL checkout. The test uses `tests/intel_toolchain.sh`, which pins Intel ifx 2026.0.0 and the runtime libraries. Its standalone operator fixture compiles the separately maintained `tools/pr87_horizontal_diffusion64.f90` kernel and donor expression at O0 and O2 in fresh `/var/tmp` scratch directories; that fixture kernel uses REAL64-internal arithmetic. It is a manufactured operator replacement check, not an exact native-kernel replay. The native C9 generated module (`module_em_c9.F`, SHA-256 `226e64ca5dc30cbaa801bb8d4e736755ec9b0ac0e1227b0992c96f4c61db0e7f`) embeds its `pr87_horizontal_diffusion64` implementation at lines 871–940 and uses REAL128-internal arithmetic. `source_prepared_diffusion_driver.f90` is the executed fixture with the donor expression copied from the production transform.

`c8_original_sources.json` is preserved unchanged. `c8_final_generator_verification.json` records that the later overwrite-guard update to the C8 generator produced byte-identical C8 output and retained the original manifest; it reports no C8 model run. C9 source hashes and the native build receipt are in `sources.json` and `native_overlay_build.json`. Executables and object/archive files are intentionally external and are not copied here.
