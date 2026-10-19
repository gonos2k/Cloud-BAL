# PR89 C5 runtime publication review

Read-only metadata review of the final bundle on 2026-10-19. No model trace was rerun or numerically recomputed.

## Checks

- Final bundle identity: Markdown SHA-256 `e793e461cabf840635b9320ba20ac4b3998b220ef280f6835c12edfdf7ebf274`; JSON SHA-256 `25b8160227b950f504b4589d09aa2c7f50a4e27a2b2bb864d5df9544167cc57f`.
- Both compressed completed-state audit files decompress byte-for-byte to their untouched runtime originals. OFF gzip SHA-256 `3d65a2589b24610770ede9e9bc5d76571702d44c3aa4a6c47760c5007d0e2dfc`, original SHA-256 `4c71a9a0821f519beda64e43a4a79e8a71dbd8f7f7c03855bb9b07cc66019296`; COUPLED gzip SHA-256 `32233e4911a2c94f3145d37550ca6b06ed72380479446ac617b6ad1b09670a94`, original SHA-256 `6ac96db37401abb7d7b719c227d0157d9f70c6a85f02e5992c225432d9ed3d50`.
- The JSON receipt hashes match the current OFF and COUPLED 120 s and 600 s receipts. Both 120 s receipts are COMPLETE, rc=0, final step 6; both 600 s receipts are INCOMPLETE, rc=128, final step 6.
- The 120 s ledger counts are consistent: 36 state records per arm (6 POST_KDM6, 6 PRE_KDM6, 6 PRE_RK, 18 RK_STAGE_END) and 18 feasible JOINT_RK records per arm at REAL64 theta=1. Cloud, rain, and graupel strict source-coefficient violation sets are empty at all 18 required endpoints in each arm.
- The independent ice split JSON hashes match the bundle. At the four reported gates per arm, outlier counts are 2, 20, 1, 1; all are inactive under the recorded REAL32 cutoff, with zero active outliers. The generic completed-state audit remains FAIL for both arms; the report retains that status and does not imply the split clears it. The single T5 POST record is included.
- For each arm, the bundle binds the 120 s and 600 s compressed trace hashes to its prefix-comparison record, reporting exact decompressed-prefix matches over 5,042,096,500 bytes and the corresponding prefix SHA-256. The report correctly treats this as six-step prefix preservation, not 600 s completion.
- The 600 s stop is described as a T7 rain public-store rejection with the exact sub-predicate unknown. This avoids assigning an unverified cause to the runtime error.

## Review result

I found no concrete metadata, count, scope, or wording contradiction in the final bundle. Its stated executable/build provenance is explicitly a PR87 source-mapped partial overlay (`full_clean_build=false`), and the report preserves both the generic ice-audit FAIL and the paired 600 s INCOMPLETE outcome.
