# PR98 closed 640-second results review

**Result: GO for the bounded results report; runtime remains incomplete and approval remains fail-open.**

## Reviewed artifacts and pins

- Boundary auditor: `tools/pr98_boundary_audit.py`, SHA256 `77f911b4e4b552cc92c47885c3f7c875cad7028636fb06d9b8ec463e79282932`.
- Boundary auditor focused tests: `tests/test_pr98_boundary_audit.py`, SHA256 `594fdc7b33ba45b72f8cc4a570b18414b7d05bd550887cb743cf44d403f5e423`; 12 tests pass.
- OFF closed audit: SHA256 `4784a5f608344b54efefc48cb31273b81b89558800171f570264e14fbeb88e92`.
- COUPLED closed audit: SHA256 `737dec46528fe4dbdf343b288d6e8b231e7507cb81d0f208e643570d0601d836`.
- HYDRO closed audit: SHA256 `98101ac5b3bd11e6b8a461d931ecf4348a1bd99d570d331011bf25babafd897f`.
- Published bounded results: `docs/evidence/pr98_c1_boundary_20261022/closed640_results.json`, SHA256 `b54c480bf0a41663f45769def34da4f11df61cd1972aedf0d86d0fd75bf3bcd0`.
- Published report: `docs/PR98_C1_BOUNDARY_20261022.md`, SHA256 `cb45a66235c22ab9a8e370e038754c34492aaac233f37eb5e4c640de0becd202`.
- Integrated science assessment: SHA256 `9a2ff668a05c15a6540eab2cd802890656e5323821016a64fca9fa07b3dba210`; validation record SHA256 `3ecfb1ba00a0d9fc2c6407ac0e717f752637609350a217b44d0882a9815108e9` records 49 passing tests and the final three-arm runtime scope.

## Findings

All three receipts are closed but report `INCOMPLETE`, return code 1, and only 31 of 32 planned steps (620 of 640 model seconds). Every arm is missing its 640-second snapshot. The first 600-second trace comparison passes for 30 common steps and 180 state records, and the ten-field raw history comparison passes for 11 common frames through 600 seconds. The trace result applies to the comparator's declared fields/records; the history result is exact numeric equality in its declared fields and metadata, not whole-file byte identity.

The source-policy checks remain distinct: generic Q/N/B is FAIL (OFF 167, HYDRO 165, COUPLED 165), exact source endpoint is PASS, and active-ice policy is PASS. These outcomes do not convert the incomplete runs into complete runs or establish scientific approval; each audit correctly retains `INCOMPLETE_OR_FAIL` and `physical_approval: FAIL_OPEN`.

The public results agree with all three closed audit summaries for audit hashes, step counts, return codes, comparison counts, and policy statuses. The HYDRO result records the reviewed input-receipt path relocation proof. The report correctly separates the receipt's generic fatal markers and the closed-log joint-moment rejection from the unresolved first grouped transaction subpredicate; the local per-cell context enum is not promoted to that missing cause.

I reviewed the closed JSON summaries and bounded report only; I did not reread traces or histories, inspect running model data, or rerun the model. No publication blocker found.
