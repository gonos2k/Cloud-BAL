# PR73 physical closure checklist — 2026-10-08

Base: merged PR72 `e9a0e38a8ada142426a0b645f1598265611cf9d4`, merged at 12:57:52 KST. Historical open/unmerged receipts remain intact. Overall physical approval remains **FAIL/OPEN**.

## Scoped closures retained

PR72 fixes the PR71 ice-branch nesting regression and the separate rain/ice zero-number velocity overwrite. The earlier inherited-defect interpretation is withdrawn. The same EOS fixture on PR70 and repaired source still rejects a different infeasible trial; it is not a successful full-process fixture. PR71 property-output definitions and signed pre-NINT guard remain unchanged. The fraction is a conservative valid fraction, not a global float32 maximum.

## Ordered work

| Priority | Item | Exit condition | Status |
|---|---|---|---|
| P1 | First species violation result | Actual species, stored values and units, call stage, array bounds and coordinate origin; actual native first failure separate from manufactured format check. | PASS_SCOPED: actual native first violation identified; see first-violation report and attempt-2 completion audit. |
| P1 | Presence combinations and property history | Four paired categories, 16 physically supported combinations; poisoned outputs and active→absent transitions; paired-positive admission separate from PSD approval. | PASS_SCOPED: actual initial property stage, 16 references + 16 history reentries per Intel profile. No n0/full-process claim. |
| P1 | Upstream state creation | Compare staged input and first-call capture, then identify first completed producer boundary; no invented floor or mass deletion. | PARTIAL: staged QICE/QNICE=0; first-call QI>0, NI=0. First producer boundary remains OPEN. |
| P1 | Same-air moment transport | Already mixed species carry corresponding donor moments through the same completed operator; DEL and host dry carrier remain separately checked. | PASS_SCOPED: research Shinhong QI/QNI routine shares donor operator; driver/native and dry-carrier closure OPEN. |
| P1 | Freezing/tiny graupel policy | Generated Q/N/B/thermal state enters the next property domain; no arbitrary density clamp. | OPEN: freezing uses E/1000 while selected PSD range is 100–900 kg/m³. |
| P1 | Water, energy and host updates | One accepted final state, same dry carrier/time/region, physical boundary and numerical cleanup terms. | OPEN |
| Parallel | Objective-derived analysis candidate | Independent observation operator/errors/background/change authority; estimated analysis term distinct from physical source, boundary and phase; candidate storage/readback. | PASS_SCOPED: manufactured H/B/R estimate → endpoint evaluator → writer → component readback. Producer stages explicitly failed/unrun. Actual 12 UTC case BLOCKED. |
| Final | Native time response | Accepted identical BASE/HYDRO/COUPLED candidates through WPS/real, first call and 10/30/60 minutes, independent observation fit. | NOT_RUN |

## Delivery gates

- [x] Four-agent implementation and independent omission review; resolve concrete findings.
- [x] Focused pinned Intel O0/O2 tests in fresh scratch and relevant Python tests.
- [x] Preserve operational inputs, historical evidence, maintained native source and private configuration.
- [x] Commit, push and create PR after implementation review and validation; no merge.
- [x] Separate dated KLAPS50/Cloud-BAL incremental Graphify snapshots; derived wiki reports, index and append-only audit.

## Acceptance boundaries

A successful property fixture, declared-input preflight, objective solver result, serialization readback and accepted native call are separate gates. Estimated analysis increments need an independent estimation model; they need not be preprescribed. Radar observations are not physical water sources. Optimization iterations are not physical time. A rejected candidate provides no post-call water/energy or initial-shock evidence. Exact absent state differs from positive mass with missing moment. Scientific approval is not inferred from graph freshness.

## First actual native rejection

Ice, `QI=3.5308575789291633e-35 kg/kg dry air`, `NI=0 m⁻³`, `i=133`, `call_lat_index=2`, `k=1`, `KDM62D_INITIAL_PREFLIGHT`. Call-lat is not asserted as global j. The retained public pretrace independently indexes this selected call at j=2. The native run exited 128; all 101 declared input files (100 model inputs plus executable) remained unchanged. Four required post-call outputs were absent, so completion is **REJECTED / FAIL**.

## Evidence and remaining work

- [First violation and completion](PR73_FIRST_VIOLATION_DIAGNOSTICS_20261008.md)
- [Actual property matrix](PR73_PROPERTY_MATRIX_20261008.md): pre-process property stage passes. Separate full-process probe failed at mask 5; this failure is preserved.
- [Upstream and Shinhong QNI evidence](PR73_SPECIES_STATE_TRANSITIONS_20261008.md): no native causal attribution or dry-carrier conservation claim.
- [Objective-derived analysis](PR73_JOINT_ANALYSIS_20261008.md): local linear manufactured objective and endpoint accounting; complete operational diagnostic CLI remains INVALID/UNBOUND.
- [Independent team review](PR73_INDEPENDENT_REVIEW_20261008.md): concrete implementation findings corrected; scientific gates remain open.

Next physical closure requires source-bound completed PBL/RK diagnostics at the first mismatch, integration of the selected QNI transport with its driver/native build, a supported freezing/tiny-particle policy, and one accepted candidate with common-carrier water/energy, mass–wind, native delivery and time response. No accepted native candidate was produced in this batch.

## Publication and KG audit

[PR #73](https://github.com/gonos2k/Cloud-BAL/pull/73) is open and unmerged. Frozen implementation: `b4c78815ea2c784bc9e985ec928b76f057c1099f`. Publication, KG receipt and checklist followups are metadata outside that frozen selected-path extraction.

| Corpus | Nodes / edges / communities | Batch delta nodes / edges |
|---|---|---|
| KLAPS50 | 34,113 / 73,920 / 2,675 | +192 / +285 |
| Cloud-BAL | 8,280 / 15,494 / 642 | +191 / +284 |

Both snapshots are separately dated `2026-10-08-pr73`; derived wiki reports, graph index and append-only audit are synchronized. Extraction covers 101 committed changed paths as overlays onto earlier graphs, AST/Markdown headings only, partial cross-file Fortran CALL edges. External WRF trees and semantic refresh are excluded. Graph deltas reflect structure and preserved evidence, not scientific completion.
