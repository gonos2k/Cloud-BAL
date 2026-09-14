# CP02 preparation record — 2026-09-09

Current state (2026-09-10): **CP02 IN_PROGRESS / NOT_RUN**. The user requested
the next stage after CP01 completed. CP01's six original bounded contract and
small-test criteria are COMPLETE/PASS; see [the final audit](CP01_COMPLETION_AUDIT_20260909.md).
The earlier preparation evidence below is retained. This is authorized private
upstream, build and transaction preparation, not whole-CP02 completion or an
operational publication receipt.

| Criterion | Current bounded evidence | Remaining work |
|---|---|---|
| E01 original producers | Retained wind→surface→temperature plus fresh cloud→humidity→derived at 13 UTC; sealed `scratch/cp02_cloud_chain.qxlc8wqi/CHAIN_CONTINUATION_RECEIPT.json` | Seal one correctly ordered wind→surface→temperature→cloud→humidity→derived chain with declared optional-input policy, source/runtime identity and complete input/output coverage |
| E02 full pinned build/ABI | Retained wind/surface/temperature and fresh pinned cloud/humidity/derived build receipts; qf63eH LAPSPREP identity | Bind all remaining producers and the complete derived→balance→LAPSPREP ABI/source closure |
| E03 OFF reproduction | Actual candidate and fresh shadow-OFF use qf63eH executable `6639c078…d5d37e`; fresh OFF WPS equals retained OFF bytes. OFF native products exist in `metgrid13_fresh_off.tEo3hs` / `real13_fresh_off.pYpsN8` | Finish the transitive OFF WPS/native input/config/binary identity review and all required comparison coverage; do not replace newer same-build evidence with the old false receipt flag |
| E05 transaction | Local filesystem preflight and process-level fsync/recovery tests pass on private tmpfs; workspace Lustre rejects unsupported no-replace | Complete durable-filesystem/crash, real mount boundary, distributed-lock and retained-writer/producer-lifecycle evidence. Supported tmpfs syscall tests do not establish operational durability |
| E06 provenance | Several individual source/build/run/validation receipts | Bind the ordered generation, producer seal, writer lifetime and validation into one auditable generation record |

## Surface generation

The original surface producer was built in fresh pinned Intel scratch
`upstream_surface_build.aKzpFQ`; executable SHA256:
`0716238d580d5258d190e8d13ddc5b37b3ba73e77ff155fb1e0e664d5b465ff5`.
The first private attempt read 816 LSO observations but failed closed because
`ncgen` was absent from PATH. No LSX was generated and all 120 pre-existing
private files remained unchanged.

The retry explicitly used existing pinned ncgen SHA256
`b83acc5e06621d9e15c3e92b7c1592ca6fcf5d62593c95d8f87fa76cbcfb549e`.
It exited 0 and wrote LSX with `istatus=1`. The durable output SHA256 is
`1b41c3a7c1fcb073d93d00ce0278c1bf229d5930e495a522a7846ea6acc6684b`
(parent rechecked), 6,668,716 bytes. All 25 required variables are present;
mandatory fields are finite/unmasked across 66,505 cells. Reference and valid
time are both 13 UTC. Optional PP/TH/HI remain explicitly masked. Complete
pre/post manifests prove 120 existing files unchanged and exactly one new LSX.
See `scratch/surface13_private_run.MMifd4/retry_receipt.final.txt`,
`source_pre_post_identity.retry.json`, and `lsx_validation.retry.json`.

This isolated surface input tree lacked current LWM and previous LM2; source
warnings/fallbacks are retained. A subsequent ordered chain must explicitly
propagate the freshly generated source-bound wind products before regenerating
surface and temperature. The isolated LSX is not claimed as that complete chain.

## Publication backend evidence

`scratch/cp02_e05_transaction_snapshot.XAE0NT/cp02_e05_receipt.md` records exact
source/test hashes and actual tmpfs/Lustre runs. The supported private tmpfs run
passes CAS/stale-current rejection, no-replace collision, current switching and
four coordinator failure boundaries. The Lustre run exits at atomic no-replace
generation rename. This proves refusal of an unsupported backend; it is neither
a successful Lustre capability test nor permission to use volatile tmpfs for
operational publication. No real current or operational tree was changed.

## CP02 entry — 2026-09-10

The user confirmed CP01 and requested "다음 단계 진행". The first bounded
implementation covers E05 filesystem capability preflight in owned scratch.
The roadmap permits this early CP02 scope before CP06-A; complete metgrid/real
expansion still follows CP06-A, while CP03/04/05 pressure-level work may proceed
under their specific analysis contracts.

Before implementation, all 10 files in the final CP01 source manifest matched
the retained hashes. Entry evidence and pre-edit snapshots are preserved in
`scratch/cp02_entry_h9hmfhmt/`. Subsequent CP02 changes are new source identities;
the prior CP01 PASS is retained at its original snapshot, not copied onto new
source hashes. The checkpoint TSV and wiki hot/overview now reflect the CP01
exit and CP02 entry.

Acceptance for this bounded increment:

- Probe only disposable descendants of an explicitly selected private root.
- Exercise existing no-replace rename, file/directory fsync, local lock exclusion,
  current replacement and stale-current rejection primitives.
- Reject unsupported capabilities and preserve existing root contents/current.
- Reject malformed or unauthoritative native inputs before filesystem probing.
- Integrate the probe before constructed diagnostic publication, without native
  launch or physical startup authority.
- Record actual supported and workspace-filesystem results plus independent
  review. Local syscall success does not certify power-loss durability or
  distributed locking; tmpfs is not an operational publication recommendation.

The full E05 filesystem, fsync-order/crash, recovery, mount and writer lifecycle
requirements remain separate. No whole CP02, legacy P2/P6 or science gate is
closed by this increment.

### Filesystem implementation and test evidence

`tools/cloud_bal_transaction.py preflight ROOT` now probes an existing private
root in a disposable child, using the actual transaction primitives. Existing
layout directories must be non-symlink directories on the root device. The probe
checks local lock exclusion, no-replace collision preservation, generation
rename, file/directory fsync, stale-current rejection and current replacement.
`run_native_preflight` calls it only after input/authority validation and before
its constructed diagnostic transaction. Actual NO_AUTHORITY rejection still
precedes filesystem work; no native producer or launcher is added.

The new `tests/test_publication_filesystem.py` is registered in the portable
Python runner. Under the sourced `tests/intel_toolchain.sh` profile, in fresh
private tmpfs scratch:

- 8 filesystem cases pass, including unsupported rename, fsync failure, ineffective
  locks, overwrite fallback, unsafe roots and symlink/cross-device layout rejection.
- 20 native input/preflight cases pass, including rejection before diagnostic
  transaction and a constructed diagnostic publication carrying the probe receipt.
- The unchanged output transaction regression passes.

Real CLI probes return 2 on workspace Lustre (atomic no-replace unsupported) and
0 on private tmpfs. Both preserve existing sentinel bytes, the current symlink
inode/target, and leave no probe child. This demonstrates safe early refusal on
Lustre, not Lustre publication success. Same-device bind mounts, crash persistence
and multi-host locking remain unverified.

Evidence copied without alteration to
`scratch/cp02_entry_h9hmfhmt/implementation_evidence/`: `filesystem_receipt.json`,
`filesystem-tests.log`, `native-tests.log`, `transaction-tests.log`.
`tested_source_identity.json` in the parent directory independently confirms all
seven implementation/test/runner/profile hashes match the executed evidence.
The original copy remains at `../scratch/cp02_filesystem_preflight.vJWpKi/`.

Independent RED review passed this bounded increment after running the eight
filesystem tests and checking source/integration/evidence. Parent GREEN review
confirmed exact tested hashes and preserved authority/ledger boundaries. Reviews
are retained as `scratch/cp02_entry_h9hmfhmt/{red_review,green_review}.md`.

Next CP02 work is the ordered original producer/input-provenance chain and
fsync-order/recovery/writer-lifetime cases. Full native OFF expansion retains
its CP06-A prerequisite; CP02 remains IN_PROGRESS/NOT_RUN.

## Continuation after GO — 2026-09-10

The [continuation record](CP02_CONTINUATION_20260910.md) corrects the earlier
preparation table's missing retained wind/surface/temperature chain and follows
new cloud-stage work plus publication fsync/recovery verification. These scoped
results do not close the complete producer or CP02 gate.
