# PR98 selected-source KG update

## Identity and outcome

The first guarded Graphify update completed with `PASS` for PR98 source commit [`4d0baf151cd2669437f0341307c095fa95fb92e5`](https://github.com/gonos2k/Cloud-BAL/commit/4d0baf151cd2669437f0341307c095fa95fb92e5), PR [#98](https://github.com/gonos2k/Cloud-BAL/pull/98), based on `b39da9bdb3015850b04e636ce4e247ff0df3a524`. It used Graphify 0.9.53 and wrote the separately dated `2026-10-22-pr98-native-effect` snapshots for KLAPS50 and Cloud-BAL. The applied source identity and receipt below remain the first-phase record.

The applied receipt is retained in the private scratch output, not copied into this public evidence directory. Its SHA-256 is `ce651957174ff90cf9ea104fafc9e407fa39590c6825d29ca3910ccf640eaf4d`. The first-phase applied helper was `update_kg.py` at commit `4d0baf151cd2669437f0341307c095fa95fb92e5`, SHA-256 `d3e54ce6929b9e8fa0857e2a63a2cf4c595b642f5c09173d6956e1925b9733d2` ([immutable source permalink](https://github.com/gonos2k/Cloud-BAL/blob/4d0baf151cd2669437f0341307c095fa95fb92e5/docs/evidence/pr98_native_effect_20261022/kg/update_kg.py)). The shared helper now exposes the snapshot count as a constant and has SHA-256 `92ca3f6aa630807dfde2e7fbb1559b87a1ba0d3f746e211a993be963be01d685`; this is a later helper phase and does not change the first receipt or applied source identity. The public evidence here is limited to this summary, bounded reviews, hashes, and guarded helper/driver sources.

## Separate graph results

| Corpus | Nodes before → after | Node delta | Edges before → after | Edge delta | Communities after | Removed IDs |
|---|---:|---:|---:|---:|---:|---:|
| KLAPS50 | 39,691 → 39,932 | +241 | 82,845 → 83,310 | +465 | 3,254 | 0 |
| Cloud-BAL | 13,863 → 14,104 | +241 | 24,393 → 24,857 | +464 | 1,261 | 0 |

Each corpus extracted 28 allowlisted PR98 documentation, tool, and test paths (242 extracted nodes and 644 extracted edges). Evidence payloads were hash-bound only. Existing dated snapshots were kept separate: 106 snapshots were inventoried before the update. All 197 inherited immutable pins remained verified.

Graphify reused the pre-existing automatic `2026-10-22` backup folders during application. The helper restored their hash-bound contents and mtimes after the rewrite; the two retained additions are the named PR98 snapshots above, with no extra automatic dated folders left behind.

The maintained-source inventory was unchanged across application: 627 entries, SHA-256 `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`. The receipt records private-profile preservation as unchanged and protects wiki content by hash only; aggregate SHA-256 of the protected-content hash map: `0fb9db0d66f71cd5059b6f50356ae4a094cf99ad4c61eac0c8c37d98fef24731`. No private profile or protected wiki content is reproduced here.

## Extraction limits and validation state

Cross-file Fortran `CALL` extraction is partial. Fortran embedded in Python generator strings is not extracted as standalone Fortran procedures. Graph freshness supports navigation; it does not establish runtime or scientific validity.

At first-phase receipt time the three C1 600-second baseline runs were closed, while the three C1 640-second requests were still pending. Since then, all three 640-second runs closed incomplete at 620 seconds (31 steps), return code 1; generic validation remains `FAIL`, full physical approval remains `FAIL_OPEN`, and observation skill status remains `NOT_EVALUATED`. See the [C1 boundary report](../../../PR98_C1_BOUNDARY_20261022.md) for the updated closed-run audit record. The first KG update does not change these states.

## Closed-640 follow-up driver (not applied)

The bounded follow-up driver is [update_closed_kg.py](update_closed_kg.py), SHA-256 `651c5fede18a8bf565c59b8788c6755e7491db7374eb80fbf5a04b77f822e626`. It binds the first receipt and frozen first-phase helper above, plans the separate `2026-10-22-pr98-closed640` snapshot against the current first-phase graph hashes, and expects 108 pre-existing dated snapshots. Its output remains unapplied: no closed-640 graph snapshot or second receipt has been created. The driver preserves `FAIL`, `FAIL_OPEN`, and `NOT_EVALUATED`.

## Review and helper

- [Preflight review](preflight_review.md), SHA-256 `4f7ab5e756aedf5ef1e9db9431656b8466651bf163e9b8600c7f2ba81f888b40`.
- [Restore helper peer review](restore_review.md), SHA-256 `21168e440c6365a707772c160d0ef922345a1ce86717d38497515d5fb640d79f`.
- [Post-apply review](independent_review.md), SHA-256 `36c8d97271bed6da706ecf104b4b0d9b5a1a8da35f277248bb50bb1ac5269138`.
- [Publication review](publication_review.md), SHA-256 `2987fad341edb63f4e0d195630fcc392788980f758f159a1fb42a827efead66a`.
- [Closed-640 driver peer review](closed640_driver_review.md), SHA-256 `d9052a0b9be1442c111d2f44d0173da6475296a71b080ae2ad40f45bad59c55f`.
- Current [guarded update helper](update_kg.py), SHA-256 `92ca3f6aa630807dfde2e7fbb1559b87a1ba0d3f746e211a993be963be01d685`.

`SHA256SUMS` binds the public files in this directory. The applied full receipt and graph/profile payloads remain outside this public evidence package.
