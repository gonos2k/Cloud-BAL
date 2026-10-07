# PR66 audit Graphify/KG maintenance (2026-10-07)

Frozen code and audit evidence: `3014914c60b5bf7aba09be8a21d3369dedeb130f`.
The metadata follow-up records this maintenance result. It is excluded from the frozen code graph extraction and does not change tested source or prior execution receipts.

| Corpus | UTC snapshot | Nodes | Edges | Communities | Delta nodes/edges |
|---|---|---:|---:|---:|---|
| Cloud-BAL | 2026-10-07T07:19:33+00:00 | 7096 | 13830 | 515 | +12 / +23 |
| KLAPS50 | 2026-10-07T07:19:26+00:00 | 32928 | 72250 | 2554 | +12 / +23 |

Each corpus extracted 106 nodes/285 links from selected paths. Each resulting graph has 14 added IDs and 2 removed IDs, a net +12 nodes and +23 links. The separate overlapping corpora are not added together. Integrity checks found no dangling endpoints or duplicate links.

Graphify 0.9.53 used AST/Markdown headings and cluster-only refresh. No semantic extraction occurred; cross-file Fortran CALL edges are partial. External WRF research trees were not extracted. The private-profile graph remains 134 nodes/133 incident links in Cloud-BAL and 0 nodes in KLAPS50. This is graph-subgraph preservation, not a new file-byte or model validation.

Derived graph reports, index snapshots and the append-only KG audit were synchronized. Wiki schema/content, hot and overview pages and prior receipts were preserved. [The receipt](evidence/pr66_kg_receipt_20261007.json) binds the separately dated snapshots and hashes to the frozen code. Graph freshness is navigation evidence; full physical approval remains **FAIL/OPEN**.
