# C10 source and store-contract review

## Identity reviewed

- Generator: `tools/pr91_source_first_diffusion.py`, SHA-256 `6cd06d2d81bfb829ff1703abaefb86483de89dd536b4a18d374a90da101e697e`.
- Focused tests: `tests/test_pr91_source_first_diffusion.py`, SHA-256 `3d07b17312c26514065d4587a7d6d57cc4f76bdbe74f87d47b7852506a7c292b`.
- Emitted module: `/var/tmp/pr91_sources_c10_20261020/module_em.F`, SHA-256 `af54a8bd951e47407f6900dbfd4b16396cd6fc30753bb32437fd46c45b86be4c`.
- Emitted solve source: `/var/tmp/pr91_sources_c10_20261020/solve_em.F`, SHA-256 `dd3d8436ec6e7712ea8b62a33502acf89832f2d8a9f45969f84968f06ff78ca6`.
- Generator inputs are the pinned D3 `module_em.F` (SHA-256 `dc21f48b29784f7ab6bbb6975ef541d184b31effa796b0e5aab51b16e80d406d`) and C7 `solve_em.F` (SHA-256 `412183300ea8dd6af028ac1a5254f937477b054db4eb1f5910a6bf974c3c5`).

## Findings

No source-contract blocker found. C10 starts from D3, so its source-only cloud endpoint keeps the original strict mean-mass store and does not inherit C8's source-endpoint volume-number gate. The later joint consumer still calls the existing `joint_moment_store` with the captured volume-number bounds for cloud and rain. It stages all pairs before committing, so the added diffusion calculation does not bypass the final paired-store validation.

The transformed source evaluates `horizontal_diffusion64` on the stored source-prepared Q and N fields, subtracts the producer-captured old-state diffusion rate, and adds that difference once to the later non-air residual. It uses the cached RK1 timestep and footprint identity, checks both paired cache channels, and rejects changed producer bounds. The virtual donor is formed after this pass. The existing transport and final commit order remains downstream.

The pinned T2 contract fixture keeps its captured source candidate, density, and bounds fixed. The mean-only D3 intermediate returns Q/N binary32 `34784CDA/4C529864`. The same intermediate itself does not pass the strict volume test. Passing that exact stored pair into the existing strict-volume `joint_moment_store` performs its pre-existing normal-Q adjustment (adjustment 2), succeeds at stage 0, returns `34784CDB/4C529864`, and leaves N unchanged. This establishes the intermediate-versus-final store behavior in the core helper. It does not establish that a full native physical update reaches this candidate or demonstrate model-level conservation.

Validation: the four focused tests pass (`pytest -q tests/test_pr91_source_first_diffusion.py`, 4 passed). The T2 store-contract helper is exercised at Intel O0 and O2. The separate diffusion fixture compiles the maintained `tools/pr87_horizontal_diffusion64.f90` manufactured operator, whose internal arithmetic is REAL64; it is not an exact replay of the native routine. The native C10 implementation is embedded in `/var/tmp/pr91_sources_c10_20261020/module_em.F`, SHA-256 `af54a8bd951e47407f6900dbfd4b16396cd6fc30753bb32437fd46c45b86be4c`, lines 871–940, and uses REAL128-internal arithmetic. The fixture tests the donor expression and a synthetic operator replacement; it is not a bitwise or arithmetic replay of that native kernel.

The C10 selected-object overlay build passed, but both paired 240-second native runs closed `INCOMPLETE` after the one completed T20 state. They failed at T2/RK3 with `PR87 unsafe complete source-prepared virtual donor`; the exact failing guard operands are not captured. The completed T20 prefix passes the strict-pair and native inactive-ice checks; the T2/RK3 diffusion-delta row has no matching `JOINT_RK` row and remains proposed, not applied. See [the closed-prefix audit](c10_t20_completed_prefix_audit.md). No full native diffusion/air-chain pass, physics validation, or model-level conservation conclusion is established.
