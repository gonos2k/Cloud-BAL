# T39 closed capture and replay handoff — 2026-10-27

## Closed diagnostic receipt

The preserved HYDRO T39 diagnostic receipt is closed as `INCOMPLETE`, return code 1, with 38 completed steps and timestep 39 observed. No duplicate POST_KDM6 timestep or output processing error is recorded. The receipt binds the diagnostic executable and unchanged candidate build/inputs; its SHA256 is `a71f157b19695cae4cb228cd92b91f05a837fdcd913b1eff3d0d25809697a697`.

The existing postclosure dispatcher says `POSTPROCESS_COMPLETE`, `model_restarted=false`, and return code 0 for both bounded diagnostics. The original receipt, dispatcher, join, prefix comparison, and the three join captures are preserved in [the replay evidence directory](evidence/t39_closed_replay_20261027/). [Its manifest](evidence/t39_closed_replay_20261027/manifest.json) records original paths, sizes, and hashes.

## Group event and fatal consumer

The first T39/RK2 group event is a stage-2 store rejection at `(i,j,k)=(199,52,21)`, pair 4. The known T39/RK2 fatal consumer is at `(2,219,13)`. Pair 4 matches the fatal callback, but the cells differ, so the join reports `DIFFERENT_CELL`; the first group event is not linked to that consumer.

The join separately binds T39/RK1 producer channels 7 and 8 at the fatal consumer cell within its recorded identity bounds. Producer diffusion bits match the consumer's source-rate bits; they do not match its recomputed-diffusion bits. This is a bounded producer/consumer observation, not a full-domain group cause or a T39 baseline comparison.

## First T39 grouped-store replay

The first T39/RK2 grouped event at `(199,52,21)`, pair 4, is an input-local strict-mass store rejection. The preserved replay [receipt](evidence/t39_closed_replay_20261027/group_replay/group_replay.json) records identical results at pinned Intel O0 and O2: the candidate is `3DC0321C9E375C92, 3D226D5A966EC69E`, store failure stage 2, invalid, with `BF800000, BF800000` sentinels. This replays the captured values through the receipt-pinned C2 core; the event was observed in the PR107 diagnostic overlay whose shared core-module hash matches C2. The [reproduction script](../tools/pr107_t39_first_group_replay.py) verifies the source and build receipts against the PR107 executed executable hash and uses only the preserved grouped capture as input. The C2 and PR107 build receipts bind the same `module_em.F` source SHA and identical preprocessed `cloud_bal_joint_transport` module SHA (`a313a76477caea9c028f174208c3e4cfc694744d6729f8542721bf22dc3249c4`); the PR107 executed executable SHA also matches the closed HYDRO T39 receipt.

For pair 4's strict `[100,900]` mass interval, exact rational arithmetic on the captured binary64 source and transport rates gives a combined `q - 900*n` delta of `2167/154742504910672534362390528` (ratio delta `4.487811674217249e-14` above 900). The captured REAL64 candidate has ratio `900.0000000000002`, so the strict check rejects it before rounding. Rounding q and n to REAL32 first would put the pair inside the interval at ratio `899.9999780564222`; that is not the executed storage path. The source and transport-rate fractions and rounded bits are recorded in the replay receipt.

The grouped predicate 1 is then evaluated on the `(-1,-1)` sentinel installed after stage-2 store failure. It is not an independent physical group failure. This is a scalar replay of the captured candidate/store and predicate path, not a replay of the full `2,533,440 x 4` group or forecast. The first-producer stencil values for this grouped cell were not captured; the source and transport rates were. Run the reproduction with `python3 tools/pr107_t39_first_group_replay.py --output /var/tmp/t39-first-group-reproduced.json` from the repository root; it uses the pinned Intel profile and refuses to overwrite an existing output. An initial generic replay command failed because its parser defaults to T32; the [failure record](evidence/t39_closed_replay_20261027/group_replay/preliminary_default_selection.failure.log) preserves that selection mismatch. The dedicated script explicitly selects T39/RK2.

The staged capture file hashes and expanded payload hashes match the closed receipt and join. The existing `postprocess_t39.py` was rerun against only those staged files in fresh scratch. Its output is byte-identical to the stored `t39_join.json` (SHA256 `a5d9feeac67965928923c4c9f269fe34f9f6408d9bd1467b4244c5411f934ed4`); the rerun output is also preserved in the evidence directory.

## Prefix scope and remaining work

The stored prefix comparison is `PASS` for HYDRO only: exact common 0–600 second POST_KDM6 traces (30 steps, 180 state records), ten native history fields over 11 frames, and T1 PRE/POST captures. It establishes output noninterference for that compared prefix. It does not classify or resolve the T39 group failure and is not physical validation.

The bounded native replays below identify two local failure mechanisms without changing model policy. They do not establish a complete correction: the first group's original source and transport producer stencils are absent, and no corrected full-domain transaction or forecast has been run. Physical water/energy/mass–wind validation remains OPEN, and T2 remains NOT_EVALUATED. The existing 640-second results remain valid in their original scope; the 3600-second H/A/N request remains incomplete.

## Fatal callback producer: conversion at the strict boundary

At the separate fatal cell `(2,219,13)`, the captured RK1 west neighbor contains Q=900 minimum binary32 subnormal quanta and B=1 quantum. The other Q/B stencil values are zero. The actual `horizontal_diffusion64` helper and a separately identified REAL128 diagnostic probe are replayed with pinned Intel O0/O2; see [callback replay](evidence/t39_closed_replay_20261027/callback_replay/).

The helper reproduces the captured source bits `3746D5B76A91F326` and `36A9FB2054D81EE3`. The diagnostic REAL128 results satisfy `Q=900*B`; independent conversion of each result to REAL64 yields an exactly positive `Q-900*B` of approximately `1.5557538194652854e-58`. The displayed quotient is about `900.00000000000011`. Exact rational comparison of those REAL64 values, rather than the displayed quotient, proves the strict-bound crossing.

Replaying the recorded RK2 zero stencil returns zero. That is a different input state from the recorded RK1 nonzero stencil, so the zero recomputation does not demonstrate stale or corrupted cache data. The RK1 output matches the RK2 consumed source bits. The immediate conversion problem is localized at this callback cell; it is not evidence that the first group cell had the same original stencil.

## Decision and next experiment

Do not relax the 900 bound, erase the cache, zero all small values, or accept a rounded REAL32 pair while bypassing the continuous-input contract. A producer correction must specify how coupled Q/B arithmetic preserves the admissible pair and account for any source representation change; changing cell increments independently can also affect flux conservation.

The next missing observation is the first-group cell's original source/transport construction at `(199,52,21)`. Capture it alongside the already understood callback cell, retain the actual RK identities and arithmetic, and test a justified correction locally before any matched H/A/N rerun. A new diagnostic request, if needed, must remain separate from the unchanged 3600-second acceptance criterion. No duplicate forecast was launched for this recovery.

The [current-C2 budget preparation](T39_C2_BUDGET_SCOPE_20261027.md) distinguishes current inspected sites from historical PR94 references and retains unmeasured terms as OPEN. IR112 still requires a sensor-matched forward operator and its coefficient/navigation/aggregation bindings.

The original procedures are [the postclosure dispatcher](evidence/pr107_t39_capture_20261026/after_close.py), [the T39 joiner](evidence/pr107_t39_capture_20261026/postprocess_t39.py), and [the prefix comparator](evidence/pr107_t39_capture_20261026/compare_prefix.py).
