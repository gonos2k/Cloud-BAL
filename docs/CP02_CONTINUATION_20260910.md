# CP02 continuation — 2026-09-10

Status: **IN_PROGRESS / NOT_RUN**. The user's GO continues authorized private
engineering work after the filesystem preflight increment. Whole CP02, legacy
P2/P6, FG1 and science/operational promotion remain unclosed.

## Entry and work allocation

Pre-edit source/document snapshots, graph baseline and source hashes are in
`scratch/cp02_continuation_ladkgcpz/`. Independent work covers:

1. Continue the original producer chain beyond the already retained
   wind/surface/temperature run, in a fresh privately writable runtime.
2. Test fsync ordering and process-level publication failure/recovery. A failure
   after the current-pointer swap cannot be described as an automatic rollback.

The original 12–15 UTC complete replay contract is not reduced to this 13 UTC
private continuation. External input/read closure and downstream field coverage
must be demonstrated before whole-generation acceptance.

## Retained chain identity

A newer receipt than the preparation table already records the private
wind → surface → temperature chain:
`scratch/surface_temp13_chain.Cqy7pD/chain_identity.json`.
At this session's entry the parent independently checked all 21 declared
artifact hashes. Surface build inputs/runtime matched 349/45 entries;
temperature build inputs/runtime matched 325/45 entries. These counts include
shared paths across manifests and must not be added as unique source counts.

The chain LSX SHA256 is
`1d6c546c598955a6d27efc12e5dcd534e231353f7069865d3053da9ef98dc49d`;
LT1 SHA256 is
`9dc247b9628e482edd3c098f8ba1aacca9a3e22d451563652bde95044359296c`.
LT1 retained validation is `PASS / LT1_CONTENT_ONLY`; its generation status
remains BLOCKED and promotion is false. The recorded absent PIN, previous LM2
and previous LSX remain declared limitations rather than fabricated inputs.

Independent rechecks are preserved in `retained_chain_identity.json` and
`retained_chain_build_identity.json` under the continuation evidence directory.

## Acceptance for the new increment

- Run the next producer only in fresh owned scratch, with the pinned Intel
  profile and executable/source/runtime identities; existing upstream evidence
  and protected originals remain unchanged.
- Record exact copied inputs, omitted optional inputs, status/output/time/grid
  checks, producer completion order, and source/output pre/post hashes.
- For publication, synchronize product directories before exposing a generation;
  distinguish failure before current swap from uncertain completion after it.
- Recovery must revalidate the same generation's identity, metadata, products,
  owner and expected-current contract, and reject tampered or stale generations.
- Test fsync failures, process stop and same-ID recovery without overwriting
  unrecognized temporary paths. Do not claim power-loss or network-filesystem
  durability from process-level tests.
- Preserve new-source test receipts and independent review before recording
  a scoped result. Prior PASS receipts keep their original source identity.

## Publication recovery result

**PASS_SCOPED** for local process/syscall failure handling. The previous statement
that every exception leaves current unchanged was false after pointer replacement.
The code now distinguishes three outcomes:

| CLI result | Meaning | Next action |
|---|---|---|
| 0 | Local commit/recovery completed | Use the verified generation within its declared scope |
| 2 | Request rejected or failed before this invocation replaces current; a previous invocation may already have published it | Inspect retained state; incomplete staging requires a fresh ID, while corrupt or stale generations require investigation |
| 3 | Current may already expose the generation; completion/durability uncertain | Reconcile the same ID with `recover ROOT ID`; do not assume rollback or rerun producer work blindly |

`recover` accepts only a complete renamed generation whose original directory
identity, owner, metadata and product hashes verify. It retains the expected-current
comparison and valid-time check, resynchronizes nested files/directories and rename
parents, and supports idempotent recovery. A matching orphan temporary pointer from
process termination may be reused; an unrelated target is rejected untouched.
Product directories are synchronized bottom-up before normal generation publication.
Unlock errors close the lock descriptor and retain the correct uncertain outcome
when the pointer is already visible.

Validation under the pinned Intel profile, in fresh private tmpfs scratch:

- 10 recovery cases pass, sweeping all 16 actual commit fsync call sites.
- Real fork termination immediately before pointer replacement leaves the old
  current intact; explicit recovery then publishes the verified generation.
- Corrupted products, owner/inode mismatch, stale current/time and wrong temporary
  targets reject. Same-ID successful recovery is repeatable without rewriting the manifest.
- Existing output transaction regression passes.
- Parent integration rerun on final source passes eight filesystem and twenty
  native preflight cases. Input authority rejection still precedes filesystem work.

`tests/test_transaction_recovery.py` is registered in the portable Python runner.
Implementation evidence: `scratch/cp02-recovery-20260910/run.sh` and `recovery.log`.
Parent integration evidence: `scratch/cp02_continuation_ladkgcpz/` with
`run_integration_checks.sh`, `integration_checks_final.log`, and the final independent
RED review/hash binding. Intermediate review hashes are not used for this result.

This does not establish power-loss durability, workspace Lustre support, distributed
lock correctness or exclusion of a producer retaining a writable file descriptor.
Those remain E05/E06 work, and CP02 remains IN_PROGRESS/NOT_RUN.

## Original producer continuation result

Fresh pinned ifx builds ran the original cloud, humidity and derived stages in
that order after the retained wind/surface/temperature chain. Producer pathname writes were
confined to a fresh owned tree with Landlock ABI 4 (requiring ABI >=3, including
truncate control), with an external-write rejection probe. The retained source
runtime was copied, not reused as the writable destination. This establishes
write confinement for these runs, not a complete external-read trace.

| Stage | Observed bounded result | Input/output details |
|---|---|---|
| Cloud | exit 0, four success notifications | Four new LC3/LPS/LCB/LCV products; no pre-existing file changes or deletions |
| Humidity | exit 0, LQ3/LH3/LH4 success | Three new products; only existing `lpbl/pbl_depth.lpbl` changed, recorded explicitly |
| Derived retry | exit 0, LCO marker and fourteen products including LMR | Fourteen new products; no pre-existing file changes or deletions |

The first derived attempt produced primary LCO but failed secondary LMR writing
because the private runtime lacked the LMR directory and CDL template. It was
not accepted as full producer success. First-attempt logs/receipts are retained;
only owned private outputs were cleared, the original LMR template was copied,
and derived was rerun. Final validation includes LMR and checks write-error logs.

The parent independently rehashed all 21 durable generated products against the
three stage receipts. Evidence is in `scratch/cp02_cloud_chain.qxlc8wqi/`:
`cloud_receipt.json`, `humidity_receipt.json`, `derived_receipt.json`, scripts,
build/runtime pre/post hash checks and durable product copies. The parent recheck
is `scratch/cp02_continuation_ladkgcpz/producer_product_identity.json`.

These are **BOUNDED_EXECUTION_PASS**, not complete E01 or native acceptance:
LC3 is finite in [0,1], but cloud-top LCT has only 18/66,505 unmasked cells;
CWT/ALB are fully masked. Humidity SH has 168,111/1,463,110 masked cells and
LCO COM has 1,198,264/1,463,110 masked cells. Time/shape/finiteness checks do not
supply missing coverage or certify scientific validity. Missing GPS, newer FUA,
historical LSX and other original fallback messages remain in the run records.
No synthetic observations or final/bigfile substitutions were introduced.

The complete consumed-input/read closure, all four 12–15 UTC cases, final required
field coverage and one sealed end-to-end generation remain unclosed. Native OFF
expansion still follows the documented CP06-A/integration prerequisites.

The sealed `CHAIN_CONTINUATION_RECEIPT.json` binds the three fresh builds,
source/configuration identity, per-stage receipts and retained input lineage.
Its SHA256 is `cc15fe922e7b11112bbd00ba3bcf0bf11b203a2b1c641716ae123fc33718b775`.
A durable 102-file input snapshot and all generated products/logs/scripts are
covered by `evidence.sha256`; the parent independently verified that complete
manifest. The source-to-private configuration comparison and all three build
input/runtime postchecks pass. This seals this research evidence bundle, not
the complete original-producer/native generation required for E01/E06.

### Independent producer review and replay limits

Independent `cp02_cloud_red` confirms bounded cloud execution and source/copy
identity, with promotion false. It does not grant whole cloud/humidity/derived
field coverage, E01 or CP02 acceptance. The parent verified all 179 files in the
sealed evidence manifest and the 21 generated product hashes.

The captured launch scripts intentionally record the original fixed runtime
`/tmp/c2cl.eki_bjms`; they are execution transcripts, not a reusable fresh-stage
runner. Do not rerun them against a new stage without regenerating and verifying
its exact path/input bindings. The durable input snapshot remains the retained
input evidence if the temporary runtime disappears.

Landlock confines producer pathname writes; stdout/stderr were intentionally
opened to owned evidence logs before restriction and remain writable. Thus this
is not a claim that every write, including inherited descriptors, stays under the
runtime directory. The same mechanism does not establish a consumed-input read
allowlist or retained-writer safety.

The independent review additionally found fully masked LMR `r` and LMT `llr`,
LF1 status 3, and historical LSX fallback messages. These are retained content
limitations even though the derived retry has no write errors and creates its
expected files. File creation and finite unmasked values must not be interpreted
as complete required-field coverage. This is research execution evidence only.
