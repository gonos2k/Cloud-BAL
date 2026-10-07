# PR65 Phi mutation-suite follow-up (2026-10-07)

## Scope and result

This follow-up runs the complete independent pressure-geopotential reader and mutation suite against the retained PR64 O0/O2 candidate artifacts. It does not rebuild Cloud-BAL or rewrite either candidate. The candidate files are byte-identical (`ba4e8466903492b905a6f042257d8183614c9536fe0c0211acab7fcef4951991`).

The complete O0 and O2 reader suites passed with exit status 0. Each run guarded the retained artifact and original PR64 `FAIL_OPEN` receipt before and after execution, and guarded the reader, imported validator files, selected Python/NumPy/netCDF4 runtime files, and frozen runner. O0 used a frozen private runner copy with the exact worktree root embedded; its SHA-256 is `e19d52106bb2d67e4ffa10d4621107ebdb099b64f2d0847666faf51a6890ff66`. O2 used the runner in this tree. Both artifacts retained SHA-256 `ba4e8466903492b905a6f042257d8183614c9536fe0c0211acab7fcef4951991`. Receipts, logs, and pre/post hash manifests are preserved in [O0 evidence](evidence/pr65_phi_mutation_suite_O0_20261007.json) and [O2 evidence](evidence/pr65_phi_mutation_suite_O2_20261007.json); the exact private O0 runner and first O0 wrapper-failure record are also checked in under `docs/evidence/`.

The first O0 invocation also printed both final `PASS` lines, but its shell wrapper failed after the reader exited because the runner file was edited while that process was active. Its post-run guard was not captured. This attempt remains separately recorded as `READER_PASS_WRAPPER_FAIL` in [the initial O0 failure receipt](evidence/pr65_phi_mutation_suite_O0_initial_orchestration_failure_20261007.json), alongside its reader log; it is not counted as either guarded pass. The original O0/O2 PR64 receipts remain `FAIL_OPEN` and unchanged.

## Mutation coverage

The full invocation checks normal independent replay and the Phi summary claims; rejects manufactured source bits, missing required Phi attributes/variables, malformed support storage including wrong type and dimension order, and removal of the Phi extension; and rejects isolated mutations to candidate/background Phi, the reference anchor, support, validity, quality, source, change masks, and contract attributes. It finishes with normal replay, storage-tail mutations, and the historical no-Phi assessment.

The dimension-order corruption test now writes a shape-compatible transposed payload for its intentionally malformed `(z,x,y)` variable. This lets the reader reach and reject the malformed dimensions instead of raising during fixture construction.

## Limits

The suite validates serialization and independent physical replay for the retained artifact. It does not change the PR64 physical or operational gates: authenticated source/boundary authority, the observation-withheld fixture scope, wind driver, and downstream WPS-to-real handoff remain unresolved as documented in [PR64 candidate notes](PR64_REAL_CANDIDATE_20261007.md).

The runtime manifest fingerprints the Python executable, selected package entry points and native extensions, and source modules. Its dependency closure is partial: transitive bundled shared libraries loaded by netCDF4, including HDF5 and compression/TLS libraries, are not included. The suite used `/usr/bin/python3` 3.12.3 and performed no Fortran compilation.
