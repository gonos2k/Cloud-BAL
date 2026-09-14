# CP02 review remediation — 2026-09-10

Status: **IN_PROGRESS / NOT_RUN** for whole CP02. This increment addresses the
GREEN/RED inspection in `scratch/cp02_green_red_5p3gm9zx/GREEN_RED_REVIEW.md`.
It does not promote the retained 13 UTC producer run to complete provenance,
scientific acceptance, or operational publication.

## Scope and evidence correction

The confirmed publication defect is deletion of an unrecognized temporary path
after a pre-swap rejection. The required behavior is to preserve that path and
the old current generation, retaining evidence for explicit recovery.

The executable finding needs a factual correction: the three retained build
logs **already contain build-time executable SHA256 values**. The earlier
review's statement that hashes were recorded only after execution was too broad.
The parent verified that all three build-log hashes match both the current
executables and the sealed receipt. The missing guarantee is enforcement of the
expected bytes at launch, including replacement between verification and exec.
See `scratch/cp02_remediation_sijjh7kb/build_hash_correction.json`.

Historical producer scripts and the 179-file evidence seal remain unchanged.
New launch controls cannot retrospectively bind a past process to an executable.

## Content and input-bundle qualifications

The independent GREEN audit verified all 21 fresh product hashes, clocks,
dimensions, and navigation fields. The inherited PBL product has fill-valued
navigation metadata despite matching clock/dimensions; its complete grid
metadata remains unverified.

Default NetCDF reader masks are not synonymous with missing input. They also
include values rejected by a variable's `valid_range`. For example, inherited
LT1 `t3` has finite raw values approximately 199.08–308.13 but declared range
0–100, so the default reader masks every cell. LMR `r`, LMT `llr`, and much of
LH3 similarly contain non-fill values outside their declared ranges. These
observations require reconciliation of units, raw values, and metadata before
coverage/science acceptance. This increment does not change physical fields or
relax those checks.

The retry's `lmr.cdl` hash is recorded and matches its source, but the template
bytes are outside the retained 179-file seal. A future complete bundle must
include those bytes along with all consumed input/configuration evidence.

## Publication change

`OutputTransaction._publish()` retains temporary paths after a failed pre-swap
attempt. It no longer attempts pathname cleanup, even after an identity check:
another actor could replace the path between that check and `unlink()`.
Successful publication still consumes the temporary pointer through the
current-pointer rename. Explicit `recover ROOT ID` can reuse a matching orphan;
foreign regular files and unrelated symlinks are rejected and retained.

New regular-file and symlink preservation checks fail against the pre-edit
implementation and pass against the fixed implementation. The existing
transaction suite also checks recovery after an ordinary pre-swap exception.

## Verified executable launch

`tools/run_bound_executable.py` copies an opened regular ELF into a Linux memfd,
seals it against writes/resizing, hashes the sealed destination, compares the
expected SHA256, and executes that same descriptor. Hashing only the input while
copying would be insufficient: a mutation of the destination before sealing
must also be detected. Missing files, symlinks, invalid hashes, and failed
binding/sealing reject without falling back to pathname execution.

Fresh `tools/build_upstream_producer.sh` builds produce `executable.sha256` and
`run_verified.sh`. The launcher checks the build input/runtime manifests before
calling the binding helper. Use it in place of the raw producer executable
inside the existing private, confined invocation. Preserve the pinned Intel
environment, working directory, timeout, and per-attempt output validation.
For a separately pinned digest, the direct form is:

```bash
python3 tools/run_bound_executable.py --expected-sha256 "$expected_sha256" "$executable" -- "$@"
```

This command is a launch-binding primitive, not an isolated producer workflow.
The expected digest, launcher, Python interpreter, and controlling process are
trusted. The main ELF binding does not seal the dynamic loader, libraries,
helper commands, environment, or consumed inputs. Dynamic lookup that depends
on the original executable path (such as `$ORIGIN`) needs separate validation.
The helper supplies the executable basename as `argv[0]` and forwards the
remaining arguments; programs depending on the original `argv[0]` path also
need separate validation.
Existing Landlock pathname-write restrictions must still surround execution;
inherited descriptors and external reads retain their stated limits.
The `BOUND_EXECUTABLE_READY` stderr marker means verified bytes are ready for
exec, not that exec or the producer completed. Binding/exec rejection prints
`BOUND_EXECUTABLE_REJECTED` and returns 2. A successful exec retains the
producer's own exit status; output and completion checks remain necessary.

## Validation record

The pre-edit snapshot is `scratch/cp02_remediation_sijjh7kb/before/`.
Final independent RED verdict: **PASS_SCOPED** for the temporary-path no-loss
fix and main-ELF launch binding. The exact-source review is
`scratch/cp02_remediation_sijjh7kb/RED_REMEDIATION_REVIEW.md`; the consolidated
hash-bound record is `scratch/cp02_remediation_sijjh7kb/receipt.json`.

- New foreign-temporary preservation tests: pre-edit implementation fails both
  replacement variants; final implementation passes.
- Recovery: 11 tests, including all 16 commit fsync boundaries, pass. Existing
  transaction regression and ordinary exception/orphan recovery pass.
- Parent integration: filesystem 8 tests and native contract 20 tests pass.
- Bound executable: six focused test groups pass, including tampering before
  sealing and pathname replacement after binding.
- Final-source Intel/Landlock smoke: a fresh pinned-ifx dynamic ELF executes via
  the sealed memfd under Landlock ABI 4, writes inside its private runtime,
  rejects opening the protected external file for writing, and preserves its
  hash. This manufactured fixture verifies launcher compatibility, not a real
  producer/science case.
- Historical evidence seal: 179/179 hashes still match. No past producer run is
  rerun or relabeled by this increment.

Evidence is under `scratch/cp02_remediation_sijjh7kb/`: transaction before/after
results in `transaction_fix/`, parent integration in `parent_checks.log`, and
the final helper checks in `final_bound_checks.log` (pinned profile, fresh
scratch, bytecode cache outside the source tree). The final dynamic-ELF check
is in `ifx_smoke.log` with source/compiler hashes in
`ifx_smoke_sources.sha256`. The first smoke attempt is preserved separately;
the final one uses runner SHA256
`0f48ae20bd0c5bc8e07f6b6edf74b69af859a4012666bd10372ccf00c07524cd`.

The structural graph was refreshed without semantic document extraction:
3,984 nodes, 8,344 edges, 263 communities. Graphify's omission of unchanged
host-profile JSON nodes was corrected from the exact verified baseline before
reclustering, without force. Final endpoint, duplicate, loop, and edge-collapse
diagnostics are zero. The parent KLAPS50 graph remains its earlier snapshot.
Graph records are in `graph_update/`; graph results are navigation evidence,
not runtime or scientific acceptance.

The new executable tests are registered in `tests/run_python_contract_tests.sh`.
Full producer rerun with the new launch control, complete input/read closure,
metadata/field coverage, all 12–15 UTC cases, and native/science/publication
acceptance remain open. Whole CP02 stays **IN_PROGRESS / NOT_RUN**.
