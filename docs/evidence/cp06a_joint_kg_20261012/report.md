# CP06A joint-producer KG maintenance — 2026-10-12

PR #79 uses the frozen source commit 08e2ae0ef8d6ceb1b5eec1dc741f890cea15235f against base a444a788e8e7301354bec14c3708aacddb8f31d3. Graphify 0.9.53 performed a selected-path structural overlay; maintained source files were not copied or replaced.

| Corpus | Previous | Current | Delta | Dated snapshot | Integrity |
|---|---:|---:|---:|---|---|
| KLAPS50 | 34612 nodes / 74505 edges | 34840 nodes / 74876 edges | +228 / +371 | 2026-10-12-cp06a-joint | 0 dangling, 0 duplicate |
| Cloud-BAL | 8785 nodes / 16081 edges | 9013 nodes / 16449 edges | +228 / +368 | 2026-10-12-cp06a-joint | 0 dangling, 0 duplicate |

Graphify selected 101 committed changed paths; extraction recorded 611 nodes and 3,414 edges per overlapping corpus. Extraction is AST and Markdown-heading structure only, with no semantic/LLM refresh; cross-file Fortran CALL extraction is partial. KLAPS50 includes Cloud-BAL, so corpus counts overlap. Freshness supports navigation only.

Validation receipt docs/evidence/pr78_validation_20261012.json (SHA-256 f59fc45fcbcd7c42b322573cce5b729f7d7382476732159256584db4cfcc8ff2) records scoped-unit PASS, CP06A real-producer scope PASS_SCOPED, and native pair REJECTED. The native pair record says both same-executable arms abort on floating invalid before KDM6 while FTZ/DAZ are already clear; it establishes no causal FP-policy contrast. The producer result is scoped to the declared background tendency prior and does not establish native or scientific authority.

Overall physical approval remains **FAIL_OPEN**. The inherited six acceptance gates and six same-candidate integration conditions remain OPEN; this update does not promote authority.

Preservation checks passed: frozen source worktree stayed clean; all selected source hashes match; maintained selected-source files are unchanged; private profile is unchanged (Cloud-BAL 134 nodes / 133 incident links, KLAPS50 0); prior immutable receipts and automatic snapshots match their pinned hashes; graph diagnostics report zero integrity errors. The dated KLAPS50 and Cloud-BAL snapshots and derived wiki reports/index/log are hash-bound in the receipt.

Receipt SHA-256: ef087032c0e75089ca3ed6d7fdfad312e274a86a0ec934f285004d7f542e25ff.
