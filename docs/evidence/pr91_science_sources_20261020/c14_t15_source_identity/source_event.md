# C14 T15 graupel source identity event

This bounded record classifies the T15 RK1 pair-4 failure at `(i=2,j=218,k=13)` in both 600-second C14 arms. Both receipts are `INCOMPLETE`, return code 1, and report 14 completed steps. The arm-specific receipt, executable, RSL, and event-line hashes are recorded in [source_event.json](source_event.json); the RSL gzip hashes match each receipt's generated-file entry. This event is separate from the accepted 240-second C14 runs.

## Guard reached

The `PR87_GRAUPEL_SOURCE_IDENTITY_FAIL` record shows source payload bits `qs64=37DF4A1044E19719` and `ns64=3741E86FF089F302`, while the recomputed Q and N diffusion increments are both `+0` (`0000000000000000`). In `module_em.F`, `add_graupel_diffusion_mixture` calls `graupel_diffusion_point` for Q and N and returns immediately if either point call is invalid (lines 5088–5091). The identity comparison and writer follow those checks (5093–5098). Thus these zero increments were computed by valid point calls, not left as the routine's initialized defaults.

The subsequent `PR91_GRAUPEL_TRIAL_REJECT_CONTEXT` code 6 maps to `certify_graupel_storage`'s local `reject_reason=6`: the diffusion-mixture fallback returned invalid at the identity comparison (4945–4952). It is not `joint_moment_store`'s `failure_stage=6`. The following `store_graupel_mixture` path, which would assign local reason 4, is not reached (4954–4962).

## Limits

This localizes the failing guard but not its upstream cause. The event rows do not contain the Q/N center-plus-four-neighbor state stencils, diffusion metrics and coefficients, carrier values, or the construction components for `qs64/ns64`; they also do not identify the subpredicate that rejected the initial `joint_moment_store` candidate. The printed `qs64/ns64` are source-rate payload operands in the trial record. Although the routine uses generic Q/N names, its caller maps pair 4 to the QG mass and QIB bulk-volume channels; `ns64` here is not a particle-number concentration. The payload units and full provenance are not established here, so these values must not be treated as QG/QIB state values or compared as a bulk-state ratio.

No PSD, storage-quantum, FTZ, or source-preparation-rounding cause is established. The exact additional inputs needed for a replay are listed in the JSON. The full state audit remains with the host diagnostics owner; this note does not claim one.
