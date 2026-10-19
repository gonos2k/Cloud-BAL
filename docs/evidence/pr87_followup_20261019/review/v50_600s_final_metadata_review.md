# PR88 final metadata review (read-only)

## Result

No factual or integration blocker found in the reviewed report and manifest snapshot. The prose keeps the completed 60-second result separate from both incomplete 600-second attempts. It says three steps completed through 60 seconds and T4 stopped before `POST_KDM6`; it does not report an 80-second or ten-minute result. `physical_approval` and the open closure/observation gates remain conservative.

## Reviewed pins

- Report `docs/PR87_SMALL_GRAUPEL_20261019.md`: SHA-256 `9415b15877c1073f445f2444b42c706d186316939eca518c75d1c2bed22e9291`.
- Manifest `docs/evidence/pr87_followup_20261019/manifest.json`: SHA-256 `93f42941c42a42a1afff37efaa62f71fdaad75951db53df8627ecf83772a6f48`.
- Paired 600-second runtime review: SHA-256 `7421494db67743966d6830d79324975519c29cddf53c41542490bd02cbd2e7e5`.
- Corrected T4 diagnosis README: SHA-256 `85a3fc54fbe5ef933cf988f21e1ff0ccd0d5ca74e50b9d2938510eb02c2a3e38`.
- T4 diagnosis independent review: SHA-256 `8c74a0fbbe8feec34d8f85b0f9ea80bde0e2bb262fbd51cbb31a15c387a79a47`.
- Focused receipt binds 28 passing tests and the current code/test pins: tool `76a8e25a641e57eeb5184eb21fb710cbf0fae64d5d1487442a3c052deb666710`; test `dc40165fa24dc2feeff335358917677e328cac2bc7c1f0302cda6d4c6217c09d`. The receipt identifies `tests/intel_toolchain.sh` and fresh-scratch Intel O0/O2 scope.

## Cross-checks

- Both native receipts are `INCOMPLETE`, return 128, have maximum timestep 4 and final completed step 3, with the same `KDM6 invalid base before nongraupel admission` fatal. The paired review confirms the 60-second prefix and all nine T1–T3 blocks match the separate completed window, and that neither T4 reached `POST_KDM6`.
- Manifest runtime paths, T4 diagnosis paths, report Markdown links, V50 build identity, executable hash, test counts and current source/test hashes resolve and agree. The paired review makes clear that the OFF cell replay is source diagnosis; COUPLED is only asserted to share the captured fatal class.
- Corrected T4 table units are internal KDM6 volume number concentration (#/m^3), not public number-per-kg. The source conversion multiplies by dry density at lines 468–481 and converts back for output at lines 1568 ff. The diagnosis and independent review now share the corrected README hash.
- The diagnosis attributes reason 6 to the strict NG validator after the existing rain-freezing packet accepted its separate 8-float32-ULP mean-mass allowance. It does not claim scientific approval of that allowance or propose a tolerance change.
- Cold group activity is explicitly `NOT_EVALUATED_NO_COLD_DATA_ROWS`; it is not described as zero. Historical baselines, scoped diagnostics and remaining scientific gates remain separated.

This review changes no repository source, tests, graph or wiki. It applies only to the listed metadata snapshot; recheck hashes if those files change before commit.
