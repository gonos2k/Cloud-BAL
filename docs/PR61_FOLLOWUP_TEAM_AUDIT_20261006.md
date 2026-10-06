# PR61 follow-up team audit — 2026-10-06

Reviewed base: `4ee6aaf84fe80369c4a95355b458a291346bf0cd`.
Four independent agents reviewed common numerical contracts, Fortran gates,
initializer/parser failure paths, and native source/execution evidence. Source
and exact artifacts were authoritative; Graphify supplied navigation only.

## Findings and fixes

| Finding | Disposition |
| --- | --- |
| Positive carrier × ratio underflow produced zero mass/number and a false conservation PASS | Reject vanished positive source products, weighted terms and intensive recovery; no floor or artificial source |
| Stage NaN/Inf and FP32 extreme subtraction broke strict JSON reports | Compare finite pairs in binary64; record unsupported pairs and null full-field maximum; count nonfinite PD residuals; handle encoding errors |
| Frozen policy-file identity did not detect numerical declaration drift | Check exact inventory and declared parameters/bounds; use 16 binary64 eps only for derived pidn relations; frozen policy bytes retained |
| Matched native paragraph implied a patch-only KDM6 executable | Explicitly distinguish pure PD from the compiled, instrumented KDM6 extension; run hashes and results retained |
| Graph report base-commit text obscured selected-overlay provenance | Clarify maintained checkout base versus selected source extraction in derived reports; re-query maintained graph after stale bundled navigation |

The policy check guards numerical declarations. It does not authenticate an
arbitrary altered Python process or establish complete executable closure.
Remap guards detect products or recovery rounded to zero; representable
subnormal values remain subject to the existing numerical checks.

## Validation

- **86 focused Python checks PASS**, including regressions for the three new
  boundary conditions and existing MP37/KDM6 integration contracts.
- Real NE57 initialization replay under the revised initializer preserves
  original inputs, mass and other fields, and produces the same native input
  hash `aecc4885da1d612e57ec8c603b6c85df6a89e3c53cda5a4a302ec65d33866739`.
  Its new code-bound receipt is separate from historical experiments.
- Revised and base CCN parsers give identical summaries on retained finite
  RK/PD native captures. No native model was rerun or attributed to new code.
- Fortran source, tests and toolchain bytes are unchanged. Previous focused
  pinned Intel O0/O2 evidence remains scoped to those bytes; no new full-suite
  claim is made.
- The remap and IO fixes received independent cross-review. No remaining
  scoped implementation blocker was found.

Exact source, log and artifact hashes are indexed in
[the follow-up receipt](evidence/pr61_followup_team_audit_20261006.json).
Original PR61 receipts retain their historical hashes; their relative source
references describe bytes at the reviewed base, rather than edited follow-up
files. The scientific disposition is unchanged: **49,067 positive-QC/zero-NC
cells remain at KDM6 return**, and complete native moment acceptance is FAIL.
Joint trial generation, contract serialization, full host/parallel closure and
BASE/HYDRO/COUPLED 0–60 minute/forecast validation remain open.

## Graph maintenance

Selected-path Graphify/KG maintenance is performed after freezing this batch.
It preserves maintained source files, the 134-node/133-link private profile,
protected wiki content and prior receipts. Separate corpus dates/deltas and the
new receipt are recorded in the reporting-only follow-up. AST and Markdown
heading extraction, partial Fortran cross-file CALL edges and overlay scope
do not establish runtime or scientific validity.

### Recorded graph result

Graphify 0.9.53 refreshed 11 selected paths at frozen source commit
`a69176f6c303025bff80f688a9e3b99fe6af5e2f` against the previous overlay.
The next commit only records these outcomes.

| Corpus | Snapshot UTC | Nodes | Edges | Communities | Delta nodes/edges |
| --- | --- | ---: | ---: | ---: | ---: |
| KLAPS50 | 2026-10-06 07:52:08 | 32,449 | 71,411 | 2,504 | +22 / +41 |
| Cloud-BAL | 2026-10-06 07:52:14 | 6,617 | 12,994 | 475 | +22 / +41 |

Integrity, unchanged maintained source, private profile (134/133), and protected
wiki-content guards passed. Derived graph reports now state selected-overlay
provenance; their wiki mirrors match. The index snapshot and audit log are
synchronized. The previous KG receipt is preserved. Structural extraction
limitations and all native/scientific open gates remain unchanged.
