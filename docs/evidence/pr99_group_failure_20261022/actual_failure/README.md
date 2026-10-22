# PR99 actual OFF grouped-failure evidence

This bounded package records the actual first group-failure event, a local
pinned-C1 scalar replay, the separately captured fatal fallback event, and
the OFF run status. It contains only the 1,530-byte first-event raw record and
compact summaries; full native captures, arrays, and logs remain in their
receipt-bound private locations.

The package also carries the parsed event, scalar-replay receipt, fatal-event
analysis, and a bounded fatal-source excerpt so reviewers can inspect the
recorded fields and source mapping without access to private run directories.
The original PR92 capture and full stdout remain private. Their hashes and
paths are bound by the summary, bundled fatal analysis, and closed receipt.

The OFF run is **INCOMPLETE**: return code 1 after 31 completed 20-second
steps (620 seconds) of a requested 640 seconds. The first group event is an
ordinary store failure at `(i,j,k)=(163,63,22)` in T32/RK1. It is not the later
fatal fallback event, which is at `(2,241,14)` and reports local reason code 6.
The two events must not be conflated.

The first event and its FREE/O0 and REPRO/O2 scalar replays agree on the
REAL64 candidate, store failure stage 2, installed REAL32 `(-1,-1)` group
sentinel, and grouped predicate 1. This establishes the local record and
replay only. The closed-run `PR92`/stdout capture separately binds fallback
reason 6 to a source-vs-diffusion-recomputation bit mismatch in
`add_graupel_diffusion_mixture`. The sampled zero local stencil/donor terms
and nonzero source totals do not establish an invalid physical state or a
producer-wide cause; a shared-certificate design review remains pending.

The 0–600 second comparison passes for the first 30 completed stage-trace
steps (180 state records) and 11 history timestamps. It is a prefix check,
not 640-second completion or scientific validation. No 640-second success or
fix is claimed.

`launch.json` at the parent evidence directory is preserved unchanged as the
original launch-time snapshot. Current closed-run status and artifact hashes
are in `actual_failure_summary.json`.
