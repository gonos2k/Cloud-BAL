# CP06-A producer team review — 2026-10-12

The source, real-input execution, native baseline, and independent review tasks
ran with at most four simultaneous subagents, using the requested luna/high
profile. The final reviewer inspected code directly; structural graph navigation
did not supply runtime or scientific approval.

## Findings addressed

| Finding | Resolution and validation |
|---|---|
| Real reader pressure/wind provenance differed from toy background flags | The explicit background prior accepts the actual reader's adapter/analyzed flags; manufactured and producer-generated prior authority remain rejected. Real-reader regression included. |
| Background-invalid/input-valid wind could enter the prior | Require usable original background values for every diagnostic cell. Negative regression passes. |
| Composition outside the validation shell could bypass a no-op result | Reject unsupported composition changes and full-domain flux changes outside the shell. Negative regression passes. |
| Copied omega boundaries could be mistaken for physical boundary authority | Bind exact original interior values, provenance, quality, and unchanged boundary arrays under a separate prior contract. Ordinary physical-boundary checks unchanged. |
| HYDRO writer replay could pass unallocated optional control arrays | Explicit HYDRO/prior replay branches retain their actual support arguments. |
| Full-domain flux output depended on an unrelated transport toggle | Select its named contract by the supported-analysis receipt; retain ordinary legacy behavior. |
| Geostrophic diagnostic rejected prior winds solely because no observed omega target exists | Optional fixed diagnostic wind support reports the existing residual. Default rejection and outside-support rejection remain tested; no acceptance threshold added. |
| Log parser missed secondary comma-separated stage counts | Independently hashed post-run parser correction passed the unchanged original verifier. Executed tool bytes are archived; final parser has the identical corrected function. |
| Driver could print WRITTEN after a writer failure | Final label requires both writer statuses; skipped writers start FAILED. This post-run logging-only fix compiled with Intel O0/O2 in fresh scratch. Executed driver bytes remain archived. |

## Final review scope

Source review found no unresolved concrete defect in the implemented scope.
Pinned Intel O0/O2 background-prior and geostrophic-support tests passed.
The existing endpoint writer/readback/corruption regression also passed in both
profiles after the final source change.

Final real-input artifact review is bound by the [validation receipt](evidence/pr78_validation_20261012.json).
The completed check covers identical common physics source hashes, fixed V2
masks, writer replay, nonzero candidate, readback budgets, immutable regions,
target/sigma, and stored prior residual. O0/O2 HYDRO and COUPLED files have
identical hashes. Executed driver/verifier and post-run logging/parser fixes
are explicitly different source versions. The actual NetCDF arrays remain in
private external scratch.

The flux stencil has not been independently reimplemented; observational error
and phase/trajectory assumptions, native candidate consumption, and physical
time response remain open. A scoped producer success does not promote
`FULL_SHADOW_PRODUCT`, CP06-A, FG1, or science authority.

The saved COUPLED geostrophic RMS increases from `6.53318e-4` to
`6.79215e-3 m/s²` on the same 900-cell diagnostic footprint. This is recorded
as a scientific limitation, not hidden by a new acceptance gate. The ordinary
standalone validator remains `INVALID / UNBOUND / REJECTED`; its entire
failure list is retained. Final independent team sign-off is scoped to this
producer implementation and evidence integrity.

## Independent final artifact review

The final review cross-checked all 62 entries in the private-evidence manifest,
the generated and annotated producer receipts, current common-source hashes,
archived executed driver/verifier bytes, and retained native raw-log hashes.
O0 and O2 HYDRO artifacts are byte-identical to each other, as are the O0 and
O2 COUPLED artifacts; both runs record successful diagnostic writes. The
producer receipt remains `SCOPED_PRESSURE_CANDIDATE_WRITTEN` with science
authority `NONE`. This sign-off covers scoped producer behavior and evidence
integrity only; the geostrophic increase above and the listed scientific,
independent-stencil, and native handoff gates remain open.
