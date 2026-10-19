# PR90 Graphify / KG maintenance — 2026-10-19

The guarded incremental update covers exactly 120 added/modified paths at source
commit `60b02162e4f94a15db1b08cbe8a6ccd0ed9f0042`, attached to
[PR #90](https://github.com/gonos2k/Cloud-BAL/pull/90). The first check-only gate
caught two hash-bound validation logs omitted by `*.log`; their exact bytes were
committed before this final freeze. The final check-only review passed, and one
apply completed. Later publication files are derived evidence, outside this
frozen source extraction; no recursive refresh is claimed.

## Separate graph snapshots

| Corpus | Snapshot UTC | Nodes (delta) | Edges (delta) | Communities |
|---|---|---:|---:|---:|
| KLAPS50 | 2026-10-19T12:23:50+00:00 | 38,810 (+488) | 81,286 (+731) | 3,173 |
| Cloud-BAL | 2026-10-19T12:23:50+00:00 | 12,982 (+488) | 22,836 (+731) | 1,188 |

The corpora overlap and are not added together. Both have distinct dated
`2026-10-19-rain-roundtrip` directories. For each corpus the merge added 493 node
IDs and removed 5; node delta is +488. Graph integrity reports zero missing or
dangling endpoint edges and zero exact duplicate edges.

## Validation and physical scope

The receipt binds the passing 95-test focused validation and pinned Intel
O0/O2 standalone evidence to the frozen source. It independently binds C7's
same-executable paired windows: 180 seconds COMPLETE (nine calls), 600 seconds
INCOMPLETE after 180 seconds, with a T10 host joint-candidate fatal. The exact
new host subpredicate remains open. Generic ice FAIL outputs remain preserved
alongside a separate source-inactive split.

`physical_approval` remains `FAIL_OPEN`. Native observation-support mapping,
water/energy closure, continuity/momentum, process justification and
initial-shock/forecast improvement remain open. Graph freshness does not
establish runtime or scientific validation.

## Preservation and extraction limits

The 627-entry maintained non-graph inventory is identical before/after. Protected
wiki content/schema and prior immutable pins are preserved; only three derived
graph reports, the index graph section and the appended audit log are refreshed.
Cloud-BAL's private profile retains 134 nodes and 133 incident links; KLAPS50's
corresponding private profile representation remains empty. Backup hashes and
rollback handling are recorded in the receipt.

Graphify 0.9.53 extracts AST structure and Markdown headings, without semantic/LLM
refresh. Cross-file Fortran CALL relationships are partial. Generated Fortran
inside Python strings is not separately Fortran-AST extracted. Sixteen unsupported
or binary selected files are hash-bound only; external runtime arrays are outside
the extraction. These limits also apply to the published report copies.

## Evidence

- [Applied receipt](evidence/pr90_rain_roundtrip_20261019/kg/kg_receipt.json)
- [Source selection and hashes](evidence/pr90_rain_roundtrip_20261019/kg/source_sync.json)
- [Frozen preflight review](evidence/pr90_rain_roundtrip_20261019/kg/frozen_review.md)
- [Independent post-apply review](evidence/pr90_rain_roundtrip_20261019/kg/postapply_review.md)
- [Derived wiki-copy hashes](evidence/pr90_rain_roundtrip_20261019/kg/wiki_copies.json)

The evidence bundle includes compressed copies of the three derived graph
reports, the index and the exact appended audit-log bytes. Full graph payloads
and native arrays are not copied into this PR.
