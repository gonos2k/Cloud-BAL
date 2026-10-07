# PR65 Graphify/KG maintenance (2026-10-07)

Frozen implementation: `3a6656fe184b4d25facbb24e93bcda3637c92bf1`.
The follow-up metadata commit adds this report and publication state; it does not change the reviewed numerical tools or native research artifacts.

| Corpus | UTC snapshot | Nodes | Edges | Communities | Node/edge delta |
|---|---|---:|---:|---:|---|
| Cloud-BAL | 2026-10-07T06:41:44+00:00 | 7084 | 13807 | 513 | +169 / +305 |
| KLAPS50 | 2026-10-07T06:41:37+00:00 | 32916 | 72227 | 2546 | +169 / +306 |

The selected-path overlays use Graphify 0.9.53 AST/Markdown heading extraction and cluster-only refresh. The two overlapping corpora are tracked separately; their counts are not combined. Fortran cross-file CALL extraction is partial. External WRF research copies were not extracted. The Cloud-BAL private profile retains 134 nodes and 133 incident links; the KLAPS50 graph has no nodes for that configuration file.

Derived graph reports, wiki index snapshot and append-only audit log were synchronized. Wiki content, schema, hot and overview pages were preserved. Prior receipts and execution evidence remain unchanged.

[The maintenance receipt](evidence/pr65_kg_receipt_20261007.json) records graph/wiki hashes, deltas, selected paths and extraction limits. Graph freshness does not establish runtime or scientific validation. Full physical approval remains **FAIL/OPEN**.
