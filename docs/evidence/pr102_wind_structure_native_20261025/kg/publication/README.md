# PR102 selected Graphify / kg-update publication

The source freeze is `394b2fb02726978ab8e12080afd80c9171f50762` on [PR102](https://github.com/gonos2k/Cloud-BAL/pull/102). The approval base is PR101 `1e2c45eb...`; the separate graph selection base is `2345bc1d...`. This publication changes bounded evidence only after the selected extraction.

| Corpus | Nodes | Edges | Node delta | Edge delta |
|---|---:|---:|---:|---:|
| KLAPS50 | 40,757 | 84,953 | +240 | +555 |
| Cloud-BAL | 14,929 | 26,495 | +240 | +553 |

Each corpus preserves both the automatic raw snapshot `2026-10-26` and separately named `2026-10-25-pr102-wind-structure`. The dated-folder inventory is 120, including all 116 prior folders. The source inventory remains 627 entries at SHA256 `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`; 197 inherited pins and protected wiki/content/schema/profile state remain unchanged. Derived graph reports, the wiki graph snapshot/index and audit log carry the source freeze, runtime gate scopes and open science items.

The exact 25 selected source/test/documentation paths were extracted. Evidence payloads are hash-bound only. Cross-file Fortran CALL extraction remains partial, and Fortran embedded in generator strings is not extracted as standalone procedures. Graph freshness is navigation evidence; it is not runtime or scientific validation.

The first apply failed in postprocessing because of an unnecessary undefined `SimpleNamespace` wrapper. Automatic rollback was independently verified against graph/wiki/snapshot/source/protected hashes. Its full engine output was preserved outside this repository; bounded rollback and disposition records are in the parent directory. A one-line fix passes the existing engine directly, 13 guard tests passed, and a new source commit, manifest, check-only plan, independent review and root GO preceded the successful second apply. Both attempts are retained separately here.

The four runtime gates are COMPLETE within their declared scopes. Generic Q/N/B FAIL173 is preserved separately from exact source endpoint PASS and active-ice policy PASS. Physical approval remains **FAIL_OPEN** and observation skill **NOT_EVALUATED**. No model/input change or forecast rerun accompanied KG maintenance.
