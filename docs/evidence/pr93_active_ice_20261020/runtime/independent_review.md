# PR93 closed runtime audit: read-only review

Auditor: `docs/evidence/pr93_active_ice_20261020/runtime/closed_run_audit.py`, SHA-256 `8f9affa02e6d843d623911cfd6a9447a9ddb4ba0713cf927e2d5de2bcfb2e126`.

## Closed bound runs

- OFF and COUPLED receipts are COMPLETE through step 30. The per-arm audits verify receipt-bound compressed and expanded trace identities and source/executable/input bindings.
- Both existing strict source endpoint gates are PASS for this candidate: 0 current endpoint violations under the PR87 source-exact cloud/rain/graupel coefficient gate. This does not overwrite historical C18 results.
- The generic PR87 Q/N/B audit remains FAIL in both reports. Its state scope includes endpoint and predictor states; the active ice policy split is separately PASS.
- Generic audit failures split into 90 endpoint and 90 predictor states per arm: OFF has 74 endpoint and 87 predictor generic-failing states; COUPLED has 72 endpoint and 87 predictor generic-failing states. Predictor Q negative cells total 1,527 OFF / 1,528 COUPLED. There are zero reported pair negative/orphan/nonfinite counts and zero number-conversion failures.
- At endpoints, generic policy-bound exact-outside rain counts are 351 cells in each arm, with zero beyond the generic 8-ULP bound. This can coexist with current strict source gate PASS because the generic JSON rain bounds and strict source REAL32 PID/lambda recomputation differ slightly. For example, step 1 POST_KDM6 has 4 generic exact-outside rain cells and 0 beyond-8 cells in each arm. These are generic-policy event counts, not strict-source failures.
- Generic ice cone violations are inactive-pair findings: endpoint inactive beyond-8 counts are 921 OFF / 861 COUPLED; active beyond-8 counts are zero. Active ice policy status remains PASS.
- Selected T24 capture status is `FIRST_VALID_TO_INVALID_CAPTURED` in both arms. The report separately preserves the k=20 result and raw pair bits; no level write order or historical C18 cause is inferred.

## Initial-to-bound step-1 comparison

Each arm's exact serialized state + PBL step-1 prefix matches between the initial one-step attempt and final bound run: 883,241,700 expanded bytes each. OFF prefix SHA-256 is `34aba43561bdcfcd2c1da2c43c2a7644b188f220895b54aab4f3dfa6a1baaafa`; COUPLED is `d4877b247c3aca320fd86b1f2d7fbce9a7d622bb477b841525908d6b16ca3c2b`. Executable, candidate build, source receipt, wrfinput, wrfbdy, and namelist pins match; the launch-runner source hash differs, as expected for the PR91_RUN_ID environment fix. This comparison does not establish C18 source-prefix identity.

## Artifact integrity and scope

Per-arm reports are `off_closed_audit.json` (SHA-256 `7179ef5bf441504afd77f4a814309b709c2a1b0e5697014b4143443dd4101814`) and `coupled_closed_audit.json` (SHA-256 `36ce0a27884ab495c3cd644c093e54e3232fedb90965ec74baac0c9d376b52ac`). Prefix comparison SHA-256: `960334df8e112893b434dc099149e817327f863341b407f8d2e97106b1624975`. Compact runtime summary SHA-256: `635f56d3a40ef2cacb2f98c01cc2fe8127c7b2bcccf1e8647f08a3c4427b1f03`. Q/N/B scope split SHA-256: `a07040bf0401b58b5f2666cb7c4b9f0265e05d81b3f679eb19af65c0551e314a`.

The orchestration initially emitted a literal `\\n` suffix after otherwise valid JSON. Original per-arm bytes and hashes remain preserved as `.pre_serialization_fix`; only that suffix was removed and replaced by a newline, with output JSON validation passing. This did not change audit data or criteria. Full invocation and artifact hashes are in `orchestration.json` (SHA-256 `41538a5e736c8a11c3d05ef6362d1a2ae315323d24e5572d7ce0e84e14961562`).

These checks do not establish reaction throughput, precipitation suppression, water/energy closure, nucleation, or scientific approval. No model rerun or graph update was performed.
