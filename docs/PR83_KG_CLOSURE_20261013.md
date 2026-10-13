# PR83 structural KG closure

Graphify 0.9.53 updated the 37 selected paths in frozen source commit `a38b649bf28bd08e4435a471def43124c5445b6d`, then `kg-update` synchronized the derived reports, index and audit log. This evidence-only follow-up does not change the code or runtime evidence bound to that source batch.

| Corpus | Dated snapshot | Nodes | Edges | Change |
| --- | --- | ---: | ---: | --- |
| KLAPS50 | `2026-10-13-moment-initialization` | 35,803 | 76,398 | +429 nodes, +619 edges |
| Cloud-BAL | `2026-10-13-moment-initialization` | 9,975 | 17,968 | +429 nodes, +619 edges |

These corpora overlap; their counts are not summed. Extraction uses AST structure and Markdown headings, without semantic/LLM refresh. Cross-file Fortran CALL coverage is partial, and external WRF sources and large runtime artifacts are not represented. The ZIP and source-bound patch are hash-recorded rather than parsed. Graph freshness establishes navigation provenance, not execution or scientific validation.

Both graph integrity checks report no dangling endpoints or exact duplicate edges. The maintained 627-entry source inventory is unchanged, as are protected semantic wiki content, the private profile subgraph and preceding immutable receipts/snapshots. The old PR82 receipt remains linked by its original hash.

The new receipt explicitly records `new_moment_initialized_candidate=NOT_CREATED`, native launch `NOT_RUN`, source PSD/cap rejection, scoped mass-only OFF/coupled startup I/O, and open physical/scientific gates. [Receipt alias](evidence/pr83_kg_20261013.json) and [compact archive manifest](evidence/pr83_kg_20261013/manifest.json) preserve the exact graph and validation bindings. Full graphs remain separately dated in the maintained workspace.
