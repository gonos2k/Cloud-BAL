# PR97 C4 620 s classifier review

Reviewed `tools/pr97_620_c4_failure_classify.py`, its focused test, the generated JSON and summary, both PR94 C4 run receipts, and the source/module writer bound by those receipts. No model run was performed.

## Result: GO, with a bounded interpretation

The classification is grounded in both PR94 OFF and COUPLED receipts. Each receipt points to build receipt SHA-256 `9ba94b0b0d4737641bd87d6237ff65e8b207bf8ae52c815521510d7d022f073d`; the staged `module_em.F` is SHA-256 `f88708844994a30540fc458aeede7e0eda4503a04a341caf714050e52f8c18af`. The classifier verifies the compressed FULL ledger and source-capture hashes against each run receipt, then requires a unique coordinate-key match between all FULL rows and all exact callback captures: OFF 7/7, COUPLED 6/6.

The exact-replay operands are sourced from the callback: Q/N REAL64 bits from `PR92_STORE_FAIL_FULL`, and the original density REAL32 bits from the adjacent `PR92_STORE_R32` record. During review, I found and reported an earlier density extraction defect (using low bits of promoted REAL64); the owner corrected it and regenerated the report. With the corrected operand, all 13 exact candidate replays reproduce the captured invalid result and stage under both pinned Intel O0/O2 profiles. The p4 call options were checked against the receipt-bound Fortran source, including `strict_mass_ratio=.true.`, zero `inactive_mass_limit`, and `allow_inactive_q_quantum_adjustment=.false.`.

The documented conclusion stays within the evidence: these are exact per-cell FULL callback rejections following grouped infeasibility, but they do not identify which cell or constraint caused the grouped transaction rejection. The generic 8-ULP classification is explicitly kept separate from the strict source gate. No claim is made that this establishes scientific approval or a forecast extension.

## Validation and artifact pins

Focused test run: `python3 -m unittest tests/test_pr97_620_c4_failure_classify.py -v` — 3 tests passed. The replay helper uses `tests/intel_toolchain.sh`, compiles in fresh `/var/tmp` scratch directories, and contains no model-run step.

- Classifier SHA-256: `9813612425f66985718b8b9b7d40f433708d2425e3fcf7f0647a320ad8b07507`
- Evidence JSON SHA-256: `bf23db734bc7f464dab05eec5e9c86bbbee82ace1b2602016de1b270b3066fde`
- Summary SHA-256: `04e8f76ea6b4a903e6f102d045d60decca2690c53c42b534bf3180ec37bf6f8c`

## Owner cleanup after review

The classifier was subsequently simplified to remove the obsolete decimal
interval replay helpers and unused imports. Replay outcomes are now joined to
FULL rows by the unique cell key, rather than relying on capture order. A
focused test reverses the capture order and verifies every cell still receives
its corresponding captured stage. The focused suite passes 3 tests, and the
regenerated JSON and summary hashes remain unchanged.

- Updated classifier SHA-256: `9813612425f66985718b8b9b7d40f433708d2425e3fcf7f0647a320ad8b07507`
- Evidence JSON SHA-256: `bf23db734bc7f464dab05eec5e9c86bbbee82ace1b2602016de1b270b3066fde`
- Summary SHA-256: `04e8f76ea6b4a903e6f102d045d60decca2690c53c42b534bf3180ec37bf6f8c`
