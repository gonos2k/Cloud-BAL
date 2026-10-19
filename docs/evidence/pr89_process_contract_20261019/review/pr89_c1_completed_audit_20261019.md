# PR89 C1 completed-prefix independent audit

## Runtime and binding

The OFF and COUPLED receipts are both `INCOMPLETE` for a 120-second request. Each finished four 20-second KDM6 calls (80 seconds), then stopped during timestep 5 joint-moment admission. Both executed the same C1 executable (`2b3e5eb4d75c91797a6f500ce0956671fdd974530212cb51ac83a65e29bbce9a`); their recorded executable hashes match, input checks report no changed staged/original inputs, and both receipts bind build receipt `2fc300282b920ec9eccbf8a0c41cfc5e3365e3f8f94b25a76afeef60dd4c0c18`. Build is pinned Intel ifx 2026.0.0 partial overlay, explicitly not a full clean build.

Fatal at the failed fifth call in both arms:

```text
PR87_GRAUPEL_TRIAL_REJECT 1 2 151 187 37 3B800AB83227AC6B 3EC0B22FF0418A72 3C5BE7A593E8188A 3F9D0AF50F3AFDC3 8000000000000000 8000000000000000
```

## Completed state

The strict endpoint audit covers four completed calls plus a partial timestep 5 PRE_RK record (25 state records total). Timesteps 1–3 pass in both arms; strict cloud, rain, and graupel source-coefficient violations are empty at T4 POST_KDM6. T4 has two ice pairs beyond 8 float32 ULP in each arm, and the unfiltered diagnostic marks the endpoint FAIL. Both offending QI values are below the native consumer inactive-ice limit (`9.999998977483753e-15`); there are zero active-ice pairs beyond 8 ULP. The generic ice diagnostic does not filter by that cutoff, so its FAIL does not mean the native full-state acceptance gate rejected T4.

## RK and V50 first-60 comparison

Each arm has 12 accepted JOINT_RK rows for timesteps 1–4 (three RK stages each), all theta 1.0 and feasible T. Timestep 5 records an attempted row theta 0.0, feasible F. The first 60 seconds were compared field-by-field to the matching V50 arm across 251 aligned field records: timestep 1 is byte-identical; differences first appear at timestep 2 POST_KDM6 (3–5 cells per listed field), then propagate at timestep 3. OFF and COUPLED report identical first-60 difference counts. The exact stage/field counts are in the JSON companion; this review does not force first-60 equality.

## Evidence files

- Machine-readable audit: `/var/tmp/pr89_c1_completed_audit_20261019.json` (SHA-256 `dc3644fc1a056a013ae14b4f096126088f0496db39c413958679bd7c42c62e2e`).
- C1 OFF/COUPLED state auditor outputs: `/var/tmp/pr89_off_completed_state_audit.json`, `/var/tmp/pr89_coupled_completed_state_audit.json`.
- Run receipts: `/var/tmp/pr89_OFF_120s_c1_20261019/receipt.json`, `/var/tmp/pr89_COUPLED_120s_c1_20261019/receipt.json`.
- No model/source changes or additional native runs were made for this audit.
