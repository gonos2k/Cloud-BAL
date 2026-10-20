# PR91 source-team review (read-only)

Reviewed the pinned C7/C12 diagnostic and source-first tools plus their focused tests. This is not a C14 review. Candidate HEAD's shared-core source is SHA-256 `c8ecedde5cc8f9adedf6cf082054596ca1c0d6a3565d152c73d730c00cd678f3`, matching the trace tool's pin. The current worktree shared-core file is dirty during the active C14 effort, so it is not treated as a frozen test target.

## Findings

1. **Replay provenance finding resolved in the reviewed update.** Parser now requires every option/failure row to match one trace run ID, rejects multiple IDs and enforces the closed diagnostic identity; `trace_metadata()` binds raw bytes, compressed artifact where applicable, capture record count, and source-run-root consistency. `main()` checks trace bytes did not change between metadata binding and parsing. The core is now pinned to archived `validation/final_i/cloud_bal_joint_transport.f90` by SHA, rather than the mutable maintained core. The 11 focused parser/metadata tests passed per root; I independently inspected `/var/tmp/pr91_d3_bound_replay_20261020.json`: it binds run `PR91-D3-OFF-200s-20261020`, 17 rows, raw SHA `3231d1a51f6f701b9d5db5a87a18e9edaee7c263eff7401cf46dfa81e4352d5a`, compressed SHA `06836135ffc87528595d29f51286b34edb33aa391098c0a999521b926601ba48`, and both O0/O2 classify all 17 as `REPRODUCED_FAILURE`. Emitted scope correctly says external runtime assertions are not revalidated.

2. **Trace-capture setup is a required precondition.** The trace writer deliberately fails closed if `PR91_RUN_ID` is missing or the output cannot open (`tools/pr91_host_store_trace.py:213-217`), before the existing fallback is tried. The run setup contract documents required identity/output availability; this is not a normal-path candidate-math change. Final runtime review should bind that the preconditions were met and distinguish setup failure from physical candidate failure. No policy change requested by this review.

## Code and rollback review

No candidate-math or commit/rollback defect found in the reviewed source-first path: it forms prepared fields from the physical source endpoint, evaluates the pinned existing diffusion operator on those fields, restores the captured non-diffusion source component plus prepared diffusion into the existing joint updater, and commits `q_stage/n_stage` only after final feasibility. The trace captures candidate values from the actual final `joint_moment_store` call and leaves sentinel/rollback behavior intact. Writer format, parser field offsets, and options arity are internally consistent in the reviewed sources/tests.

Limitations: read-only source review; no tests executed. This does not cover in-progress C14 core changes or establish native/runtime/scientific acceptance. Re-run focused tests and refresh this review after C14 freezes.

## Exact reviewed hashes

| File | SHA-256 |
|---|---|
| `tools/pr91_host_store_trace.py` | `3f694f9ecfd19d8ce93c59feab64d12382ba789d80755851eb477735a26850e8` |
| `tools/pr91_host_store_replay.py` | `025d482991c6fa0586f110b8943275337151e5a133f207606d41f4fa343b26d9` |
| `tools/pr91_source_first_diffusion.py` | `80b654e32bcda6207aa69825f1ff5bfad4410ad681bdcaa67e53b68e14322796` |
| `tools/pr91_virtual_donor_capture.py` | `c400f92525b7deb9e0fc839cc39932c7b9de261151335052933f53e0e381f77e` |
| `tests/test_pr91_host_store_trace.py` | `79d92b5bfc612bc97112dd38669452ad443a923c7ecd1ea7c9fb2da130053e85` |
| `tests/test_pr91_host_store_replay.py` | `58f1fbbc11c207885226b8937789a42239adad8bafd79aaffa2ed88636d61e45` |
| `tests/test_pr91_source_first_diffusion.py` | `9e8756b2d48774d5eaf692cd3d8c74253a9bfc27086776d2cb6c56176f8219e6` |
| `tests/test_pr91_source_first_diffusion_c11.py` | `ba6f2f2c1e83b42426370b37e4b0d41a5cce329865637f853db2f849848208b4` |
| `tests/test_pr91_source_store_contract.py` | `ab36b46c03e6b9d084e2189d16ad835adf831ddc71dd9c221392e4843bac6d8d` |
| archived replay core `docs/evidence/pr91_host_store_20261020/validation/final_i/cloud_bal_joint_transport.f90` | `9cfc20a3724b9a71b0be912d7f6746cd3ae5f17128dd743539a34ddadfd862a6` |
| `tests/intel_toolchain.sh` | `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4` |
