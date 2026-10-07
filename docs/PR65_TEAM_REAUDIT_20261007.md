# PR65 independent team reaudit (2026-10-07)

Reviewed PR65 head `8ed9f84862d55f5838ddc8554f26949bead94bef`, then confirmed that
main merge `0be11ca80211232eb3dc025aa95801e989841f53` has the identical tree.
Four focused reviews covered numerical equations/native patches, capture and
budget validators, preflight execution, and evidence/test/KG claims. Fixes
were cross-reviewed before this follow-up was frozen.

## Findings and corrections

| Finding | Correction | Verification |
|---|---|---|
| Preflight checked only the executable status from a `tee` pipeline and omitted stderr from its log | Capture both pipeline statuses immediately; preserve the child exit when logging succeeds and return 125 when logging fails. Include stderr in the logged stream. | Exercise the exact runner helper with child exit 7 and injected `tee` exit 23. Register this required shell test after the portable Python tests. |
| Receipt validators followed symlinked executable, capture, manifest or output paths | Require regular non-symlink files using `lstat` before resolving or hashing the paths; geometry outputs must also declare one link, matching the live file. | Symlink mutations are rejected; regular retained captures still pass. |
| Existing CI documentation described an active hosted workflow absent from the current checkout | Identify the local runner and its registered tests; state that no tracked workflow establishes a hosted result. | Compare the document with the runner and tracked workflow inventory. |

No additional mathematical defect was confirmed in the NC donor reconstruction
or the selected PBL solver replay. Native patch indexing, reciprocal/multiply
order, operand-based tolerances, units, and once-only tendency accumulation
match the recorded scope. The donor replay's normal IEEE binary32 error model
is not a proof for arbitrary subnormal/FTZ arithmetic. The observed donor case
showed no mismatch; the native PBL rate replay separately models its FTZ path.

Two reviewers initially navigated the stale isolated 1,499-node graph. They
corrected their queries to the maintained Cloud-BAL graph with 7,084 nodes.
Source and artifacts were authoritative throughout; graph navigation does not
establish runtime or scientific validity.

## Validation and provenance

- [Focused validation receipt](evidence/pr66_team_reaudit_validation_20261007.json):
  53 Python tests, exact-helper shell failure injection, and Bash syntax checks
  passed. Source hashes matched before and after execution.
- [Retained-capture readback](evidence/pr66_actual_readback_reaudit_20261007.json):
  modified validators accept the guarded donor-control and shared-NC research
  artifacts. Budget and domain numerical/replay fields match PR65 evidence except the
  expected validator source identities. Prior `provenance` and `source_inspection`
  annotations are kept in the original PR65 receipt; they are not readback outputs.
- [Initial comparison](evidence/pr66_actual_readback_initial_comparison_20261007.json)
  remains FAIL because the initial comparator included the updated geometry
  validator's source hash in its equality check. The scratch receipt and output
  files are preserved. The follow-up comparison checks numerical fields and
  records source identity separately; it does not relabel the initial attempt.
- PR65 source-bound execution receipts, replay evidence, native captures and
  original failed attempts are unchanged. The new runner was tested through
  its shell helper; the full actual-input preflight was not rebuilt or rerun.
  No Fortran compiler or native model was executed in this audit.

This closes the verified validation/runner mistakes. Full physical approval
remains **FAIL/OPEN**: entry moment gaps and negative QC, complete same-call
water/energy terms, an independently admitted joint candidate, and fixed-setting
BASE/HYDRO/COUPLED time-response/observation validation are still required.
The [PR65 physical checklist](PR65_CLOSURE_CHECKLIST_20261007.md) retains these
scientific gates; this follow-up supplies implementation audit evidence only.
