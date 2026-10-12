# Team 10/12: Cloud-BAL transaction and provenance audit

Scope: read-only review of `scratch/pr77_native_state_20261012/Cloud-BAL`, based at `9701ef23f04576d875508a0882d0e0af67282587` with the visible PR77 working tree. Reviewed the stage coordinator, transaction/recovery publisher, detached runtime and Landlock policy, producer/build/compiler audit, E01 gate, stage-off semantic validator, and focused tests. No source, model, or evidence files were edited. No publish action, external message, or compile was run.

## Findings

### F1 — E01 fresh-output gate ignores symlinked directories

**Priority:** P1 (reproducible gate bypass)

`tools/e01_completion_gate.py:94-103` walks `root.rglob('*')`, skips anything for which `Path.is_file()` is false, and only rejects symlinks after that check. `pathlib` does not recurse through symlinked directories, so a symlink at a generated namespace directory is silently omitted from the inventory. `assert_fresh_generated_namespace()` then sees no generated product and accepts the runroot.

A safe `/var/tmp` probe created `runroot/lapsprd/lco -> <outside-temp-dir>` with a stale `262281200.lco`. `inventory(runroot)` returned `{}` and `assert_fresh_generated_namespace({})` accepted it. This permits stale generated products to be visible through the runroot and can direct a producer to follow a generated-output directory outside its intended isolated tree.

Existing test: `tests/test_e01_completion_gate.py:126-134` rejects a regular preexisting `.lco`, but does not cover symlinked directories. Recommended closure: reject symlink directories during a no-follow tree walk (or reject all symlinks before considering file type), and add this exact nested stale-output case.

### F2 — E01 producer check does not itself bind bytes to the subsequent exec

**Priority:** P1 (unimplemented integration closure; no live runner caller found)

`tools/e01_completion_gate.py:170-181` checks the executable by pathname, hashes it, and returns the digest string. It does not return a descriptor or launch the checked bytes. A caller that executes the path after this helper returns can have the pathname replaced in between. The repository search found only unit-test references to `bind_producer_executable`; no E01 orchestration caller currently consumes it, so this is an integration gap rather than a reproduced live-run defect. Existing tests prove mismatch/missing-path rejection (`tests/test_e01_completion_gate.py:136-150`) but do not prove binding through exec. Recommended closure: make the E01 launch path use the sealed-fd helper (`run_bound_executable.bind_executable` / `exec_bound`) and bind its actual launch receipt to the stage record, or keep E01 explicitly NOT_RUN until that orchestration exists.

## Safeguard review and evidence

The newer publication path is materially stronger than E01's helper-only gate. `cloud_bal_transaction.py:237-335` snapshots outputs through directory descriptors, rejects symlink/hardlink/FIFO substitutions, creates detached single-link inodes with `O_EXCL`, checks source identity around copying, and fsyncs the destination. `prepare()` and `commit()` bind the owner/context, revalidate the prepared snapshot, and require the trusted semantic receipt for validation-required transactions (`:1033-1156`). The publisher swaps `current` under a root-directory flock using a checked temporary symlink and reports post-swap failures as uncertain for explicit recovery (`:1173-1245`).

Existing recovery coverage is unusually thorough: `tests/test_transaction_recovery.py` covers all observed commit fsync boundaries, pre/post-swap recovery, stale/foreign temporary links, retained writers, source-path swaps, FIFOs, tampered snapshots, required validation, and owner/inode/old-time checks. Targeted tests passed: coordinator, transaction recovery, and E01 modules (47 tests total; `TMPDIR` set under `/var/tmp`). `tests/test_intel_integration_audit.py` also passed (22 tests). These are focused tests, not a full suite or actual publication.

The detached runtime uses copied/hash-checked runtime entries and sealed executable/loader memfds; Landlock policy checks the declared input/context/runtime read roots and output write directory. The stage coordinator requires a fresh launch root (`root.mkdir(mode=0o700)` without `exist_ok` at `tools/cloud_bal_stage_coordinator.py:191-196`), detaches and rehashes inputs, validates build manifests and executable bytes (`:32-85, 182-214`), and records observed helper-source digests. The receipt explicitly limits itself to `EVIDENCE_ONLY_NO_DYNAMIC_AUTHORITY`; its hashes are caller-owned evidence and are not a substitute for E06 producer/build/compiler authority.

The stage-off validator has explicit exact-source, source/input/link, compiler trace, runtime, producer/executable, and output-role relationships (`tools/verify_stage_off_generation.py:167-303, 327-430, 460-489`). Compiler integration audit is read-only and reports build not attempted (`tools/audit_intel_integration.py:1020-1079`); its focused fixture suite rejects compiler substitution, hidden make overrides, noncanonical adapter linkage, weak receipts, symlinked scratch, and unsafe audit output. I did not execute the installed pinned Intel audit or inspect live operational binaries; no operational compiler result is claimed here.

## Classification and limits

- Reproducible defect: F1, demonstrated with a contained `/var/tmp` probe.
- Static integration risk: F2. The helper only hashes a path and has no repository caller that performs/receipts the corresponding E01 launch.
- Transaction/recovery defects: none found in this scope; focused recovery tests passed.
- E06 closure: the stage-off semantic validator contains exact source/executable/input/link/compiler/output bindings, but this audit did not establish a fresh production E06 bundle or operational publication. Publisher/test evidence is not itself an external attestation.
- Exclusions: no broad native rerun, no pinned Intel compile, no operational audit against the live upstream tree, no source mutation, and no publisher invocation.

## Graphify

Read the Graphify skill and queried the existing Cloud-BAL graph for coordinator, transaction, provenance, and audit relationships. The graph returned 1,499 nodes and located the transaction, stage-coordinator, compiler-audit, and related test nodes. I did not refresh it because the task was read-only. The checked-in graph manifest is stale relative to this PR77 working tree and only records two directly relevant tool entries (`audit_intel_integration.py` and `cloud_bal_transaction.py`); it has no manifest entries for the stage coordinator, detached runtime/Landlock, E01 gate, or stage-off validator. Treat graph results as navigation only, with these extraction/freshness limits; no graph delta was produced.
