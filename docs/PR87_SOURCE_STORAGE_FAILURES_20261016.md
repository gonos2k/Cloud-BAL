# PR87 source and full-candidate storage diagnostics

The read-only classifier is [tools/pr87_source_storage_failures.py](../tools/pr87_source_storage_failures.py). Its hash-bound evidence is [pr87_source_storage_failures_20261016.json](evidence/pr87_source_storage_failures_20261016.json). It keeps the earlier v2 source-only diagnostics separate from the later v3 full-candidate rejection.

## Historical v2 source-only stage

The corrected v2 40-second OFF and COUPLED attempts each recorded 582 source-only failures. Their `SOURCE` records contain the source-only formula, with transport excluded. All 582 continuous candidates were finite, nonnegative, within REAL32 range, inside exact pair bounds, and valid under the source-only `joint_moment_is_valid` check, including the `N * dry_density` storage check.

| v2 source-only classification | Count | Pair split |
| --- | ---: | --- |
| Continuous Q rounds to REAL32 zero while stored N remains positive | 577 | QC/QNC 446; QI/QNI 131 |
| Positive stored pair falls below the minimum mass ratio | 4 | QC/QNC 1; QI/QNI 3 |
| Positive stored pair exceeds the maximum mass ratio | 1 | QI/QNI 1 |

For the 577 pair-loss rows, continuous Q ranges from `9.83367319940532e-50` to `6.993365609641656e-46`. Continuous N ranges from `1.00089967152931e-39` to `6.217336272231188e-34`. The first row is RK 1, QC/QNC, `(i,j,k)=(216,2,16)`: continuous `(Q,N)=(8.106718411126022e-47, 6.844783533007300e-35)`, stored `(Q,N)=(0, 6.8447836e-35)`.

These v2 rows do not identify the offending operands in the full source-plus-transport candidate. The full candidate was also rejected in those attempts, but the full operands were not logged there. Do not infer from v2 that its 582 source-only rows caused a full-candidate failure.

## Latest v3 full-candidate stage

The later v3 OFF and COUPLED attempts used the same selected-object partial overlay and each completed the 20-second step. They entered the 40-second step and reached the step-2 FogDES input; neither completed that step. Both stopped at RK 3 after recording 17 `FULL` cloud-moment failures. The paired runs agree on all 17 rows. They also record 445 source-only failures, which remain a separate diagnostic count and are not the full-candidate result.

| v3 full-candidate classification | Count |
| --- | ---: |
| REAL64 candidate outside the coded 8-ULP pair gate | 14 |
| REAL64 candidate passes, independent REAL32 rounding crosses the gate | 3 |
| **Total full-candidate failures** | **17** |

All 17 are step 2, RK 3, pair 1 (QC/QNC), with positive ordinary-magnitude cloud Q and N. The exact bound check applies the existing `8 * SPACING(REAL(endpoint,REAL32))` tolerance. In the three storage-crossing rows, the REAL64 candidate passes that check, but independently rounded binary32 Q/N fail it. Two other rows fail the continuous check even though independent rounding would pass; the native store rejects those at the earlier continuous check. The logged `full_stored` pair is `(-1,-1)` on each rejected row, the routine's failure sentinel.

The 17 full failures are not 17 subnormal-Q cases. This evidence does not justify widening the tolerance or relaxing a gate. The separate strict QV predictor gate remains an independent open validation condition.

## v4 RK3 sub-quantum Q rows

The later closed v4 OFF run records 10 continuously valid FULL candidates at timestep 2, RK 3. Their REAL64 Q values range from 0.5094 to 0.7453 times the minimum positive REAL32 subnormal. Ordinary REAL32 rounding selects the minimum subnormal, but the nearest lower Q value is zero; storing that zero beside the positive rounded N fails the existing paired-state validator. In these rows, N is an ordinary positive value, so joint absence also removes the full stored N value. The signed Q and N representation deltas must both be recorded per pair; this numerical representation term is not a physical conservation claim.

The constrained storage policy therefore adds joint `(Q,N)=(0,0)` only after ordinary storage and the one-adjacent-Q candidate fail, and only for a continuous valid pair with `0 < Q < minsubnormal(REAL32)`. Its signed ledger records the actual extensive Q and N changes. Strict default and the earlier subnormal-only option keep their prior behavior. No mass-ratio tolerance is changed, and no positive Q at or above one REAL32 quantum is cleared.

## Identities and limits

- The v2 source-only ledgers have SHA-256 `f7ce6365240a93339dcf61003b61103feeab521a09efb978e621026d6732bd88`; both arms and their receipts are bound in the JSON. Their partial-overlay executable SHA-256 is `0ee83b88eb94112ad152b8f780e81e3c996cc86f2d70cba4095a89e6839fc8da`.
- The v3 source/full diagnostic ledgers each have SHA-256 `00688a8c1623135d5eeb777c08092ac982ac744afa475024cfe10e9f5e966bad`; the shared storage ledger SHA-256 is `d32e8863b14140a36813373c0ac0f89a990b64fcc60d7577c4a91a1e1d42c9aa`. Their distinct run receipts and source receipts are bound in the JSON.
- Both v3 attempts executed the same selected-object partial overlay, SHA-256 `0a53474445b5a1a021572ae05d99fc677993bd4355d7dac97383589bbdf72ea5`, pinned to the PR85 parent receipt and Intel profile. This is not a clean build. The candidate executable remains distinct from the frozen parent executable recorded by each run receipt.
- Values are local mixing ratios and number moments. No geometry-weighted or domain-integrated physical-kg amount is inferred.
- The 577 v2 Q-underflow rows support evaluating a common absent-pair representation only with explicit rejected continuous Q and N accounting. This evidence alone does not authorize that storage policy. The five v2 positive ratio exceptions remain distinct from Q underflow.
