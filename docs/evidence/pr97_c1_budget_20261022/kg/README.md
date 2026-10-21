# PR97 bounded Graphify/KG publication

The guarded selected-source Graphify update passed for frozen source commit
`876fbbd961e03a0cde90e4cbb8128d145cc714d7`, base
`72bab3a89ec3b74b552646cf44386cb7a3950672`, PR #97. The bounded
[`summary.json`](summary.json) records separate KLAPS50 and Cloud-BAL
snapshots, actual graph counts and deltas, selected source hashes, source and
receipt identities, preservation checks, and scoped runtime/science status.

The update selected 15 files in total: PR97 docs/tools/tests, the two PR96
terminology documents, and the PR94 hydro response tool/test pair. The other 36 changed paths, including evidence payloads, were SHA-256
bound only. The update preserved the 627-entry maintained-source inventory,
197 inherited immutable pins, 102 prior dated snapshots, protected wiki
content, and private profiles. The named PR97 snapshots are dated
`2026-10-22-pr97-c1-budget`. Graphify also retained two automatic, separate
`graphify-out/2026-10-22/` five-file archives during `cluster-only`; the
summary records their member hashes. Their reports and Graphify sidecars match
pre-apply backups; their graph and manifest are intermediate merged pre-cluster
state, distinct from the final named snapshots. The original 102 dated
directories were preserved. Graph JSON payloads, private profiles, and backup contents are
excluded from this public bundle.

The three C1 600-second arms are complete at 30 steps and return code 0.
Their source endpoint and active-ice checks pass; the generic Q/N/B audit
remains FAIL, and the closed audit queue remains REVIEW_REQUIRED. The T1
liquid-store terms are accounted for, but residuals of roughly −66,060 kg per
arm remain open. The separate C4 620-second classifier review is GO while the
grouped rejection cause remains open. No new C1 run beyond 600 seconds was
performed. Physical approval remains FAIL_OPEN.

Graph extraction of Fortran has partial cross-file CALL coverage. The dated
graph snapshots record source navigation only; they do not establish runtime
or scientific validation. The exact independent post-apply review is included as
[`independent_review.md`](independent_review.md); it passed with no preservation
blockers and documents the Graphify automatic archives. `SHA256SUMS` covers
the summary, this README, and the independent review.
