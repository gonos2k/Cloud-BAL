# PR87 final static review

Date: 2026-10-16  
Review scope: maintained joint transport kernel, current V42 producer overlay inputs, and focused source/test paths. This is a static and focused-test review; it does not certify the matched native run or scientific closure.

## Result

No concrete static correctness blocker was found in the reviewed changes. The joint update stages candidates before committing them, keeps the paired transport on shared face weights, and leaves strict full-candidate validation in place. Source-first fallback is restricted to the intended paired channels and retry path. The reviewed process paths stage related moments together and validate before commit; I found no new per-cell acceptance repair or tolerance widening.

The REAL128 diffusion change preserves the helper interface, REAL32 input fields, stencil, and REAL64 output. Its isolated endpoint regression passes with the unchanged strict store. This only supports the tested operator and witness; it is not a general proof that the stencil always preserves every cone.

## Validation

- Focused review set: **42 passed** in 18.48 seconds. The retained log is [`focused_tests.log`](focused_tests.log), SHA-256 `427b9e11b1a5889c8d2f0a20dd8f558ebe501a23f712a6220c89a6d49202255b`.
- The retained V42 suite log reports **194 passed** in 62.83 seconds; SHA-256 `e31e7f58e49e91ad32f1b29c3ea74a5875dda8cf981b3d8c50d3021bbb6e09d3`.
- V42’s selected-object overlay build receipt reports `PASS_OVERLAY_BUILD`, executable SHA-256 `04266c303b89a1c51775e735aa573ff52c2c1ec252d88ad7ccf6a2139dae8c2a`; receipt SHA-256 `a28f9a99af74d080c38b986fdc12f941845b34a93a41515089632df5137dd680`.
- The matched native run and completed-stage strict audits are outside this review and remain pending here.

## Limits and remaining risks

- Signed storage deltas are numerical representation changes in the pressure-coordinate ledger. They do not establish kilogram, energy, or complete physical conservation. Shared face fluxes support the transport conservation argument before storage; R32 storage and producer-side representation changes still require separate budget interpretation.
- The REAL128 stencil benchmark measured about **135.7×** the REAL64 helper time for a 64×64×39 active region over 12 calls with the pinned Intel profile. This is a helper-only timing, not a model-runtime estimate. The full model impact remains unmeasured.
- The tests and local replay cover selected producer states and parameter bindings. They do not establish a universal cone-preservation guarantee or full scientific approval.

## Bound source identities

The V42 generated-source, build, and archive manifests are retained under [`../pr87_two_step_v42_20261016/`](../pr87_two_step_v42_20261016/). The exact identities used for this review are in [`review.json`](review.json), including the maintained kernel, generated V42 Fortran sources, and key transformation inputs.

The small benchmark inputs are archived here as [`benchmark_baseline.f90`](benchmark_baseline.f90), [`benchmark_real128.f90`](benchmark_real128.f90), and [`benchmark_driver.f90`](benchmark_driver.f90). The transformed source generator and the captured V41 replay record are also included. No executable or full model arrays are included.
