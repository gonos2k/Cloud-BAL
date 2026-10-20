# Independent C14 T15 and 600-second prefix review

Review status: **no blocker found**. This is a bounded artifact and source-guard review; it does not repeat full trace parsing or certify a completed 600-second run.

## T15 event record

The source-event JSON was received at SHA-256 `69789921e3a6d45f8e48549ee7518fa02c8ca1db76ad69778ec3d99f7676f035`; its interpretation text was updated below for the pair-4 channel naming. The pinned module and shared core match the JSON's source hashes (`6a7a97c23c84f05837a3bb5e384ce944ecd2df220ea1889d990349cd509094b1` and `cf1384a06a82e2f3d03b4ca61db8fbfb8ad2e61d889e4290d790d7aa4d3be466`). The event's ifx build receipt, compiler profile, and executable hashes agree with the C14 build receipt identity. Both closed receipts identify the same T15 RK1 pair-4 cell `(i=2,j=218,k=13)`, are `INCOMPLETE` with return code 1 after 14 completed steps, and bind RSL gzip files whose hashes match their receipt entries. A narrow lookup of the two compressed RSLs confirmed the recorded source-identity and reject-context lines in both arms.

The source guard mapping is correct. `add_graupel_diffusion_mixture` returns before the identity check if either `graupel_diffusion_point` call is invalid; the emitted zero increments therefore came from valid point calls. The following reject code 6 is `certify_graupel_storage`'s local `reject_reason`, not `joint_moment_store`'s `failure_stage`. The code-4 store fallback is downstream of that return and was not reached. The record localizes the mismatch; it does not identify the failed initial-store subpredicate or explain the upstream payload/recomputed-increment difference.

I corrected the event note and JSON interpretation to reflect the caller's pair mapping: generic Q/N argument names, with pair 4 mapped to QG mass and QIB bulk volume. `ns64` is not a particle-number concentration in this call. Payload units and complete provenance remain unresolved. No storage-quantum, PSD, FTZ, or rounding cause follows from this record.

## Closed 600-second prefix package

The 600-second closed audit SHA-256 is `f0011302d7c5f501c9878653a7e9d8c2854af527644e8748d9c2dcd9d9a5bc32`; its completion partition is `f7e8f51a868dd21d923c34369d05a37a9882f57fc282b494b0e7d3afb7d28e37`, and the arm-selector wrapper is `1ebec2c34b1acdedd64e20eb4b80a0e75e509c04b8577da408c9c64bb303f5f4`. The package binds both arms to build receipt `273b08fa9bb31d4070f59c817b3d59f77154947366dbcf8edb53c546360e053f` and executable `5581e1be3febd54409304ccf7cbe305830a75968858075bf0d95f68b48d812be`. Each arm's receipt, preflight, executed executable, run executable, namelist, source receipt, and unchanged inputs pass the wrapper's identity checks.

The wrapper delegates selection and strict checks to the previously reviewed C14 prefix parser and C13 source checks. Both arms have 14 completed steps, maximum seen timestep 15, 84 strict state records passing, and 42 selected source-boundary endpoints passing. The 43 retained joint transport rows comprise 42 completed feasible theta-one rows plus the partial T15/RK1 rejected row at theta zero. Each requested 600-second run remains `INCOMPLETE`, return code 1; the audit status is `CLOSED_PREFIX_REVIEW_REQUIRED`, never `PASS_600`. The sparse attempted-store trace contains the separate T10/RK3 cloud stage-3 rejection; it has no T15 store-attempt row. The T15 event happens before the later mixture-store call, so no T15 committed-state or store-stage claim is made. The closed 240-second C14 result remains separate.

One selector metadata label is stale: the strict-source report retains the boolean key `coverage_all_12_steps_x_3_boundaries`, while the same record reports `coverage_expected_steps: 14`. The wrapper sets its expected prefix from each receipt, and the selected stage list has 42 entries (14 × 3); I interpret the passing coverage as 14-step coverage, not 12-step coverage. The raw audit was left unchanged.

## Five-time native maximum table

The primary report's C14 table at 0/60/120/180/240 seconds matches the C14 response summary's whole-native `max_abs_difference` values to the displayed precision. The summary shapes distinguish P+PB mass levels (39) from PH+PHB interfaces and native W faces (40 each). The report labels these as whole-native maxima and explicitly says they may occur at different locations. Its separate reference to the C7 27-column support is clearly scoped to the prior-history diagnostic; the five-time C14 table is not described as a 27-column or same-location result. The table makes descriptive matched-arm claims only and does not imply closure, observation skill, or causal isolation.

## Reviewed artifact pins

- Current source-event note SHA-256: `734e86d2795113bdfa28ff46a38c4639f61d73d260e256c6425923208a4306f2`
- Current source-event JSON SHA-256: `f63992e8ff48bea046a82c69762b55eb9c3284748a10c40755006c1c9c405d99`
- Current C14 response summary SHA-256: `8b5803001908e89a3d9a5432dc495b2604bdb395a017cdc068669856a7d66efc`
- Primary report reviewed: `docs/PR91_HOST_STORE_CONTRACT_20261020.md` C14 diagnostics section
