# PR89 C4 completed-prefix independent audit

Both 120-second arms closed `INCOMPLETE` after four completed KDM6 calls (80 seconds). Their C4 executable hashes match build SHA `5c7f6ff646d4867e4e21194d071a12db9bfad6ad4ef303d7d3bc75fd150268a4`; receipts report no changed staged or original inputs. Build is pinned Intel ifx 2026.0.0 `PASS_OVERLAY_BUILD`, with `full_clean_build=false`.

The strict completed-state audit passes timesteps 1–3 in both arms and finds empty strict cloud/rain/graupel violation sets at T4 POST_KDM6. T4's generic ice diagnostic reports two positive pairs beyond 8 ULP, but both are below the native inactive-ice limit (`9.999998977483753e-15`), so there are zero active ice pairs beyond 8 ULP. The audit's generic `FAIL` label reflects its all-positive-pair diagnostic; it does not indicate an active-ice contract violation. T5 has only PRE_RK and does not count as a completed call.

C4 and C3 have **exactly identical** stage traces through the first four steps in both arms: 33 records, 333 fields, and 3,378,551,280 field bytes compared per arm; no metadata or data mismatch. The entire compressed trace hashes are also identical per arm. This comparison is C4 vs C3 only; no V50 identity is assumed.

At T5 RK1, both arms fail at `(i,j,k)=(188,220,2)` with:

```text
PR87_GRAUPEL_TRIAL_REJECT 1 2 188 220 2 3383F446E813526C 36D101F352E66E25 346166B78DD72367 37ADA9CCD75CAC3F 8000000000000000 8000000000000000
```

The candidate Q endpoint rounds to REAL32 zero; N rounds to nine positive REAL32 subnormals. This is the next observed storage-contract boundary. No conclusion about physical invalidity is drawn from the candidate failure.

Machine-readable audit: `/var/tmp/pr89_c4_completed_audit_20261019.json` (SHA-256 `76ec4fab014c06eed68f9362d71c710ac1f0838bc9750096e9d38ab56d7d56f2`).
