# PR61 team review and closure checklist

Date: 2026-10-06. Base: PR60 main
`8c7ec0a4496ea5705f5b53ff8c3a2f8691e97211`.

This work addresses common moment realizability, fixed-pressure mass
compatibility, and the native failures recorded in PR60. A research prior,
successful model exit, or finite reflectivity is not joint initialization
approval. Historical producer, model executable, and diagnostic executions
retain their original identities.

## Common numerical contracts

- [x] Check declared dry-air mass/number pairs using
  `m_min N <= r <= m_max N`, and graupel volume using
  `r/rho_max <= BG <= r/rho_min`. Bounds describe the mean particle mass;
  gamma distributions do not have bounded individual diameters.
- [x] Reject complex, nonfinite, negative, malformed, or mismatched-basis
  data. Missing physical declarations remain unsupported. Do not fill or
  clip arrays in the common validator.
- [x] Transfer dry mass and available extensive mass, number, and volume
  through the same nonnegative column-stochastic weights. Record floating
  point error separately from weight closure. Missing moments remain missing.
  This closed-domain remap is not a sedimentation or size-sorting operator.
- [x] Connect optional physical bounds to the existing MP37/native input
  validator. Native mass units must match when physical bounds are supplied.
  Syntax-valid source declarations do not authenticate scientific authority.
- [x] Reject an incompatible fixed-pressure seven-component mass increment
  before producing the first trial when no surface-pressure reconstruction
  is requested. Pressure requests defer this decision to the endpoint gate.
  Enthalpy is not included in that
  mass sum; per-component endpoint gates remain separate.
- [x] Run the focused pipeline test with the pinned Intel profile in new
  external scratch directories at O0 and O2. No full-suite result is claimed.

## Native investigation

- [x] Bind the research PSD policy, selected source, initial input, trace,
  output, and receipt before running. Preserve every field outside the
  declared moment changes and roll back new artifacts on failure.
- [x] Re-run the same one-rank 20-second model experiment and compare the
  full moment and reflectivity gates with PR60.
- [x] Trace positive initial CCN through scalar tendency, RK update,
  boundary treatment, and KDM6 entry. Distinguish a reproduced numerical
  cause from an inferred source concern.
- [x] Complete independent source/math and artifact review, resolve its
  findings, and retain the commands, hashes, and limitations in the evidence.

## Team findings resolved before PR

Independent numerical, source/math, native-execution, and artifact reviews ran
in parallel. The following concrete mistakes or omissions were corrected:

- Reject NaN/nonpositive pressure-cell mass before the early fixed-geometry
  feasibility calculation, rather than allowing a floating exception.
- Reject complex data and positive mass with zero number/volume explicitly;
  tiny products must not silently underflow into a false realizability PASS.
- Reject nonfinite extensive totals in remap accounting; avoid overflow when
  forming the roundoff scale from two individually finite totals.
- Cover initializer receipt-creation and publication failures with cleanup and
  rollback. Recheck code/input identity and independently read the exact output.
- Correct CCN stage vertical-origin parsing and validate PD capture memory
  bounds against the KDM6 capture. Register all new Python tests in the runner.
- Separate unpatched upstream startup/boundary observations from the selected
  private startup object, which carries the dry-density conversion patch.
- Correct frozen-policy labels without changing its bytes: the ice fill cutoff
  is a research cutoff and `rho_mid=400` is an unused source parameter.
- Preserve a failed mixed-interface native build. Restore the original PD
  routine interface, compile only its numerical change, and re-run with matched
  PD-only and combined controls. No retained caller is linked to an extended
  diagnostic interface in the final combined executable.
- Keep preliminary runtime hypotheses separate from measured causes. The
  reproduced rain failure has mass-limiter factor 1, concurrent accretion, and
  premature NR-to-NCCN bookkeeping. Finalized Q/N are now used in the source-copy
  patch; no number floor or output replacement is introduced.

## Validated scope and remaining native failure

- Focused Python tests: **80/80 PASS** (common moments 8, MP37 contract 22,
  native MP37 21, initializer 4, CCN parser 12, KDM6 parser 13).
- Focused pipeline: **pinned Intel O0/O2 PASS** in fresh external directories.
  Exact source hashes match the final tested code. These are focused results;
  the historical broad suite remains partial.
- Current initializer replay reproduces the prior input hash `aecc4885…`.
  Its new code-bound receipt is separate from the original experiment receipt.
- Matched one-rank/one-tile 20-second PSD-prior runs: identical KDM6 entry
  captures; first-call NN negative/zero/nonfinite counts **0/0/0**. PD-only
  reflectivity has 1 nonfinite cell; the finalized KDM6-order run has **0**
  among **2,573,532** cells. Only the selected PD and KDM6 objects use the
  pinned strict profile; retained host objects prevent full build closure.
- Full native moment gate remains **FAIL**: **49,067** positive-QC/zero-NC
  cells above qmin at return. Entry also contains **23,494** negative QC values.
  Small source-bound excursions near FP32 limits are recorded separately from
  these robust gaps. Finite reflectivity does not approve the full state.

Commands, source/log hashes, independent raw replay, and limitations are indexed
in [the team validation receipt](evidence/pr61_team_validation_20261006.json).
Native details are in [the moment report](PR61_NATIVE_MOMENT_INITIALIZATION_20261006.md)
and [the CCN report](PR61_CCN_ORIGIN_20261006.md). Neither source-copy experiment
is a COUPLED run or a 0–60 minute forecast test.

## Historical cadence metadata correction

The immutable PR60 native receipt
[`evidence/pr60_current12_kdm6_first_call.json`](evidence/pr60_current12_kdm6_first_call.json)
(SHA256 `612bc31be11c1541c720792502fbd19f620d6cfa0b0814a86fdf5b42e4cc4f35`)
still contains a mislabeled `namelist_controls.history_interval_s: 60`.
The bound baseline namelist SHA256
`a3c29306c6ae7112500e89aecf0bf41015b430c462f0243d4231bec87e899e3c`
actually declares `history_interval = 60` minutes, or 3600 seconds, and no
`history_interval_s`. The receipt's later cadence-only experiment section
correctly describes its explicit 20-second output cadence. This correction
changes no historical input, executable, output, or first-call trace and does
not relabel either native execution.

## Remaining joint/scientific gates

- [ ] Independently admitted mass/energy sources, boundary transport,
  phase-transfer freedom, observational error/correlation, and feasible trial
  search under one joint objective.
- [ ] Serialize the optional component contract and independently replay it
  with the same stored candidate. The writer remains closed to unsupported
  contracts; its checks are not weakened.
- [ ] Validate the complete native Q/N/volume/CCN state and its conservative
  transport. Reflectivity alone cannot approve this state.
- [ ] Compare BASE/HYDRO/COUPLED under identical settings through 0–60 minutes
  and subsequent forecasts, preserving observed cloud and dynamical signals.
  The conditional PSD experiment is not a COUPLED run.
- [x] Synchronize selected-source Graphify overlays and derived KG reports,
  with separately dated KLAPS50/Cloud-BAL snapshots. Graph freshness is not
  runtime or scientific validation.

## Frozen graph maintenance

Graphify 0.9.53 extracted the 25 changed paths from frozen commit
`91cac783c5dffd8ff18cc67bcdf95bdeb8ccd222` as candidate overlays; maintained
source files were not replaced. The subsequent commit only records these
results. Separate corpus snapshots are:

| Corpus | Snapshot UTC | Nodes | Edges | Communities | Batch delta nodes/edges |
| --- | --- | ---: | ---: | ---: | ---: |
| KLAPS50 | 2026-10-06 07:35:41 | 32,427 | 71,370 | 2,500 | +127 / +272 |
| Cloud-BAL | 2026-10-06 07:35:48 | 6,595 | 12,953 | 470 | +126 / +271 |

Private profile preservation (134 nodes/133 links), graph integrity, maintained
source guards, and protected wiki-content guards passed. Derived reports,
index Graph snapshot and append-only log were synchronized. Extraction used
AST and Markdown headings without semantic refresh; cross-file Fortran CALL
extraction remains partial. Graph freshness is structural navigation evidence.

The unfiltered diff whitespace check reports whitespace embedded in literal
source-copy `.patch` artifacts. Their original context and hashes are retained.
The source/document check excluding these forensic diffs passes; this scope
qualification replaces any earlier unqualified diff-clean statement.

## Follow-up audit

A further independent audit of `4ee6aaf` reproduced remap underflow-to-zero
and nonfinite diagnostic serialization failures, added a numerical-policy
drift guard, and clarified native instrumentation and graph provenance.
See [the follow-up report](PR61_FOLLOWUP_TEAM_AUDIT_20261006.md) and its
[receipt](evidence/pr61_followup_team_audit_20261006.json). The earlier
80-test receipt remains historical; the follow-up focused batch has 86 PASS.
Native full-state FAIL and scientific open gates are unchanged.
