# PR97 C1 closed-results package review

## Outcome

**GO for the bounded KG selection and documentation.** The report and JSON agree with an independent rerun of the history postprocessor. No publication blocker was found in the reviewed package. This review does not grant scientific approval; the results remain `REVIEW_REQUIRED` and physical approval remains `FAIL_OPEN`.

## Bindings checked

- `closed_results.json` SHA-256: `bb69a2ec7ce83902c589ce6b3fa0464c3ade0e3e94d13c7a9ba45b5c32b6ba7f`.
- `hydro_response.json` SHA-256: `e53345d8539cbcde99017db0e9a46a09291c2caa61befde4278d1c5e5efe73eb`.
- The actual closed audit overview matches SHA-256 `201ab705b5f96a59f1e7c8f26e17cb42147eadfd9cbaff621cded60c92097a51`; its queue source pin matches the results receipt.
- The Intel compiler profile, build receipt, all three run receipts, preflight files, audit JSONs, and generated history files match the SHA-256 values recorded by the closed-results package and audit overview. All runs use executable `a714f00d3f81c0b47d94aef815f1f765ae48842e9de629cb869323ccfc22a96d`, common boundary `885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7`, and common namelist `afc366ae884021ae5eb91510f61a137cab30880ba9a81702094e763e5fb52f35`.
- Each arm is `COMPLETE`, return code 0, step 30/30 at 20 seconds per model step. The output histories contain 11 matched frames from 0 through 600 seconds. The HYDRO receipt and source-bound input chain pass the analyzer's current-generation and unchanged-input checks. The three arm initial-condition hashes remain distinct.
- The source-composed QC mask file matches SHA-256 `331eb9837c41a7aa663864c348f8fe18c44f8e55feed736900f5029685b1aa64`.

## Numerical and field review

I reran `tools/pr94_hydro_response.py` read-only against the three closed histories with its output directed to `/tmp`. The resulting JSON is identical to the reviewed `hydro_response.json` (same SHA-256).

For each of pressure (`P+PB`, Pa), mass-level geopotential (vertical average of `PH+PHB`, m² s⁻²), mass-point W (destaggered, m s⁻¹), and QCLOUD (kg/kg dry), I verified the table's 613-cell direct spatial RMS comparisons. At 60, 120, and 600 seconds, direct COUPLED−OFF RMS exceeds HYDRO−OFF RMS for all four fields; at 0 seconds the values are equal. COUPLED−OFF is computed directly from the coupled and OFF arrays, not inferred by adding component RMS values. The code's pointwise identity is an algebraic decomposition and is not evidence of causal attribution.

The separate face-wind records use actual cropped staggered U, V, and W history arrays at 0, 60, 120, and 600 seconds. Their respective shapes are 39×280×233, 39×281×232, and 40×280×232. These are distinct from mass-grid winds, the 613-cell support, and the destaggered mass-wind statistics. The report correctly makes no face-flux, continuity, or wind-closure claim.

Masks are 613 source cells, 2,496 cells in the fixed 2-cell Chebyshev buffer, 7,644 in the 5-cell buffer, and 2,533,440 cells in the active history domain. The report keeps the run comparison descriptive: initial states differ by arm, and shared boundary conditions do not isolate a causal mechanism or establish observation skill or forecast value.

## Audit interpretation and KG selection

The audit overview and three arm audit files agree with the closed-results summary: generic Q/N/B is FAIL with 161 OFF and 159 HYDRO / 159 COUPLED failures; exact source endpoint is PASS; active-ice 8-ULP policy is PASS. The queue remains `REVIEW_REQUIRED`; physical approval is `FAIL_OPEN`. Those statuses are kept separate in the results README.

The bounded KG helper selects the response tool and its focused test because the array-norm calculation is relevant, the PR97 documentation, and the two specified PR96 terminology documents. Evidence payloads, including the result JSONs, stay hash-only. Cross-file Fortran CALL extraction remains partial, and graph freshness does not establish runtime or scientific approval.

## Review scope

This review checked artifact identities, code paths and units, closed-run gates, audit-status mapping, and direct history metrics. It did not launch model runs, change source, run the test suite, or apply a graph/wiki update.
