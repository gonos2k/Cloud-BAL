# C14 240-second runtime audit independent review

Review scope: closed paired 240-second receipts, executable/build/input binding, state-trace coverage, the exact-source endpoint supplement, inactive-ice reporting, joint transport, attempted-store failures, storage ledger, and the matching primary contract claims. The running 600-second extension is not assessed.

## Findings

- **No blocker found for the bounded 240-second claims.** The audit JSON reports `PASS_240_PREFIX`. Its two receipts report `COMPLETE`, return code 0, and step 12. They bind the same candidate build receipt (`273b08fa…e053f`) and executed executable (`5581e1be…d812be`). Per-arm identity checks pass for the candidate build, staged/runtime executable and namelist, source receipt, unchanged input lists, and all noncandidate runtime inputs against preflight.
- Each arm has 97 parsed records: 72 state records and 25 non-state records. The 72 state records form complete six-boundary sequences for steps 1–12. The inherited generic state audit passes with the declared inactive-ice 8-ULP exception tracked separately: 378 OFF and 379 COUPLED inactive-ice outliers; active-ice outliers are zero. These counts are not a claim that every state passed the stricter cloud/rain/graupel predicate.
- The additional exact-source supplement selects exactly 36 records per arm: RK3 end, PRE_KDM6/rk0, and POST_KDM6/rk0 for each of 12 steps. It calls `tools/pr87_completed_state_audit.py::_strict_source_checks` and `_strict_source_violations`; coverage and zero-violation results are present in the audited JSON. The checks use exact source REAL32 cloud/rain coefficients with specific-ratio and REAL64/REAL32 density-times-number volume constraints, and exact QG/BG graupel bounds `[100,900]`, without ULP allowance. The primary document keeps the generic inactive-ice 8-ULP policy distinct from this 36-endpoint supplement.
- Both arms have 36 feasible joint-transport rows with theta 1. Each final C14 storage ledger has 36 blocks and one pair-2 inactive-Q quantum adjustment (`[0,1,0,0]` in pair order). The signed Q/N deltas are retained as pressure-coordinate numerical terms. The report does not interpret them as kilograms, energy closure, or an isolated physical transfer.
- The sparse actual-store trace contains one failed baseline call per arm at T10/RK3/pair 1 `(130,182,2)`, failure stage 3, adjustment 0. It is a rejected attempted call, recorded outside the committed ledger. The receipts complete and endpoint checks pass. Because this trace is failure-only, it does not itself record a corresponding successful per-cell source-first call; the report should ground “not committed/fatal” in the attempt status, completed run, and state/ledger checks rather than treating the sparse row as a success trace.
- The primary contract correctly limits its runtime claim to 240 seconds and states the 600-second extension is still running. The C14 manifest matches all 31 packaged file hashes and records the 600-second wrapper separately with status-at-refresh `RUNNING`; it makes no 600-second result claim.

## Reviewed pins

- `closed_audit.py` SHA-256 `6a31baf1cc3589a292e21b6cea5fc046ec18e6c6b435e98f5a2048f49923e3d5`
- `closed_runtime_audit.json` SHA-256 `875be1a620472caf9e017ffc0ca8b1f50466ccf96ec81f9ccacb267e669c5601`
- C14 manifest SHA-256 `c8c9b732d24a896a722ce75f36ebaa7d97f315bff80c3710876a86655d708e7a`
- Primary document SHA-256 at review `17c59c689400a8bfa4e22f334b2ae9237e495cbf0a341c3817dec529995cb65c`
