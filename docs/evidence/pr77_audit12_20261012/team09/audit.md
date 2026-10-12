# Team09 Cloud-BAL serialization / validator authority audit

**Snapshot:** `9701ef23f04576d875508a0882d0e0af67282587` plus the current PR77 working-tree changes, at `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL`. Read-only review; targeted mutations were made only to temporary copies under `/var/tmp`.

## Findings

### A12-01 — P2: physical estimator source, quality, and time metadata lack validator checks

The writer serializes `_valid`, `_quality`, `_source`, and `valid_time` for the physical candidate fields through `put_thermo_field` ([cloud_bal_real_netcdf.f90:2152](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/src/common/cloud_bal_real_netcdf.f90:2152)). The independent physical-contract validator requires only the value and `_valid` fields and checks numerical values and validity against the canonical candidate; it does not include `_quality`, `_source`, or `valid_time` in the required bundle or cross-check ([validate_shadow_diagnostics.py:6311](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/validate_shadow_diagnostics.py:6311), [validate_shadow_diagnostics.py:6354](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/validate_shadow_diagnostics.py:6354)).

**Probe and limit:** on a copied available PR73 estimator artifact, setting `physical_candidate_vapor_source` and `_quality` to `2147483647` added no validator failures. Setting `physical_candidate_vapor.valid_time=1` also added no failures. The baseline was already numerical `INVALID`, artifact `UNBOUND`, candidate `REJECTED`, with 15 failures; each run retained those 15 failures. This demonstrates missing validation coverage only, not false acceptance. The suggested `verified-physical-shadow.nc` was absent from `/var/tmp/cloud_bal_pr73_joint_analysis.oevPdH` (that run directory retained only the estimator artifact).

**Next check:** add corruption tests for these arrays/attributes and either validate their bits/time and bind them to the canonical candidate metadata, or explicitly remove them from the claimed assessment contract.

### A12-02 — P2: blocked stage receipts are only partly persisted

The writer’s in-memory coherence gate requires `pipeline`, `column`, `balance`, `overall`, and `geopotential` statuses/reasons all be `FAILED/AUTHORITY` for estimator receipts ([cloud_bal_real_netcdf.f90:3035](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/src/common/cloud_bal_real_netcdf.f90:3035)). The NetCDF metadata records pipeline status/reason, column status, and balance status, but omits column/balance reasons and overall/geopotential status/reason ([cloud_bal_real_netcdf.f90:4143](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/src/common/cloud_bal_real_netcdf.f90:4143)).

The standalone policy remains unbound/rejected as requested: its existing checks require the normal producer status contract and only mark a candidate accepted when pipeline status is OK and there are no failures ([validate_shadow_diagnostics.py:7221](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/validate_shadow_diagnostics.py:7221), [validate_shadow_diagnostics.py:8446](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/validate_shadow_diagnostics.py:8446)). The existing O0 estimator artifact records `pipeline_status=-10`, `pipeline_reason=9`, `column_status=-10`, `balance_status=-10`, physical feasibility PASS, and the physical analysis extension. The standalone validator reports `column_status`, `pipeline status`, and `rejection reason` failures, among 15 total. That rejection is expected; the persisted receipt is incomplete for reconstructing all in-memory stage decisions.

**Next check:** if downstream audit needs a complete producer receipt, add an explicit estimator receipt extension with all blocked stage status/reason fields and a round-trip assertion; preserve standalone `UNBOUND/REJECTED`.

## Positive checks

- Writer repeats the estimator physical assessment against the supplied `state_in` and candidate, then compares both recalculated budget and evaluation to the pipeline receipt ([cloud_bal_real_netcdf.f90:2449](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/src/common/cloud_bal_real_netcdf.f90:2449)).
- Estimator mode has explicit shape, support metadata, boundary provenance, manufactured provenance, identity, missing-contract, component mismatch, coverage, and combined-thermo rejection cases in [test_real_shadow_io_contract.f90:489](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tests/test_real_shadow_io_contract.f90:489). The writer case asserts output creation but does not read back blocked stage receipts ([test_real_shadow_io_contract.f90:623](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tests/test_real_shadow_io_contract.f90:623)).
- The standalone validator replays the stored eight-component conservation relation, physical increment structure/identity, coverage, and candidate endpoint math ([validate_shadow_diagnostics.py:6124](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/validate_shadow_diagnostics.py:6124)).

## Graphify context and limits

The maintained absolute Cloud-BAL selected overlay is `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/graphify-out/2026-10-08-pr76-degenerate-kkt`: 8,542 nodes and 15,847 edges, snapshot `2026-10-08T10:05:56+00:00`, selected overlay `2f27b3fc680f5fad14b2efa2879ab5fddd5325f4` against `fd7e1be37075a7ba80ee3a0be080111a5be03a26` (68 committed changed paths only). It combines prior corpus snapshots and the selected PR76 overlay; it is not a full PR77 extraction. Graphify reports AST/Markdown-heading extraction and partial cross-file Fortran CALL extraction; external WRF sources were excluded. No new graph delta is claimed. The graph supports navigation only, not runtime or scientific validation.

## Coverage and exclusions

Covered: writer admission/re-evaluation; physical contract serialization and readback validation; status coherence and standalone decision; focused source/quality/time mutation probes.

Excluded: the complete upstream case-input reader matrix; broad corruption/mask matrix; a pinned Intel compilation/run; and full writer-suite duplication. No source, input, test, or evidence files were changed, and no test suite was run.
