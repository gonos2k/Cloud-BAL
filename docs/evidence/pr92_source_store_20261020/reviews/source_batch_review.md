# PR92 source batch review (read-only)

Reviewed the current PR92 authored diff, `PR92_SOURCE_STORE_CONTRACT_20261020.md`, `PR92_SCIENCE_RESPONSE_20261020.md`, and their linked source/store and QC evidence. No maintained files were changed.

## Consistency findings

- **D1 vs C15 scope is stated accurately.** D1 source/store replay is pinned to module SHA `1d6538e3e1aeb59a2f0f38b2ec8de8aef11c4991e2d6ae0c8d4641b065c821ef`; both source-chain and stage-6 paths close at O0/O2. D1 receipts remain INCOMPLETE at 14 steps. All 17 FULL stage-2 rows remain rejected by the new policy. The docs do not claim D1 proves legacy mixture acceptance.
- **C15 generation identity matches.** Retained `c15/module_em.F` and `graupel_store/witness/module_em_c15.F` both hash to `1ec3131abace4337314279ac833a6bcae32c0080261cccc912b45f0afba16399`, matching the generated-source binding. Core is `8ce23e675a23283fb047a88f6ca0d26444ed2f56a9e7dfdc872a1602a6f1d6bf`; executable pin is `cb1d845e059ebbc50ef3fa7bc3d5ed51ad2f8cdf0344bdefd9efa11e8bc62870`.
- **Storage policy and ledger claims match source/tests.** The new p4 opt-in remains narrow, code-5 changes have a separate signed extensive-Q/B ledger, trial counters/deltas reset locally and commit only on final success. Fixture cases cover strict/option bounds, pair-4 grouping alongside valid p1/p3, inactive-ice adjustment 4, code-5 ledger separation, and atomic rollback. The claim is numerical storage absence, not a physical phase process.
- **Validation counts and scope match receipts/logs.** Canonical Intel snapshot: 6,372 files, exit 0, hashes unchanged. Separate new Python suite: 39 passed. Default-off regressions: 14 passed. Historical C14 tests: 5 passed over the retained core pin `cf1384a06a82e2f3d03b4ca61db8fbfb8ad2e61d889e4290d790d7aa4d3be466`. Current core/fixture O0/O2 and generated C15 binding report PASS.
- **Science report keeps limits.** QC replay reports 624/624 exact REAL32 matches over 16 selected columns × 39 levels; it is not presented as a full initializer run or domain footprint. Horizontal source attribution remains open (131/288 values differ at PR83 input despite transferable geometry). C14 response maps/tracks are descriptive and carry no scientific approval or budget-closure claim.

## Remaining publication/runtime items

- At review time, C15 OFF/COUPLED processes were still active and no final receipts were present. The contract correctly describes the 600-second pair as running. D1's 14-step receipt/replay and C15 launch/build receipts are not full-run completion evidence.
- `docs/PR92_SOURCE_STORE_CONTRACT_20261020.md` links to `evidence/pr92_source_store_20261020/kg/README.md`, which is not yet present. Treat this as the planned KG publication placeholder and resolve it before final publication; the guarded KG helper is not yet applied.

## Selected code/document pins

- Core: `8ce23e675a23283fb047a88f6ca0d26444ed2f56a9e7dfdc872a1602a6f1d6bf`
- C15 generated module: `1ec3131abace4337314279ac833a6bcae32c0080261cccc912b45f0afba16399`
- New policy fixture: `69f11fb1fca0ae6a1d6cfefa368fb6f85fd1c890d02f4d8cbc893d5158b02b64`
- Policy source generator: `86d8c13efef6bd1e0fb7d5dbcaa07c346d323e2906ce116d6efb980e9f67b581`
- Source contract: `a3dde03ffdbf36666efc68a39e23a09001c3e3883619c102d0d7d1b34aec5af2`
- Science response: `3438560274ac8d510e685b26df3d897dd862ad6a719b765d6269f844e9524df6`
- Canonical snapshot validation: `9e8c5a5cc7cfb5a7a14cc4ae29a1c86ed4d9e47485e476156da0ff6d35abb1bd`
