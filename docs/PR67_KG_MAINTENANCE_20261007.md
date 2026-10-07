# PR67 Graphify / KG maintenance (2026-10-07)

Frozen implementation source: `51ed55acf87a14f42d21b2050469b734ad6d4bcd` against `3405d25aa62f0ebecd7e1b94a3915e7c1bb2aa6e`.
PR: https://github.com/gonos2k/Cloud-BAL/pull/67. Selected committed source paths: 76.

| Corpus | UTC snapshot | Nodes | Edges | Communities | Batch delta (nodes, edges) |
|---|---|---:|---:|---:|---|
| KLAPS50 | 2026-10-07T09:15:16+00:00 | 33256 | 72662 | 2568 | +328, +412 |
| Cloud-BAL | 2026-10-07T09:15:23+00:00 | 7424 | 14241 | 549 | +328, +411 |

The maintained source files were neither copied nor replaced. This update
uses selected candidate overlays in the two separate, overlapping corpora.
Graphify 0.9.53 extracted source AST and Markdown headings, with cluster-only
refresh and no semantic/LLM extraction. Fortran cross-file CALL extraction is
partial. External WRF research trees were not extracted; only their committed
patch/evidence files entered the selected corpus. JSON, logs and unsupported
file formats do not imply scientific relation extraction.

Cloud-BAL private-profile structure remains 134 nodes / 133 incident links;
KLAPS50 has no nodes from that source. Content/schema pages, hot/overview and
prior immutable receipts remain unchanged; derived graph reports, index snapshot
and append-only audit log were synchronized.

**Physical approval remains FAIL/OPEN.** Graph freshness does not establish
runtime, conservation, scientific or operational approval. The rejected research
candidates and remaining gates retain their separate implementation receipts.

[Durable receipt](evidence/pr67_kg_receipt_20261007.json), SHA-256 `0a42d98e36a0b047db37b0981412e8626e78b91290f12a9be31ed22481992025`.

This metadata follow-up is excluded from the frozen implementation extraction.
Its commit is a publication record, not another model build or native run.
