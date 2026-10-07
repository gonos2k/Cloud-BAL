# PR63 nonzero component-contract evidence

**Decision: `PASS_SCOPED`.** A synthetic, fixed-pressure 4×4×3 candidate with an independently predeclared nonzero condensation extent passed the existing pipeline, SHADOW writer replay, and independent physical-contract readback under the pinned Intel O0 and O2 profiles.

This is a writer/readback feasibility result. It is not production schema admission, source authorization, global optimization, native KDM6 acceptance, or evidence of reduced initialization shock.

## Changes exercised

- Internal phase extent is a separate ledger term, with zero dry-mass, net-water, and represented-enthalpy components. It is not labeled as external source or boundary transport.
- For explicitly contracted fixed-pressure candidates, the final pipeline closes stored dry-air mass on changed, valid thermodynamic cells using fixed pressure-cell mass and stored water mixing ratios. The physical phase extent remains based on the pre-transfer carrier. This representation closure is bounded by the caller's predeclared component tolerance; it is not a physical source or phase term. The endpoint helper leaves its incoming dry-mass values bitwise unchanged in cells whose thermodynamic values did not change; this does not undo any earlier block update.
- Writer replay and the independent reader check the same declared contract and stored endpoint. Legacy no-phase receipts remain supported.
- Invalid NaN water placeholders fail in the pipeline with `REASON_METADATA`; outputs roll back and the accepted budget is empty. The regression compares invalid placeholders without ordered NaN comparisons.

## Validation

The complete Real SHADOW I/O suite exited 0 with the pinned profile:

```text
CLOUD_BAL_WORKSPACE_ROOT=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50 \
CLOUD_BAL_TEST_SCRATCH_ROOT=/var/tmp \
CLOUD_BAL_KEEP_TEST_ARTIFACTS=1 \
bash tests/run_real_shadow_io_contract_tests.sh \
  > /var/tmp/pr63_run9_20261006.log 2>&1
```

The harness compiled separately at O0 and O2 using `tests/intel_toolchain.sh`, `ifx 2026.0.0`, strict floating-point flags, and the pinned NetCDF libraries. At each profile, the writer tests passed; the dedicated independent contract reader passed on both the nonzero phase artifact and the legacy no-phase artifact; and the legacy transition payload and full-file replay checks passed. The transition replay reports measured zero differences and explicitly labels the result **not approved**.

The focused O0/O2 suite also exited 0 for `test_pipeline`, `test_pressure_thermo_state`, `test_water_phase_transfer`, and `test_pressure_phase_transfer`. It used a fresh `/var/tmp` build directory for each profile. The pipeline test covers the NaN-placeholder rollback and changed-cell-only canonicalization regression.

The detailed receipt, including the writer command, focused build recipe, profile flags, toolchain/library hashes, source hashes, test executable hashes, and NetCDF artifact hashes, is [PR63_NONZERO_CONTRACT_EVIDENCE_20261006.json](PR63_NONZERO_CONTRACT_EVIDENCE_20261006.json). The full writer log is `/var/tmp/pr63_run9_20261006.log`; preserved artifacts are under `/var/tmp/cloud_bal_real_shadow.W0g57n`. Focused binaries and their result marker are under `/var/tmp/pr63_focused3.2AB9w2`; no full focused compile/run log was retained.

## Scope limits

The nonzero test artifact is intentionally 4×4×3. The production schema-7 validator keeps its 235×283×22 domain gate. The small artifact was checked by the dedicated physical-contract reader; it was not submitted for production schema admission. This test therefore establishes only the optional physical-contract and endpoint-readback scope.

No KDM6, native WRF, NE57 forecast, or initialization-shock test was run for this candidate. No source or boundary authority was authenticated by the synthetic fixture.

## Excluded attempts

- `pr63_run7` stopped before compilation because the nested checkout selected the wrong workspace root for the pinned `nf-config` dependency.
- `pr63_run8` was not counted as full-suite evidence: an interim edited pressure-transition assertion failed after its O0 writer and dedicated readers passed. The legacy assertion was restored before `pr63_run9`, which passed.
- An interim focused run failed because the test compared NaN placeholders with ordinary equality and included an invalid standalone-kernel dry-mass expectation. Those test assertions were corrected; the final focused O0/O2 run passed.
