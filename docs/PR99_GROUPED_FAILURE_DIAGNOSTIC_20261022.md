# PR99 grouped candidate failure diagnostic

The three frozen C1 runs stopped at the host message `PR87 full joint moment candidate infeasible` after 31 completed 20-second steps. The closed logs establish the aggregate candidate failure but leave its first grouped predicate open. The existing per-cell store callback reports selected coordinates after the group result and cannot identify the earliest failing cell in the complete group.

`tools/pr99_group_failure_trace.py` applies to the receipt-pinned C1 `module_em.F` source (input SHA-256 `f88708844994a30540fc458aeede7e0eda4503a04a341caf714050e52f8c18af`). It adds optional outputs to `joint_qnb_update` for the first failed cell and pair, a distinct grouped predicate code (`1` joint moment validity, `2` stored volume-number contract), the existing `failure_stage`, candidate REAL64 Q/N and stored REAL32 Q/N. The host enables the outputs at model timestep 32 and writes one compact record before invoking the existing diagnostic callback or retry path. The pre-failure row labels the attempt as baseline or source-first. The immediately following fallback result row identifies the same event by run/timestep/RK/cell/pair/predicate and records whether fallback made the group feasible; it inherits the attempt label from the preceding row. `tools/pr99_group_failure_capture.py` validates the exact-bit payload and strictly binds each initial failure to its post-retry status.

The record also includes native cell indices, timestep and RK stage, old/new carrier and dry density, base Q/N, source and transport REAL64 rates, timestep duration, mass bounds, number bounds, all grouped-policy flags, the exact REAL64 inactive-mass cutoff, and group dimensions. Exact IEEE payloads are written as `HEX32` and `HEX64` fields with `TRANSFER`; decimal lines are included for readability. The REAL64 candidate is recomputed with the same theta-one expression and operands used by the initial constrained `form_candidate` call. The host maps the flattened candidate cell using the same `j,k,i` traversal used to assemble the group.

`SOURCE_FIRST` is the host-wide `ANY(source_first_pair)` flag at this grouped attempt. The capture does not record whether the failing pair itself was selected for source-first rates, so the label is context only and cannot establish this pair's candidate formulation. The `PR99_GROUP_POST_RETRY_V1` wire row records feasibility after the inner `try_graupel_mixture_trial()` fallback in the same `evaluate_joint_candidate` call. It does not report the later outer RK3 source-first reevaluation. The parser emits these meanings explicitly and rejects disagreement between `store_succeeded` and `failure_stage == 0`, plus pair-option/bounds mismatches.

The scalar replay checks the exact REAL64 candidate and store outcome against the pinned C1 store at both FREE and REPRO settings, then calls the frozen module's actual grouped moment, strict-mass, and stored-volume predicates and requires the first predicate to match the capture. When `joint_moment_store` fails, `form_candidate` replaces its Q/N candidates with `(-1,-1)` before it evaluates those grouped predicates; the captured `HEX32_STORED` values therefore represent that core-installed sentinel rather than necessarily the store routine's direct outputs. The replay mirrors this replacement and reports both store outputs and grouped-predicate inputs separately. The generated adapter only exposes private predicates and does not edit pinned source equations. The current fixture exercises a failed store followed by grouped predicate 1 on the sentinel. It does not demonstrate a grouped predicate failure after successful storage; under the current implementation, storage and the following predicate use the same stored values and contracts.

This is a diagnostic-only source overlay. It does not change candidate arithmetic, acceptance predicates, thresholds, fallback behavior, rollback, or commit ordering. It does not re-run a stateful store routine. A single integer failure-stage grid is allocated only when the timestep-32 capture is enabled. No type or stencil histogram is recorded; existing runtime callbacks remain the source for their noncausal counts, while this compact event identifies only the first failing candidate.

## Actual OFF event and run status

The actual first captured grouped event is now preserved in the bounded
[evidence package](evidence/pr99_group_failure_20261022/actual_failure/README.md).
The original raw record is 1,530 bytes and is bound by SHA-256 in the package.
It records T32/RK1, flattened cell 556962 at one-based `(i,j,k)=(163,63,22)`,
pair 4, grouped predicate 1, and an ordinary `joint_moment_store` failure at
stage 2. The immediate inner mixture-fallback status is false. The raw event
is now parsed directly from the original Intel list-directed bytes; its
concatenated marker/run-id/attempt fields and wrapped integer header are not
rewritten in the preserved record.

The pinned-C1 scalar replay at FREE/O0 and REPRO/O2 reproduces this event's
REAL64 candidate bits, store failure, installed REAL32 `(-1,-1)` group
sentinel, and grouped predicate 1. This is a local replay of the captured
event, not the cause of the run's later fatal exit.

The full OFF receipt is closed and reports **INCOMPLETE**, return code 1,
after 31 completed 20-second steps (620 of the requested 640 seconds); wall
time was 13,198.311 seconds. The candidate inputs were unchanged. The run
used a PR87 partial native overlay with nine source overrides; only
`module_em` differs from frozen C1 for this failure-only instrumentation.
The original launch-time [launch.json](evidence/pr99_group_failure_20261022/launch.json)
is retained unchanged; the package binds the later closed receipt separately.

The run's separate fatal inner fallback is captured at T32/RK1,
`(i,j,k)=(2,241,14)`, pair QG/QIB. The stdout callback reports local reason
code 6, which the pinned source maps to a bit mismatch between the captured
`qs64/ns64` source and the pointwise `qdiff/ndiff` recomputation in
`add_graupel_diffusion_mixture`. At this sampled cell the logged local
stencil and transport-donor terms are zero while the source values are
nonzero; the captured source-plus-cache bits match `qs64/ns64`. That is a
local source-contract observation. Nonzero source totals alongside a zero
local diffusion stencil do **not** by themselves imply an invalid physical
state or a producer-wide cause. The common-certificate design review remains
pending; no fix is claimed.

The receipt-bound first-600-second comparison passes for the common prefix:
30 completed steps and 180 state records across 12 fields, plus 11 history
timestamps across 10 fields. This comparison does not make the diagnostic
executable identical to C1, establish 640-second completion, or identify a
physical cause. The run is not a 640-second success, and the grouped-failure
cause remains open.
