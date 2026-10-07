# PR68 Graphify/KG follow-up (2026-10-07)

PR: https://github.com/gonos2k/Cloud-BAL/pull/68

Frozen implementation: `85717dcf78eb182402b0754671ba2185f933efb4` against `920c7048bc7376347aefed7eaef3ae50ee3946a9`.

Graphify 0.9.53 processed 50 committed changed paths as selected candidate overlays. The maintained source checkout was neither copied nor replaced.

## Separate snapshots

| Corpus | Snapshot UTC | Nodes | Edges | Communities | Batch delta nodes/edges |
|---|---|---:|---:|---:|---|
| KLAPS50 | 2026-10-07T12:24:18+00:00 | 33,408 | 72,950 | 2,572 | +152 / +288 |
| Cloud-BAL | 2026-10-07T12:24:26+00:00 | 7,576 | 14,529 | 553 | +152 / +288 |

Counts are separate for overlapping corpora and must not be added as independent coverage. Each extraction produced 167 nodes/444 edges; overlay replacement and deduplication give the reported net deltas. Graph integrity checks report no dangling or duplicate edges.

## Scope and preservation

- AST and Markdown heading extraction only; no semantic refresh. Cross-file Fortran CALL extraction remains partial.
- External native WRF research trees are represented by repository patch/evidence artifacts; they were not themselves extracted.
- The persistent graphs combine prior corpus snapshots and selected overlays; this is not a full extraction of the candidate tree.
- Cloud-BAL private profile remains 134 nodes/133 incident links; KLAPS50 retains zero nodes from that private source.
- Derived corpus reports, wiki graph reports, the index Graph snapshot section and the append-only audit log were synchronized. Schema/content pages, hot.md, overview.md and earlier immutable receipts remain unchanged.
- Graph freshness supports navigation; it establishes no runtime or scientific validation.

## Dated-copy correction

Team review found that Graphify's automatic dated graph copies preceded the final cluster-only labels; the dated reports also retained earlier freshness text. Those intermediate graph/report/manifest files are preserved in the receipt-linked `dated_sync` backup. The dated copies now match all three final current files byte-for-byte in each corpus. No current graph, extraction, runtime result or scientific judgment changed.

The [initial update receipt](evidence/pr68_kg_initial_20261007.json) remains immutable; the final receipt records its hash, dated-file before/after hashes, preserved backup paths and the appended corrective audit entry. Protected wiki content preservation is supported by the update helper's in-run before/after check; the initial receipt did not persist those individual protected-content digests for independent replay.

## Remaining work

Overall physical approval remains **FAIL/OPEN**. Incoming moment admissibility, host/internal moment-unit lineage, same-call mapped water/energy closure, native dry-carrier PBL, feasible mass–wind estimation and fixed-setting native time-response/independent observation validation remain open.

The source freeze contains 24 passing focused Python tests and pinned Intel O0/O2 helper/source wiring; native research results retain their separate identities. The full unit suite remains NOT_RUN.

## Receipt

[Durable receipt](evidence/pr68_kg_followup_20261007.json) SHA256:

`f27a631771525da6a439b27e41e8f9a7042e49da16c64b3915024112dea92b89`

This metadata follow-up records the existing frozen implementation and its graph update. It adds no new physics algorithm or runtime evidence.
