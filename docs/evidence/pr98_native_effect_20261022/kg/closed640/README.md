# PR98 closed-640 selected-source KG update

## Outcome and identity

The guarded second-phase Graphify update completed with receipt status `PASS` for PR98 source commit [`aea142c3df602e3ac339953507dc7f691743ddb8`](https://github.com/gonos2k/Cloud-BAL/commit/aea142c3df602e3ac339953507dc7f691743ddb8), PR [#98](https://github.com/gonos2k/Cloud-BAL/pull/98), based on first-phase source commit `4d0baf151cd2669437f0341307c095fa95fb92e5`. The applied snapshot is `2026-10-22-pr98-closed640`; Graphify version is 0.9.53.

The private applied receipt SHA-256 is `6483bca8400f8ced959f23cde9a71208e8a525284fecfae843eb7e46730f2c06`. The first-phase receipt remains unchanged and is bound as the prior receipt by SHA-256 `ce651957174ff90cf9ea104fafc9e407fa39590c6825d29ca3910ccf640eaf4d`. The original first-phase source/helper identity is still commit `4d0baf151cd2669437f0341307c095fa95fb92e5`, helper SHA-256 `d3e54ce6929b9e8fa0857e2a63a2cf4c595b642f5c09173d6956e1925b9733d2`. The current shared helper SHA-256 is `92ca3f6aa630807dfde2e7fbb1559b87a1ba0d3f746e211a993be963be01d685`; the closed-640 driver SHA-256 is `651c5fede18a8bf565c59b8788c6755e7491db7374eb80fbf5a04b77f822e626`.

## Separate graph results

| Corpus | Nodes before → after | Node delta | Edges before → after | Edge delta | Communities after | IDs added / removed | Graph SHA-256 |
|---|---:|---:|---:|---:|---:|---:|---|
| KLAPS50 | 39,932 → 39,938 | +6 | 83,310 → 83,326 | +16 | 3,259 | 12 / 6 | `983942df987a14cfbe4b78a7b51f73f092d58fb208e0b4c92278a7f73ddec2bc` |
| Cloud-BAL | 14,104 → 14,110 | +6 | 24,857 → 24,873 | +16 | 1,269 | 12 / 6 | `be2ccfd8d33823dc984bcc4621e55da45c304ae6387febce745e4c7c37be57a6` |

Four PR98 documentation, test, and tool files were extracted into each corpus; 20 selected paths were hash-bound in total, with the other 16 treated as evidence/hash-only. The 12 added and 6 removed IDs in each graph reflect re-extraction, so the net node change is six.

## Preserved state and boundaries

The pre-update inventory contained 108 dated snapshots; the update preserved their recorded hashes and added the separately named closed-640 snapshot for each corpus. All 197 inherited immutable pins passed. The maintained-source inventory remained 627 entries before and after, SHA-256 `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`. Protected wiki/private-profile records remain hash-bound only; aggregate SHA-256 of the protected-content hash map is `0fb9db0d66f71cd5059b6f50356ae4a094cf99ad4c61eac0c8c37d98fef24731`. No full receipt, graph, profile, or protected content is included here.

The three C1 640-second runs closed `INCOMPLETE`: each ended at 620 seconds (step 31 of 32), return code 1, with the required 640-second snapshot missing. Their retained first-600-second trace and history prefixes pass comparison. Generic Q/N/B validation remains `FAIL`; exact source-endpoint and active-ice checks pass; the first grouped rejection subpredicate remains open. Physical approval remains `FAIL_OPEN`, and observation skill status remains `NOT_EVALUATED`. See the [closed C1 boundary report](../../../../PR98_C1_BOUNDARY_20261022.md).

Cross-file Fortran `CALL` extraction is partial. Fortran embedded in Python generator strings is not extracted as standalone procedures. Graph freshness is navigation evidence, not runtime or scientific approval.

## Reviews and checksums

- [Check-only preflight review](preflight_review.md) (GO for apply plan only; it did not perform the apply).
- [Closed-640 driver review](../closed640_driver_review.md) (GO for the driver/configuration).
- [Independent post-apply review](independent_review.md) (GO for receipt, graph/snapshot hashes and counts, preservation, wiki outputs, and bounded publication; it does not change runtime or scientific status).
- [Final publication review](publication_review.md) (GO for the bounded public bundle and its checksums).
- `SHA256SUMS` covers this summary, all three reviews, the driver review, current helper and driver. It excludes private receipts and graph/profile payloads.
