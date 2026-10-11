# PR76 gradual-underflow policy comparison

## Result

The paired O0 partialhost runs used the same 100 staged inputs and reproduced
the PR74 first-call pretrace and driver capture hashes in both cases. The
incoming O0 archive was copied into fresh scratch builds and remained
unchanged. Both runs retained the inherited `-ftz` link option and the pinned
Intel profile, including `-convert big_endian` and the original KDM6 compile
options.

| Run | At `(i, call_lat, k) = (211, 2, 15)` | First rejection and outcome |
| --- | --- | --- |
| Baseline | NI `0x0093B134` × dry density `0x3F449EE9`; MXCSR `0x9FFD` before and after; FTZ and DAZ set; converted NI `0x00000000`, invalid | `KDM6 invalid NI number basis input` (exit 128) |
| KDM6 entry policy | Same NI and density bits; entry MXCSR `0x9FFD` → `0x1FBD`; conversion MXCSR `0x1FBD` → `0x1FBF`; FTZ and DAZ clear; converted NI `0x00716F5A` (`1.041735647987705e-38`), valid | Later rejection: `KDM6 orphan number/volume state without positive mass` (exit 128) |

The treatment returns a nonzero subnormal result for the exact NI conversion
that failed in the baseline. Its MXCSR change at KDM6 entry is exactly mask
`0x8040` (FTZ bit 15 and DAZ bit 6). The helper check also exercised sticky
flags and a nondefault rounding mode, then verified that every bit outside
that mask was preserved. The conversion after-state `0x1FBF` differs by
`0x02`, the denormal-operand status bit. Underflow status was already set in
the before-state `0x1FBD`; no status-bit change is attributed to an individual
instruction.

This is a scoped causal runtime-policy comparison for that conversion. The
baseline only observes FP state; the treatment changes FP state at KDM6 entry.
The policy is applied
at KDM6 routine entry on the calling physics thread, remains in effect on that
thread after KDM6 returns, and does not establish state at host-main startup or
on threads that do not enter KDM6. The first later rejection has no captured
coordinate claim. Neither run completed a model timestep: each produced only
the initialization output `wrfout_d01_2026-08-16_12:00:00`. Both lack the
PR74 post-call outputs `kdm6_first_call_post.raw`, `pr67_kdm6_process.raw`,
`pr69_water.raw`, and `wrfout_d01_2026-08-16_12:00:20`. No physical pass is
claimed.

No scheme floor, QC cap, or model input was changed. The intervention modified
only FTZ and DAZ at the KDM6 entry, while preserving rounding, exception masks,
and sticky status at that point.

## Evidence

The hash-bound receipt is
[`pr76_native_fp_policy_20261008.json`](evidence/pr76_native_fp_policy_20261008.json).
It records the pinned Intel compiler identities and argv, archive and protected
source hashes, both staged-input hash sets, the same-call bit records, entry
and conversion MXCSR/thread captures, failure lines and sources, available
outputs, missing outputs, helper-control verification, and the prior attempts.
It also binds preserved compiler, link, run, and RSL error logs plus unified
source deltas for each scratch build.

Raw records are preserved in:

- `pr76_native_fp_baseline_ftz_daz_target_call.raw`
- `pr76_native_fp_baseline_ftz_daz_adapter.raw`
- `pr76_native_fp_baseline_ftz_daz_stdout.raw`
- `pr76_native_fp_baseline_ftz_daz_rsl.error`
- `pr76_native_fp_baseline_ftz_daz_source.diff`
- `pr76_native_fp_baseline_ftz_daz_compiler.raw`
- `pr76_native_fp_baseline_ftz_daz_linker.raw`
- `pr76_native_fp_kdm6_entry_gradual_entry.raw`
- `pr76_native_fp_kdm6_entry_gradual_target_call.raw`
- `pr76_native_fp_kdm6_entry_gradual_stdout.raw`
- `pr76_native_fp_kdm6_entry_gradual_rsl.error`
- `pr76_native_fp_kdm6_entry_gradual_source.diff`
- `pr76_native_fp_kdm6_entry_gradual_compiler.raw`
- `pr76_native_fp_kdm6_entry_gradual_linker.raw`

The first paired attempt, which already showed the later state rejection but did
not yet record successful target-call result bits, remains preserved as
[`pr76_native_fp_policy_first_attempt_20261008.json`](evidence/pr76_native_fp_policy_first_attempt_20261008.json)
with its raw traces, compiler and link logs, run logs, and RSL errors. The PR75 first direct capture attempt and its
classification also remain untouched.

The transform and helper checks and the paired runs are reproducible with
`tests/run_pr76_native_fp_policy.sh`. It sources
`tests/intel_toolchain.sh`, builds in fresh `/var/tmp` scratch directories,
and does not modify maintained model source or the incoming archive.
