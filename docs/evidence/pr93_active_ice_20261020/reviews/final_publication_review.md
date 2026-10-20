# PR93 final publication review

**Result: PASS for publication scope; no blocking claim or evidence mismatch found.**

Reviewed the final active-ice contract, execution and closed-runtime summaries,
gzip audit ledger/reports, Q/N/B scope split, selected-call replay summary,
C4 science summaries, C18 input comparison, and the O0/O2 evidence references.
This review used published summaries and compressed audit JSON only; it did not
reread the large native traces.

## Verified claims

- Both current arms are scoped 600-second completions: 30 distinct KDM6 calls,
  COMPLETE receipts, return code 0, no collector errors or changed staged
  inputs, and requested 480/500/600-second snapshots. The same executable pin
  is used in both arms. These facts are consistent across execution summary,
  receipts, and the active document.
- The bound candidate's executable and model-input pins match the C18 input
  comparison. This establishes input identity for this comparison, not C18
  native source-prefix identity or historical cause. The document preserves
  that limit.
- `audit_publication.json` agrees byte-for-byte with both gzip files. OFF is
  32,427 compressed / 1,529,411 expanded bytes, SHA-256
  `5ec932db6d71ee27ff5c3b661cd9647684402b1ab8ffaf6e1eedb4c7c2b820ff` /
  `7179ef5bf441504afd77f4a814309b709c2a1b0e5697014b4143443dd4101814`;
  COUPLED is 32,374 / 1,525,204 bytes, SHA-256
  `9a0acb97b03395659f3d23a558fd149cbb27c46905ead575030cf821104426c9` /
  `36ce0a27884ab495c3cd644c093e54e3232fedb90965ec74baac0c9d376b52ac`. Both expanded
  reports parse as JSON, and `qnb_scope_split.json` binds to those expanded
  hashes.
- The source-derived REAL32 cloud/rain/graupel endpoint gate passes in both
  arms, while the separately defined generic Q/N/B and generic exact-bound
  gates fail. The doc explains the distinct coefficient bases and records the
  351 generic exact-outside rain events per arm as within 8 ULP; it does not
  conflate the generic-policy result with the source gate.
- The closed audit covers 180 state records per arm: 90 completed endpoints
  (RK3, KDM6 pre/post) and 90 predictor states. Active/inactive ice policy
  passes in both arms. Inactive ice beyond 8 ULP is 921/861 endpoint
  cell-state events (OFF/COUPLED); negative QV counts of 1,527/1,528 are
  predictor diagnostics and are correctly kept separate. These are repeated
  cell-state counts, not unique grid cells.
- Selected-call evidence is scoped to one captured C4 `(loop,n,mstep)=(1,1,1)`
  call per arm. The summary reports exact 39-level O0/O2 replay, and the
  document distinguishes the temporary sedimentation pair from subsequent PSD
  completion. It makes no claim that this proves the historical C18 first
  writer.
- The C4 science summary remains scoped to the actual eleven common history
  records and 613-point/16-column support. Its text explicitly leaves
  observation skill, water/energy closure, face-flux/momentum closure, and
  reduced initial adjustment open; no physics or skill approval is implied.

No publication blocker found. Preserve the current scoped language and the
explicit historical C18 attribution and scientific-approval limits.
