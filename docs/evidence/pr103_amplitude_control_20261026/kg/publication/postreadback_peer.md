# PR103 KG APPLY postreadback peer review

Result: **PRESERVATION_AND_ARTIFACTS_PASS_WITH_RECEIPT_STATUS_BLOCKER**.

Reviewed plan SHA-256: `c19f490c2b1f29bba49367da42ea7a639ec3581d07e4d79f40a3271c398bf43e`.
Original APPLY receipt SHA-256: `2187059339edc437d835badcef60e9bf232839dbaed6a19f861ca32658f92d97`.
Execution stdout SHA-256: `4cd31715b10418f7a15749cda59d4af8151e406925dad52eec97645bcf528d46`.

## Verified maintained state

- All 120 pre-existing dated snapshot directories and their 472 member hashes match the reviewed plan exactly.
- The final dated inventory contains 124 directories: the preserved 120 plus the four expected raw/named targets. All four target member inventories match the receipt; full inventory SHA-256 is `7237f4d4cdd04adb53404638dd5bb44e8d7916b4059f314b66169349181ff5d3`.
- Both current graphs, both graph reports, both named snapshot triplets, and all five derived wiki files match receipt hashes. Graphify metadata inventories match the pre-apply plan for both roots.
- The maintained-source inventory matches the pinned 627-entry hash `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`; protected content and helper chain match; all 197 inherited immutable pins match and their current hashes equal expected.
- The graph extraction source remains pinned to reviewed commit `e73203b9c2f070a58aeb8488bf1e5e67a66d5f2e`. The receipt-phase fix was reviewed and committed separately as admin-only commit `abbe8b847711c94623c7e0bf47756ee0aa0b8435`; the worktree now contains the expected untracked final publication evidence directory.

## Graph deltas

- **KLAPS50:** 40983 nodes / 85369 edges / 3315 communities; delta +226 nodes, +416 edges; 236 added IDs and 10 removed IDs. Selected-source extraction reports 317 nodes / 904 edges. Receipt integrity checks report zero unverified nodes, dangling/missing endpoints, exact duplicate edges, or self-loops.
- **Cloud-BAL:** 15155 nodes / 26911 edges / 1344 communities; delta +226 nodes, +416 edges; 236 added IDs and 10 removed IDs. Selected-source extraction reports 317 nodes / 904 edges. Receipt integrity checks report zero unverified nodes, dangling/missing endpoints, exact duplicate edges, or self-loops.

## Material receipt issue

Execution stdout reports `APPLY_COMPLETE`, but the original receipt status is `PREFLIGHT_PASS_NO_WRITES`. This is a receipt-label mismatch; the maintained graph and wiki readback otherwise matches the receipt. Keep the original receipt immutable and publish a superseding administrative envelope that binds the original receipt SHA, stdout SHA, reviewed plan SHA, and this readback. No graph rebuild or maintained-root republish is needed.

Physical approval is `FAIL_OPEN` and observation skill is `NOT_EVALUATED`. Graphify extraction is selected-source with evidence payloads hash-only; Fortran cross-file CALL extraction is partial. Graph freshness does not establish runtime or scientific validation.

Only these peer-review files were written: `/var/tmp/pr103_kg_postreadback_peer_20261026.md` and `/var/tmp/pr103_kg_postreadback_peer_20261026.json`.
