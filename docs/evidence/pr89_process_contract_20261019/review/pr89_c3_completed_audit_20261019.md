# PR89 C3 completed-prefix independent audit

Both 120-second arms closed `INCOMPLETE` after four completed KDM6 calls (80 seconds) and failed during T5 RK1. The executed candidate executable matches build SHA `ab8ff2312b8cb8cd65a44b78801d2938367f6e8793148d2ed1211479fe04ff97` in both receipts; staged and original inputs are unchanged. Build status is `PASS_OVERLAY_BUILD`, with `full_clean_build=false`, using pinned ifx 2026.0.0. Preflight binds 101 inputs, the same six 20-second steps, same boundary/namelist hashes, and arm-specific `wrfinput_d01` only.

The strict completed-state audit passes T1–T3 in both arms. At T4 POST_KDM6, cloud/rain/graupel strict source coefficient violation sets are empty. The generic existing ice diagnostic reports two pairs beyond 8 ULP in each arm, but both have QI below the native inactive-ice cutoff (`9.999998977483753e-15`): zero active ice pairs exceed 8 ULP. T5 is PRE_RK only, so the requested 120 seconds are not complete.

The fatal line in both arms is:

```text
PR87_GRAUPEL_TRIAL_REJECT 1 2 188 220 1 3313FC0F74539AB9 36610895A31A7272 33F16D2A0D5CBF25 373DB4CA633D4BA5 8000000000000000 8000000000000000
```

Decoded candidate endpoint Q and N both round to REAL32 zero. This is the next exposed joint-storage contract boundary, not a proven C3-introduced regression: C1 would also reject this bad-PSD/unrepresentable pair if execution reached it, and no C1 source contrast shows this exact cell passed. The audit records 12 feasible theta=1 RK rows through T4, then a T5 RK1 row with theta=0 and feasible false.

Machine-readable evidence: `/var/tmp/pr89_c3_completed_audit_20261019.json` (SHA-256 `9a6432422c7d52159590b8d0531e047754663bff14ff3bd71dd192cea34bdd17`). The audit does not compare C3's first 60 seconds against V50.
