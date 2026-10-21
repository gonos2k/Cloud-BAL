# PR94 C4 cold-process limits

Read-only audit of the closed OFF and COUPLED C4 runs in
`/var/tmp/pr93_{OFF,COUPLED}_600s_c4_bound_20261020`. Both receipts report
30 completed 20-second steps. The reducer and native-area join are the existing
`docs/evidence/pr93_active_ice_20261020/runtime/reduce_closed_cold_activity.py`
and `tools/pr90_cold_column_summary.py`; no runtime or model files were changed.

## Area-weighted activity, steps 1–30

Values are kg of half-L1 request activity, calculated with the existing
receipt-bound native area map. “Applied” and “deferred” partition the request
proxy; they are not reaction throughput, water residuals, or closure terms.

| Arm | Group | Proposed | Applied | Deferred | Deferred / proposed |
|---|---|---:|---:|---:|---:|
| OFF | AUT | 108,698,658,658.1 | 34,894,276,607.0 | 73,804,382,051.1 | 0.678982 |
| OFF | G | 1,174,298,657,600.4 | 359,780,533,022.1 | 814,518,124,578.3 | 0.693621 |
| OFF | NG | 602,615,356,218.7 | 490,173,816,636.7 | 112,441,539,582.0 | 0.186589 |
| COUPLED | AUT | 108,700,845,648.5 | 34,899,623,381.3 | 73,801,222,267.2 | 0.678939 |
| COUPLED | G | 1,173,902,652,467.7 | 359,768,122,148.9 | 814,134,530,318.9 | 0.693528 |
| COUPLED | NG | 602,680,203,105.2 | 490,153,971,384.1 | 112,526,231,721.1 | 0.186710 |

## What the frozen ledgers establish

- `pr89_kdm6_cold_summary.raw.gz` and `pr90_kdm6_cold_column.raw.gz` contain
  accumulated signed and half-L1 group activity. They do not preserve each
  transaction's individual scale factors.
- `pr85_kdm6_cold_budget.raw.gz` declares fields for `alphaNG`, `alphaAUT`,
  `alphaG`, and `compositeGamma`, but the corresponding write in the frozen
  `module_mp_kdm6.F` is guarded by `if (.false.)`. The two actual run files have
  only the header. Thus there is no transaction population from which to
  compute area-weighted individual-alpha/composite-gamma decompositions.
- `pr87_admission_reason.raw.gz` does contain selected `rain_aut_alpha` or
  `rain_g_alpha` for limited nonzero AUT/G requests (169,677 OFF rows; 169,690
  COUPLED rows). Its `endpoint_reason` is a separate full-proposal endpoint
  probe performed before the fraction search. The source comment explicitly
  says this is the first failed full-proposal check, not a unique active-bound
  certificate. It cannot identify which constraint selected the final alpha.
  The ledger does not record NG alpha, and is conditional on limited requests,
  so it cannot recover whole-population group distributions.
- `compositeGamma` is applied after the group alpha checks during joint
  backtracking. The all-transaction ledger that would pair gamma and the three
  group alphas is disabled. Sparse ice-event records may include these values
  only for their specific events; they do not provide a complete cold-process
  population or a general gamma decomposition.

The needed source predicates are `kdm6_rain_process_state_valid` and
`kdm6_rain_process_fraction` (including `failure_reason` and the actual
fraction-search result), followed by the composite backtracking loop that
updates `rain_composite_gamma`. A selected-constraint attribution requires a
per-candidate/per-bound trace tied to the chosen fraction, including the
post-alpha base state. Existing `PR87_ADMISSION` reason codes alone are
insufficient. Recovering alpha/gamma activity requires enabling or otherwise
capturing the currently disabled `PR85_KDM6_COLD` transaction row, then joining
its exact event weights through the existing dry-carrier and native-area map.

Evidence pins: frozen source SHA-256
`b358064642d81c86ee1f914c52620ade2c7589ccf302dcffd26d25809fd5adaa`; OFF
receipt `4569bfc353628a2512701428822916fbfdbe2c47954ce0c4050dfbd7d938398a`;
COUPLED receipt
`03ff4396ff4d6eed3978a8481dd11120aad30d3b59bc6af89bb20ebcf3d9e418`.
The existing activity JSONs preserve the reducer output, layout/map identity,
ledger and history hashes, and per-step coverage.
