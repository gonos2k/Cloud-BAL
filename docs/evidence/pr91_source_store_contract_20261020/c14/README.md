# C14 evidence bundle

C14 is an explicit physics-path change. The common joint store can, when explicitly enabled, represent a tiny positive inactive Q as the binary32 quantum `2^-149`, while retaining the already-rounded N and checking the existing inactive mass/volume constraints. The default policy remains rejection. Final-store Q-quantum adjustments use the explicit `INACTIVE_Q_QUANTUM_ADJUSTMENTS` per-pair ledger (four pair slots); signed storage deltas remain in the existing store ledger. Source preparation’s existing `SOURCE_REPRESENTATION` aggregate is kept separate and is not used to account for this final-store adjustment.

The generated host source embeds the instrumented C14 core. `dedup_byte_comparison.json` records that regenerating `module_em.F` from the archived C12 input and C14 core is byte-identical to the source used by the native overlay build. The C14 transformation reuses `pr91_host_store_trace.py`; `original_c7_core.f90` preserves the historical raw C7 core pin used by D3 trace tests.

## Validation

`build_receipt.json` records a pinned ifx 2026.0.0 partial native overlay build with status `PASS_OVERLAY_BUILD`. This is not a clean build and the receipt records `model_run=false`. `build_binding.json` names the rebuilt host/core consumers and compiler profile. The focused command in `manifest.json` passed five tests; its core test compiles and runs with the project Intel profile at O0 and O2.

The scoped FP expression probe is in `fp_probe.f90` and its O0/O2 outputs. It observed gradual underflow and matching conversion results for the tested minimum-subnormal expressions. This does not establish a general compiler/runtime property beyond the tested profile and expressions.

The paired 240-second OFF and COUPLED native runs were running when this bundle was written. No native runtime success or final validation claim is made here.
