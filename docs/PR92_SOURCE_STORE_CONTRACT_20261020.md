# PR92 — Source replay and bulk-volume storage

## Current scope

Base: PR91 main `71b8c1d5dae181c163d04eabac9cf8f80134f417`.

C14 remains the preserved research baseline: paired 240-second requests completed, and the paired 600-second requests completed 14 timesteps before the T15/RK1 failure. Their original receipts remain unchanged.

Current candidate: **C18**, executable SHA-256 `32a324d49366487f68ec1e6e687a465ef2533bd9163e2fe09733e83cc2272c16`. Both 600-second requests closed **INCOMPLETE**, return code **128**, after **23 completed timesteps / 460 seconds**. T15 and T22 completed; T24 reached KDM6 and stopped with `PR85 invalid cloud-ice freezing packet base`. There are no collector errors. Whole-WRF clean-build validation and scientific approval remain separate gates.

| Preserved identity | Completed prefix of its 600s request | Next boundary |
|---|---:|---|
| C14 | 280s / 14 steps | T15 RK1 source/store |
| C15 | 280s / 14 steps | T15 RK2 bulk-volume representation |
| C16 | 280s / 14 steps | T15 RK3 retry-selection probe |
| C17 | 420s / 21 steps | T22 RK3 positive subnormal Q/B storage |
| C18 | 460s / 23 steps | T24 cloud–ice freezing base |

C14's separate paired 240-second successes remain preserved. Original receipts and failed trials are not rewritten as later successes.

## 1. The diagnostic build preserves C14's actual state

D1 adds producer and failed-store bit records to the retained C14 source. Both diagnostic requests stopped at the same T15 boundary as C14, with return code 1, 14 completed timesteps, and no receipt-processing errors. Each arm's entire `pr85_joint_moment_stages.raw` payload is byte-identical to its original C14 600-second payload:

| Arm | Raw bytes | SHA-256 |
|---|---:|---|
| OFF | 11,920,009,040 | `515edbccd7e9d29a07132b4b037d81b514a1ab69cbc115bc20d182b91d7e5ae7` |
| COUPLED | 11,920,009,040 | `cbb8537153a8102837315cfe924800df6aac5b79f99c4068b78f47041c26a511` |

D1 was launched with the unmodified PR91 runner, preserved as `d1_launch_runner.py`. The later C15 runner extension was not loaded by these already-running Python processes.

## 2. Source identity and candidate storage are different checks

The captured source uses the original evaluation order:

```
source64 = FINAL32 + ((BEFORE_D32 + producer_D64) - AFTER_D32)
```

Every REAL32 operand is promoted before the indicated REAL64 operations. Reassociating this expression changes its rounding behavior.

For the first T15 identity failure, both QG and QIB producer replay, geometry, coefficients, cache correction, and assembled source match their captured bits at Intel O0 and O2. The consumer's later Q1/QIB stencil differs from the producer's stencil. The fallback correctly computes diffusion of that later stencil; this is not the same diffusion source. All captured state-stencil differences are at the west donor `i=1`: QG/QIB at `j=218,219`, level 13. The center and other donors agree. The selected solve performs boundary handling between production and the later RK1 Q1/N1 copy. This static call order does not alone establish the exact boundary write or a physical boundary error. Its exact identity guard is retained. We neither delete other source terms nor replace bit comparisons with a tolerance.

All 17 FULL stage-2 Q/B payloads are pure producer diffusion at their own coordinates. This does not prove that the later-stencil mixture fallback accepts them. Their actual seven donor weights and fourteen REAL32 donor components are recorded at T15/RK1 in C15, after the unchanged mixture helper accepts a local trial. The witness is restricted to the twelve diagnostic support coordinates. A local trial must also match a later committed stage before it is described as committed.

See [the captured source/store replay](evidence/pr92_source_store_20261020/graupel_store/replay_findings.md). Its original combined status remains `LEGACY_REPLAY_PENDING`. The additive [actual C15 witness replay](evidence/pr92_source_store_20261020/graupel_store/c15_witness/summary.md) now reproduces all 17 local trials exactly at Intel O0/O2, including their D1 candidate bits and cells. All stored pairs pass the strict density predicate. A separate [closed-runtime audit](evidence/pr92_source_store_20261020/c15/closed_runtime_20261020/closed_runtime_summary.json) confirms that all 17 stored trial pairs exactly match the committed T15/RK1 endpoint. The additional tiny-volume target is zero/zero in both arms. This does not turn the later C15/RK2 failure into success.

## 3. A separate bulk-volume representation gap

The captured continuous candidate is:

| Channel | REAL64 bits | Value |
|---|---|---:|
| QG, kg/kg dry | `370528AC448AD089` | 1.1859961634011352e-43 |
| QIB, m³/kg dry | `3668384CB70114F1` | 1.3257553714467398e-46 |

Its density is approximately 894.58145 kg/m³. Nearest REAL32 storage is Q=`00000055`, B=`00000000`. For a positive stored B, `B >= eta_B = 2^-149 m³/kg dry`. With the declared lower density, a positive coherent pair therefore requires `Q >= 100 eta_B`; the captured Q32 is below that threshold.

The current opt-in `allow_bulk_volume_quantum_storage` includes a joint-absence branch for the following declared volume-underflow region. Preserved C15–C17 sources used its earlier `allow_bulk_volume_quantum_absence` name:

- finite, positive continuous Q/B satisfying the strict [100,900] density cone;
- B below half its REAL32 quantum and rounded B equal to zero;
- continuous Q below `rho_max * eta_B / 2`;
- strict mass checking, subnormal storage, and joint-absence permission enabled;
- no number/volume contract or positive inactive-mass exception on this bulk-volume channel.

It stores **both Q and B as zero**, with distinct adjustment code 5. The intensive per-event losses are bounded by `|delta B| < eta_B/2` and `|delta Q| < rho_max*eta_B/2`. Extensive bounds use the same positive carrier as the signed ledger. These per-event bounds do not bound cumulative or endpoint loss.

The policy retains B's nearest zero representation instead of raising B beyond its half-quantum budget. With B32=0, the strict density cone requires Q32=0 as well. This is a declared joint accuracy policy; it does not minimize an unspecified Q/B error norm or establish physical disappearance.

C15 initially used the narrower `Q < rho_min*eta_B` region. Its T15/RK2 candidate has Q=`370FBB34F9B63B31`, B=`367229317228D12C`, density approximately 894.58145, nearest Q32=`0000007F`, and B32=0. Exact common-store replay locates rejection at stage 6. A positive pair `(127 eta_B, eta_B)` also satisfies the density cone: C16's zero-pair selection is therefore an explicit lossy numerical choice, rather than a claim that no positive representation exists. It spends approximately 28.21% of the declared Q budget and 28.38% of the B budget for this candidate.

The tests include both exact RK1/RK2 candidates, the feasible positive alternative, half-quantum ties, near-budget states, density violations, orphans, nonfinite values, incompatible options, default-off behavior, live cloud/rain bounds, inactive-ice adjustment 4, separate ledgers, and atomic rollback.

This is an explicit numerical removal, not melting, sublimation, precipitation, or physical absence. It leaves T and vapor unchanged. It does not accept stage-2 density failures. Some other representability gaps remain outside this conservative policy.

For each committed event:

```
delta_Q = carrier_new * (stored_Q - candidate_Q)
delta_B = carrier_new * (stored_B - candidate_B)
```

The separate `BULK_VOLUME_ABSENCE` row reports only code-5 counts and signed Q/B deltas. Ordinary rounding repairs remain in the existing total storage ledger. The two deltas have different units and must not be added together. These coupled-carrier sums still require the same layer/map-area geometry to become physical inventories. Sums across RK events are not the final endpoint's water loss.

The host enables this policy only for pair 4 and publishes its count/deltas only when the complete transaction succeeds. Failed trials preserve the original stage arrays and zero counters/ledgers.

## 4. The retry-selection probe must share the committed policy

C16's T15/RK3 trial stopped on cloud pair 1 at `(204,10,2)`. The subsequent graupel-only probe printed local reason 6 for the tiny-volume cell, but this is not a new violation of the declared absence budget. Its Q=`371FB7DAF11AF1E8`, B=`368227465D101BF5` is accepted by the current common store with the policy enabled, at Intel O0/O2; default-off rejects it at stage 6. The candidate spends approximately 253.745 Q quanta and 0.283647 B quanta, below the 450/0.5 intensive limits.

The probe omitted `allow_bulk_absence` and its required outputs. This kept `failed_pairs(4)` true and prevented the existing whole-support cloud source-first retry. Although the probe does not commit state, its result controls retry selection.

C17 passes the existing opt-in and **probe-local** count/delta outputs to the same certifier. The certifier resets these outputs. Probe values are never added to the committed ledger; only a successful subsequent candidate owns committed changes. Core thresholds, precision and physical coefficients are unchanged. A focused source-form contract regression checks both trial/probe forwarding and the local-only output ownership.

## 5. Positive subnormal storage must use the same error budget

C17 completes T15 and its subsequent calls through T21. Its T22/RK3 cloud trial first rejects pair 1 at `(204,10,2)`, followed by a graupel-only probe at `(2,252,14)`. The probe's local reason 6 is not the common store's stage enum.

The independently replayed Q/B bits are `374237F3DE250AFA` / `36A6E0DE5EEF31AA`: approximately 1165.988152 Q quanta and 1.429900 B quanta, density 815.433599 kg/m³. The current C17 common store rejects at stage 6, with or without its absence option. Its nearest REAL32 pair is Q=`0000048E`, B=`00000001`, density 1166; B is positive, so the absence branch does not apply.

A strict-valid positive pair exists at Q=`00000384` (900 quanta), B=`00000001`. Its errors are approximately −265.988152 Q quanta and −0.429900 B quanta, strictly inside the same 450/0.5 event budgets. This is a representation gap in C17's one-neighbor subnormal repair, not absence of a valid positive pair.

C18 allows the **existing directed-Q helper** to consider subnormal Q only under the explicit bulk-volume opt-in, after the unchanged strict continuous gate and with positive rounded B. Both signed representation errors must pass the same existing intensive budget. The resulting pair must pass the strict stored cone. The projection uses adjustment 2 and the ordinary signed Q/B storage ledger; it does not increment code-5 joint-absence counts. Default-off behavior, the normal-Q path, source identity guards, T/vapor, and the per-event budgets are unchanged. No NR/BG floor or new physical source is introduced.

The [exact C17 replay](evidence/pr92_source_store_20261020/local_validation/c17_t22_probe/result.json) and [current Intel fixture](evidence/pr92_source_store_20261020/local_validation/c18_policy_final/validation.json) retain the rejected nearest pair, valid positive alternative, default-off rejection, and mixed-ledger/rollback checks. The actual closed C18 [OFF endpoint](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/off_t22_p4_endpoint.json) and [COUPLED endpoint](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/coupled_t22_p4_endpoint.json) confirm QG=`00000384`, QIB=`00000001` at both T22/RK3 and PRE_KDM6 at `(2,252,14)`. T22 completes; POST_KDM6 is zero/zero and is kept distinct from the consumed input. This verifies the stored positive pair and subsequent call, not unchanged state through microphysics.

## 6. Validation and experiment gates

- Current common core and its original transport suite: pinned Intel O0/O2, fresh scratch working directories, PASS.
- New representation, mixed-option, separate-ledger, and rollback fixture: pinned Intel O0/O2, PASS.
- Captured producer/source/stage-6 chain: both arms, O0/O2 identical; four stage-6 records become strict-valid zero pairs, seventeen FULL stage-2 records remain rejected by the new policy.
- Existing default-off store regressions: 14 PASS. Historical C14 generation/compiled-core checks: 5 PASS, with its original core hash preserved.
- Canonical `tests/run_unit_tests.sh`: the preserved C16 snapshot exited 0 with all 6,372 file hashes unchanged. The new [C18 base-plus-current-core snapshot](evidence/pr92_source_store_20261020/local_validation/c18_canonical_validation.json) also exited 0, with all 6,372 frozen file hashes unchanged. The entry includes the policy fixture at both Intel profiles. New PR92 Python tools are outside those snapshots and have a separate 40-PASS focused suite.
- C15 requested 600 seconds once per arm and closed at T15/RK2; its 280-second completed prefix is preserved. C17 requested 600 seconds once per arm using a new executable identity with the same input/boundary/FP configuration and closed at 420 seconds. C18 retained that requested window, completed 300/320 seconds and closed at T24 KDM6 after 460 seconds. The required 600-second snapshot is absent; the complete request is INCOMPLETE. The [closed OFF audit](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/off_closed_runtime_summary.json) and [COUPLED audit](evidence/pr92_source_store_20261020/c18/closed_runtime_20261020/coupled_closed_runtime_summary.json) each bind 138 completed states through T23 to the C18 build and receipts. The separate declared source-cutoff/8-ULP ice policy has zero active outliers and zero failures under that policy. The independent generic exact-source audit remains FAIL: rain has 619 exact-bound cell-state outliers in OFF and 617 in COUPLED, none beyond 8 ULP. These are not relabeled as exact passes. T24 partial states are excluded from that completed-state acceptance claim.
- The disk guard is calibrated only from a successful, same-input 240-second receipt. It verifies archive and decompressed hashes, cadence and source identities, uses a 3x inventory estimate plus per-step slack, retains the 0.85 free-space guard, and checks both requests together before launch.

The runner source hash is captured at process entry and written before launch. Preserved C15 source, build, preflight and launch pins are in [the C15 evidence](evidence/pr92_source_store_20261020/c15/). Preserved C16 source/build and closed results are in [the C16 evidence](evidence/pr92_source_store_20261020/c16/). Preserved C17 source/build, closed receipts and the paired preflight are in [the C17 evidence](evidence/pr92_source_store_20261020/c17/).

## 7. Science continues on source-bound preserved results

[The science report](PR92_SCIENCE_RESPONSE_20261020.md) contains same-location pressure/Phi/W response maps and fixed-location tracks. Extrema at different positions are not treated as a single trajectory. The [C16 closed audit](evidence/pr92_source_store_20261020/c16/closed_runtime_20261020/closed_runtime_summary.json) preserves the generic exact-source ice failures and separately finds zero active outliers under the declared inactive policy. Its whole history files are byte-identical to the same-arm C14 files through T240, so those existing field diagnostics apply over that verified scope only. T260/T280, partial T15, and C17 require their own evidence. C16 also has its own area-weighted grouped activity summary through completed step 14; historical C14 ratios are not relabeled as C16 results.

The closed C18 report adds its own area-weighted grouped activity through T23: AUT deferral is about 69.00% and G about 71.42% in OFF (69.00% and 71.41% in COUPLED). These half-L1 activity ratios are not precipitation suppression rates. Same-arm C18/C17 history files are byte-identical through 420 seconds, and the first fourteen complete stage-trace timesteps match in all 113 records per arm; the report links the corresponding hashes. No history endpoint at 460 or 600 seconds is inferred from those files.

The actual PR83 `real` QC vertical source-form replay now reproduces 624 initialized QCLOUD values bit-for-bit at Intel O0/O2. This validates the selected vertical input/output path. Attribution from the original Cloud-BAL pressure support through the actual operational horizontal product remains incomplete; the earlier 288-value horizontal component replay used a different product. The additive provenance correction preserves the original PR91 artifacts.

Current AUT/G group activity ratios remain descriptive half-L1 diagnostics. The available first-full-proposal predicate does not identify the binding constraint at the selected approval fraction. The source audit records this limit explicitly.

Water/energy closure, native continuity/force balance, independent observation agreement, and reduced initialization shock remain OPEN. Successful time integration alone does not approve these claims.

Historical source paths in original receipts are resolved by [the additive source archive index](evidence/pr92_source_store_20261020/historical_source_aliases.json). All archived C15/C16/C17 generators reproduce their original compiled module bytes; the original receipts remain unchanged.

## 8. Remaining T24 boundary

Both C18 arms stop in the PINU cloud–ice freezing packet-base check, after committing T24's three RK stages and entering KDM6. This is a different reported boundary from T15/T22 host storage. The selected KDM6 source is unchanged, but that alone does **not** establish causal independence from earlier numerical changes. Its relationship to prior Q/B adjustments remains unresolved.

The [exact T24 replay](evidence/pr92_source_store_20261020/local_validation/c18_t24_freezing_base/README.md) reproduces both arms' identical final PINU row at `(i,call_j,k)=(230,247,20)`. QI=`3623A538`, internal NI=`441BBBE7`, and dry density=`3F0938B8`. QI exceeds the inactive cutoff; the active-ice mean mass is `2.0982771175135736e-9` kg against a maximum `2.0982747187893314e-9` kg. It exceeds the bound by approximately 10.8 REAL32 ULP, outside the helper's existing 8-ULP allowance. The cloud condition passes. The captured unchanged helper returns `base_valid=F, accepted=F` at pinned Intel O0/O2, matching the actual rejection.

The ledger retains the failed base, proposal and zero approved packet. This closes the immediate failing predicate, not its upstream producer. The next bounded task is to locate the first state transformation between the last valid ice reconstruction and the freezing input. Do not enlarge the tolerance or modify number concentration from a rounded diagnostic. No cloud–ice freezing physics is changed in this PR.

## Navigation maintenance

The compact [Graphify/KG publication bundle](evidence/pr92_source_store_20261020/kg/README.md) binds the final reviewed source commit, separate KLAPS50/Cloud-BAL snapshots, deltas, protected-content checks, and the exact runtime/validation status. It contains no full graph or private host-profile contents. Generated Fortran inside Python strings is source-hash-bound; Fortran cross-file call extraction is partial. Structural freshness provides no additional runtime or scientific approval.
