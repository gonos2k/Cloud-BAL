# CP02 call-boundary KG maintenance — 2026-10-28

Graphify 0.9.53 incrementally extracted exactly two SHA-256-pinned Python files from the uncommitted source worktree overlay based at `f79bc2a190de78ac9209109766f4d0e2ddec0a2b`. The base commit does not contain that overlay. Sixteen other changed report, receipt, and data files were pinned by SHA-256 only.

| Corpus | Before | After | Delta | Snapshot |
|---|---:|---:|---:|---|
| KLAPS50 | 41388 nodes / 86004 edges | 41438 nodes / 86117 edges | +50 nodes / +113 edges / 0 removed | `2026-10-28-cp02-call-boundary` |
| Cloud-BAL | 15560 nodes / 27548 edges | 15610 nodes / 27660 edges | +50 nodes / +112 edges / 0 removed | `2026-10-28-cp02-call-boundary` |

The two graph integrity checks reported no dangling or missing endpoints, duplicate edges, self-loops, or collapsed parallel edges. All 86 preexisting KLAPS50 and 90 preexisting Cloud-BAL dated snapshots were read back unchanged.

The archived pinned Intel binary had two ordinary runs and two GDB replays. The captured analysis confirms the selected derive-column-physics boundary within this profile and input scope. The 31-test focused suite passed. No clean rebuild or new WRF forecast was run, and the first arithmetic cause is not established. The exact historical column-physics and LAPSPREP source files remain unrecovered.

Graph freshness describes structural extraction only; it does not establish runtime or scientific validation. For the compact publication receipt and path hashes, see [`kg_receipt.json`](evidence/cp02_call_boundary_20261028/kg/kg_receipt.json).
