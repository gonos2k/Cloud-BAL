# C18 publication-helper review

Read-only review of the external evidence finalizer and selected-source KG helper on 2026-10-20. Runtime receipts and final manifests were not yet available; this review does not close either gate.

## Pins checked

- `/var/tmp/pr92_finalize_evidence_20261020.py`: SHA-256 `db1f1ec699b51128114b3040529601ec12736cb35d487b95ad4d8964182507e5`.
- `/var/tmp/pr92_refresh_kg_source_store_20261020.py`: SHA-256 `9b848a2a48ab104ab96447355d71c14f6719cc19be371e0cfdc3b52b4f840051`.
- Both helpers require candidate `PR92-C18-bounded` and executable SHA-256 `32a324d49366487f68ec1e6e687a465ef2533bd9163e2fe09733e83cc2272c16`.

## Review findings

- The finalizer reads the C18 canonical-validation record and refuses to publish unless status/exit, frozen-file integrity, and core/fixture hashes match the current sources. It also checks the focused-suite result and generated-source binding. C18's canonical frozen-snapshot rerun is still in progress, so this check has not yet been exercised against its final receipt.
- The source-hash set includes the C18 generated module and preserved C15/C16/C17 generated modules, archived C17 core/generator/instrumenter, historical policy/module sources, maintained source allowlist, and Intel toolchain profile. Validation logs are recursively enumerated. Runtime receipts, preflights, and launch provenance are copied and their hashes/identity are referenced by integration; the integration manifest's validation hash binds the final validation payload.
- Bulk ledger units and scope remain correct: `delta_Q`/`delta_B` are RK-row sums of positive `newcarrier` times intensive event error, the event bounds are stated as policy/fixture-verified, and the aggregate is explicitly insufficient to verify per-event or extensive bounds. The ledger scope remains committed code-5 absence events; positive directed adjustment-2 events belong to the general storage ledger.
- COMPLETE runtime receipts require exact ledger cadence through the completed step. INCOMPLETE receipts permit only an ordered RK prefix at the immediately following step and require `maximum_seen_timestep` to agree. Receipt status and return code remain explicit rather than being promoted to success.
- The KG check requires committed evidence bytes to match `git show` at the frozen commit, the actual GitHub PR to be open with the requested head SHA/branch and `main` base, matching C18 identity/executable, paired arm receipts, and the validation hash. It preserves `physical_approval: FAIL_OPEN` and still guards the prior snapshots and protected wiki/source inventories.
- The integration science-identity wording now distinguishes C14 response maps, C16 byte-identical history through T240, selected QC vertical replay, separately bound C17 audit, and a C18 audit that can only be bound after closed receipts. This does not claim C18 scientific validation.

## Gate status

No helper-contract blocker found in this review. The canonical C18 rerun and paired C18 runtime are pending. After runtime closure, the finalizer output and C18 audit binding still require a read-only check before the later guarded KG check/apply.

## Addendum: completed-state audit gates

The helpers were updated after the review above; this addendum records the new pins and audit checks.

- Finalizer SHA-256: `31e21d799f81c2ce675d21ca020f57a24f46742d995e53da50721758beede11b`.
- KG helper SHA-256: `f3fcf23ea71a92c8fbabdaaf931cb88c164f870a1b2f1ae1f49e5b94bcbd356b`.
- The canonical C18 snapshot now reports PASS, exit 0, all 6,372 frozen-file hashes unchanged, and core/fixture hashes matching the reviewed C18 pins.
- Finalization now requires per-arm closed-state audit summaries matching runtime status, completed step, zero processing errors, receipt hash, executable SHA, and the C18 generated-module SHA. It gates the declared native ice policy on PASS, zero active outliers, zero strict-state failures, and exactly six completed states per completed timestep. The generic exact-source audit status is separately carried through without being substituted for the declared-policy result.
- KG check recomputes each audit file hash, matches its receipt/executable binding, confirms the declared-policy object and metrics, and checks that the generic status matches the manifest entry. C18 identity and executable pins remain consistent across both helpers.

No blocker found in these additions. The paired C18 runtime and actual audit summaries are still pending, so the per-arm gate has not yet been exercised; after receipts close, review the concrete audit values and generic status before final publication.
