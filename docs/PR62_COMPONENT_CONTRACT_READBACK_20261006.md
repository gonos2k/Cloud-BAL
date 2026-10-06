# PR62 physical joint contract SHADOW readback

## Scope

The optional `physical_joint_candidate_contract` now survives pipeline evaluation and SHADOW writing. Contract presence is determined by `PRESENT`, so an explicitly supplied default constructed object is evaluated and rejected for missing coverage. An omitted optional argument keeps the legacy SHADOW path. Writer endpoint validation passes the retained contract only when allocated; replay does the same through an explicit allocation branch.

The NetCDF extension stores the caller supplied identity label, adjustable-variable bits, cell coverage, component source and boundary increments, physical tolerances, and feasibility result. It also stores the canonical thermodynamic inputs needed to independently recompute the eight local components: dry-air mass and temperature plus vapor, cloud water, cloud ice, rain, snow, and graupel. The Python reader recalculates those component residuals and coverage/tolerance checks from the bytes in the file. Where standard candidate fields are present, it requires exact agreement with the retained physical bundle; both background and candidate dry mass are also checked against pressure mass and represented water.

The identity is a label, not authenticated authority. The serialized bytes and their binding to the pipeline snapshot establish what the writer retained; they do not approve the named source. The Python readback scope is the eight local component residuals and coverage/tolerance contract. It does not reproduce the full Fortran `assess_physical_joint_candidate` authority checks because all field-level source and boundary metadata required for that replay are not serialized. Writer validation still runs the complete Fortran assessment before retaining a result.

The gate remains distinct from trial search and optimality. These tests verify the supplied candidate contract and file readback; they do not run an optimizer or establish an optimal candidate. Existing files without this optional extension retain their prior validation path. The present empty-contract, absent-contract, and blank-identity cases are separately tested.

The writer round-trip fixture is a schema-5 no-op with a zero component declaration. A separate joint-candidate evaluator test already exercises a nonzero, predeclared +0.5 K temperature candidate; its enthalpy source is independently calculated from background dry-air mass and mixture heat capacity, and temperature is the declared adjustable field. The writer API accepts a coherent pipeline result, while the current pipeline request surface has no operation that prescribes an arbitrary +0.5 K temperature increment. Creating a file fixture by editing the candidate after the pipeline or by fabricating a stage ledger would test an artificial path. Therefore the nonzero case remains an evaluator test, while the actual writer round-trip establishes serialization and replay for the supported no-op contract case.

## Validation evidence

The focused runner was invoked from a fresh `/var/tmp` scratch directory with the pinned Intel profile in `tests/intel_toolchain.sh`:

```text
CLOUD_BAL_WORKSPACE_ROOT=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
CLOUD_BAL_TEST_SCRATCH_ROOT=/var/tmp
bash tests/run_real_shadow_io_contract_tests.sh
```

The runner produced a real SHADOW file at both O0 and O2. Those writer fixtures were compiled with pipeline source SHA256 `69201919089deda323e1fdef49cfad859235226bc25e76dd35ff7e5d85e2b6be`; that pre-cleanup source snapshot is preserved at `/var/tmp/pr62_joint_contract_evidence_20261006/cloud_bal_pipeline_writer_build.f90`. It was reconstructed by reversing only the subsequent optional-presence cleanup hunk; the writer fixture scratch timestamps predate that cleanup. The complete build source hashes are recorded separately from final source hashes in the evidence JSON. The final pipeline source SHA256 `a9e923b4d23c1bc75b54f474b8ec7a74822b3b9b78a2f787e6b5805b8800761b` was subsequently recompiled and the pipeline authority test passed at O0 and O2. That pipeline edit only inlined the optional-presence inquiry and removed a redundant local boolean. The final pipeline was not part of the writer-fixture build.

For each writer fixture, `tests/check_physical_contract_shadow.py` reported `Physical SHADOW contract readback and corruption checks passed`; its eleven rejection mutations cover forged source, coverage gap, NaN, negative tolerance, wrong coverage shape, wrong source dtype, packed tolerance, packed candidate mass, missing bundle, a coordinated detached candidate bundle/source, and a negative vapor value with coherent mass/source declarations. Two synthetic reader positive controls are accepted: a cloud-water change with independently recalculated dry mass and source, and a +0.5 K temperature change with independently prescribed mixture enthalpy source. Neither is presented as a writer-produced fixture. Both actual writer fixtures have SHA256 `1f52fccaac7fe2085bd43d3d8a661514f86a62c91fb35186db3c077258d3593d` and are preserved at `/var/tmp/pr62_joint_contract_evidence_20261006/verified-physical-shadow-O0.nc` and `verified-physical-shadow-O2.nc`.

The independent readback reruns and their output hashes are recorded in `docs/evidence/pr62_component_contract_readback.json`. The exact code hashes, pinned compiler profile, paths, and fixture hashes are recorded there as well. The pipeline authority test was separately compiled at O0 and O2 with the pinned Intel profile; both runs printed `Cloud-BAL pipeline authority tests passed`. It verifies omitted contract behavior, explicit empty-contract rollback with `REASON_REQUIRED_COVERAGE`, and allocated arrays with blank identity yielding `UNSUPPORTED` / `REASON_AUTHORITY`.

These are implementation and serialization checks. They are not full physics approval, source authentication, trial-search evidence, or optimality evidence.
