# C14 closed 240-second runtime audit

Both paired runs completed successfully with `SUCCESS COMPLETE WRF`, status `COMPLETE`, rc 0, and 12 completed/seen timesteps. The paired identity, candidate executable/build, and unchanged-input checks pass against the archived C14 build and receipts. The detailed bounded audit is `closed_runtime_audit.json`; `runtime_summary.json` gives its compact result.

Each arm has 97 stage-trace records: 72 state records across 12 steps plus 25 non-state records. The inherited PR85 state audit passes and retains the inactive/active ice split at the native cutoff: inactive ice has 378 (OFF) and 379 (COUPLED) outliers beyond eight float32 ULP; active ice has zero. This inherited generic state result is distinct from the exact-source boundary audit.

The additional exact-source audit reuses `tools/pr87_completed_state_audit.py` and checks 36 records per arm: RK3 end, PRE_KDM6, and POST_KDM6 at every timestep 1 through 12. Cloud and rain use exact source coefficients, mass-ratio limits, and both REAL64 and REAL32 volume checks with no ULP allowance; graupel uses exact stored QG/BG bounds. Both arms have zero violations. All 36 joint transport rows per arm are feasible and use theta 1.

Each arm has 36 committed storage-ledger blocks and one p2 inactive-Q quantum adjustment (`[0, 1, 0, 0]` in pair order). Signed Q/N storage deltas remain separate per-pair pressure-coordinate numerical terms. The existing `SOURCE_REPRESENTATION` aggregation is separate; these values do not represent isolated kg loss or energy closure.

The sparse actual-store capture contains one failed baseline attempt per arm at T10/RK3/p1 `(130,182,2)`, failure stage 3, adjustment code 0. It is retained separately from the completed state and committed ledger. The model continued and completed the 240-second run; this row is not a fatal runtime failure.

`closed_audit.py` imports the C13 completed-prefix parser and adds the exact-source checks in the same decoded-state pass. `coverage_selector_attempt.json` records the earlier selector coverage miss and its precheck against the already-decoded 97-record metadata; the final audit supersedes that attempt.

This is a paired 240-second result only. No 600-second outcome is claimed here.
