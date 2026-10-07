# PR68 agent-team review (2026-10-07)

Base: `920c7048bc7376347aefed7eaef3ae50ee3946a9`.
Four independent assignments cover velocity/rate lifetime, rain-process origin,
carrier reconciliation and completed QC updates. Root reviews integration;
velocity/rain and carrier/QC agents cross-review each other's work.

## Findings addressed during development

| Finding | Resolution and required evidence |
|---|---|
| Rate helper initially used active bounds for the full-grid thickness array. | Preserve `ims:ime,kms:kme` thickness bounds; test distinct nonunit active bounds and halos. |
| Initial rate regression allowed 100% relative error. | Require the direct binary64 division result and test simultaneous speed/thickness unit scaling. |
| Initial carrier deltas subtracted float32 snapshots before promotion. | Promote both snapshots first; retain the old float32 subtraction effect separately from binary64 reduction differences. |
| Run-local runtime manifest described a different PR67 executable variant. | Bind the actual combined source/object/executable to the preserved variant manifest and build provenance; retain the auxiliary mismatch explicitly. |
| First rain observer draft used J/K/I array indices as global I/J/K. | Derive targets from the receipt-bound raw mask using named global bounds; require exactly the baseline 25 coordinates. |
| First rain observer source used the pre-normalization combined observer variant. | Exclude that draft; start from the normalized source `9efc0925…` used by the rejected 25-cell candidate. |
| The first rain trial formulas and event labels mixed cold and warm branches. | Reconstruct verbatim source expressions and check captured temperature; exclude initial derivatives and rerun the corrected observer. |
| Some rain checkpoints preceded completion of mass/number updates, and repeated source replacements could target the wrong branch. | Use distinct source anchors and completed boundaries; check instrumentation before compilation and require matched-run neutrality. |
| First QC observer probe preceded initialization of tendency storage. | Remove that probe; capture only initialized boundaries, then rebuild and rerun from the corrected source. |
| Whole-file QC diagnostic streams contain excluded channel data/order differences. | Compare unique keyed initialized columns and completed QC; report whole-file hash differences without rewriting old receipts. |
| Velocity refactor left a process observer reading old `work1`. | Record the named mass-rate array, preserving the observer field's s⁻¹ meaning. Rebuild and rerun the corrected source. |
| Velocity report linked an earlier helper run rather than the final patch-bound receipt. | Link the final DAzSaj receipt and preserve older attempts separately; recheck report and curated hashes. |
| An integration check during rain development used the old supported-rate test expectation. | Correct source-bound branch fixtures before the final registered runner; do not count the intermediate failed runner as PASS. |
| Rain audit initially trusted limiter metadata and declared neutrality hashes. | Reconstruct the source limiter bound and aggregate in binary32; rehash live pre/post products and reject mutated files. |
| QC inventory could accept repeated path entries despite a valid count. | Reject normalized duplicates, escapes, malformed hashes and changed live bytes; replay all 102 declared inputs. |
| Automatic dated Graphify copies preceded final clustering and retained old report text. | Preserve the intermediates and initial receipt; copy final graph/report/manifest into separate dated corpus paths and issue a new final receipt with before/after hashes and corrective audit entry. Current graph/runtime evidence is unchanged. |
| Registry host number/kg was initially assigned to internal rain-process rates. | Use selected-source volumetric number convention for internal arithmetic and retain host number/kg separately; inspected driver/wrapper pass the field directly and no density conversion was found there. Driver source/object lineage remains partial, so the runtime unit contract stays OPEN. |

## Acceptance boundaries

The existing manufactured number-wrapper assertion fails for both captured
baseline (`9efc0925…`) and the earlier refactor draft (`97e989…`) in matched
Intel O0 builds. That draft precedes the diagnostic-only observer correction;
it is not a whole-wrapper run of the final `aeda1032…` source. The failed
wrapper attempt is preserved independently of passing rate-helper tests. A native
O3 experiment produced different post-call state bytes; those differences are
quantified separately. Fresh matched Intel O2 strict builds produce identical
physical products, including identical existing 25-cell reflectivity failure
masks. This establishes scoped equivalence for that arithmetic profile.

The initial self-collection-only explanation was rejected when all-target
rate inspection showed dominant additional ice/rain collision terms. No
self-collection-only patch or number replacement was applied.

Carrier reconciliation is algebraic attribution on immutable captures. The
remaining approximately 1.91e6 kg is unclosed. PBL dry-carrier redesign, full
water/energy terms, accepted moments, joint mass–wind estimation and the
fixed-setting native time response remain separate requirements.

**Overall physical approval remains FAIL/OPEN.** Research patches are disabled
artifacts against source-bound external copies. Maintained WRF and operational
inputs are not modified. Final review and validation results are recorded below
after the matched investigations complete.

## Final validation

The independent velocity/rain review confirms the generated final observer
bytes, source branch formulas, completed checkpoints and live-product neutrality.
The carrier/QC review independently reproduces the retained audit and checks
source/object/archive/executable bindings, input inventory and source-delta
reconstruction. Review findings above are resolved for this scoped batch.

The final focused entry point `tests/run_pr68_native_contract_tests.sh` passes
21 new Python tests plus the pinned Intel O0/O2 rate helper/source wiring;
3 prior `pr67_negative_qc_replay` regressions also pass. Python compilation and
shell syntax checks pass. The [validation receipt](evidence/pr68_focused_validation_20261007.json)
binds tested file bytes and logs. The Python checks are also registered in
`tests/run_python_contract_tests.sh`; the entire unit suite was NOT_RUN.

The neutral rain observer locates all 25 failures at the cold process update:
12 accepted number trials are negative and 13 are exactly zero, while the
separately updated mass stays positive. No conservative process correction is
claimed. These checks establish the selected source path, not physical approval.

Publication and the separately dated Graphify/KG update follow the source freeze.

## Publication metadata

Implementation freeze `85717dcf78eb182402b0754671ba2185f933efb4` is published in [PR #68](https://github.com/gonos2k/Cloud-BAL/pull/68). The [KG follow-up](PR68_KG_FOLLOWUP_20261007.md) records separate graph snapshots, deltas and extraction limits. Metadata review is performed against this frozen implementation; graph freshness does not change FAIL/OPEN scientific approval.

Final metadata correction passed two independent read-only reviews: all six dated graph/report/manifest files equal final current artifacts, all six preserved intermediate files match before hashes, final wiki hashes match, and the initial receipt remains unchanged. The helper checked protected-content preservation in-run; its initial receipt lacks individual protected-content digests for independent replay, as disclosed in the KG report.
