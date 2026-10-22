# PR99-C2 native 640-second runtime record

This bundle records the completed three-arm PR99-C2 candidate-storage run. The arms used the same C2 executable and frozen launch policy with the original C1 OFF/HYDRO/COUPLED template inputs and boundary. HYDRO also used its separately receipt-bound native input. These are the C2 candidate inputs; they are distinct from the older C1/P20 captures.

The runner receipts report all three requests `COMPLETE`, return code 0, and final model step 32 at 640 seconds. The receipts are copied under `receipts/` and are the primary closed-run records. The launch observation is retained as a historical 08:38 UTC snapshot; its former `RUNNING` state is not the final status. `build_summary.json` likewise preserves its launch-time provenance and is not a closure result.

The completed closed-run audit is bound by `closed_result_summary.json`
(full private audit SHA-256 `7db371d79162c795a4be66ae92bbef2b4652fac97da11db423328ae007903fc9`).
The 39.7 KB public projection retains the identity, procedure, prefix,
T1-payload, policy, and history results; the large per-state tables remain
in the hash-bound 5.26 MB private audit. All three arms pass first-600
comparison of 180 trace records (12 fields, serialized bytes) and 11 raw
history times (10 fields, exact numeric values, with metadata checks).
T1 pre/post and PR67 expanded payloads are identical to their matching C1
captures. No whole-NetCDF byte identity or full-640 water closure is inferred.

The declared source endpoint gate passes at RK3/PRE_KDM6/POST_KDM6. The
separate active/inactive ice policy passes over 192 states per arm;
96 predictor diagnostic records are not part of the endpoint gate.
Generic Q/N/B failures remain **173/171/171 records** for OFF/HYDRO/COUPLED,
not unique cells. Physical approval remains **FAIL_OPEN**.

`bulk_storage_results.json` binds all 96 expected RK ledger rows per arm,
verified through compressed and expanded hashes and gzip EOF/CRC. Each
arm has 39 aggregate adjustment-5 events and 27 conditional tiny-B host
witness rows. The counts combine ordinary absence and new certificate
paths; certificate-only counts/locations are not observed. Q and B signed
sums are separate pressure-carrier-weighted quantities, not kg. Decimal
reductions use printed ES26.17 strings at precision 28; they are not exact
underlying binary sums. A witness/ledger join establishes call-level
association, not proof of every rejected trial or rollback branch.

The retained v3 reducer refused the actual receipt schema before reading
the ledger (`bulk_storage_v3_schema_refusal.log`). Reviewed v4 changes only
the binding of generated `.gz` metadata to the compressed-output record;
expanded identities are still verified independently. Five focused binding
cases pass. `bulk_storage_run.json` records the final rc=0 command and pins.

The runtime receipts include path/hash/size references for collected outputs, but this evidence bundle intentionally excludes model arrays, native append streams, compressed raw payloads, executables, full host source, compiler profile files, and KG files. The failed shell setup attempt is preserved as provenance; no model request was launched by that attempt. No source, build, or runtime change is made by this bundle.

## Build and input identity

- C2 source commit: `63c0e12`; source `module_em.F` SHA-256 `d82efa15ee1c0a44080a8ef40b8a8aef436661f2093b6f66bef7e666584aa296`.
- C2 build receipt SHA-256 `9c4802e12ea1d6a8f3c8b5ef1a5ff72116e5fbdbf9f6c78e906935622d45dafb`; executable SHA-256 `387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a`.
- Frozen Intel profile SHA-256 `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`; compiler IFX 2026.0.0.
- Root launch authorization SHA-256 `5420c264a6dabf1361e6ff4b0e448efdeee9b0f51811fcef79cb894005760363`.
- v3 bulk reducer SHA-256 `63b4ee606a21a31e44aa18e807ef4482493fd5a6e00a0164a6e7964b8d05a132`; independent source review SHA-256 `042c84ba40b298ebdc293567b7c7d96632ff3e2cdb12fce67cc206637d7a6d5a`.

The historical build summary records the pre-supplement audit-driver pin
`6b1d78db...`; it is preserved without revision. The actual closed audit used
`closed_audit_driver.py` SHA `6c85d05da948c2911a4d4c30c35f0c64eca0676401006650e4b375593eea6ccf`,
including the separately reviewed T1 payload supplement. The summary and
08:38 observation are launch-time provenance, not final runtime authority.

See `SHA256SUMS` and `closed_runtime_review.txt` (including the final bulk
result review) for the bounded inventory, independent checks, and limitations.
Reproduction requires the hash-bound private run payloads; this public
bundle is not a replacement for those arrays or a clean upstream rebuild.
