# CP02 event-contract KG update — 2026-10-28

Graphify 0.9.53 incrementally extracted exactly two frozen Python paths from the source overlay at base `f308ebcb0378ab367951656f75598b1ec9267e33`. The code files were `docs/evidence/cp02_call_boundary_20261028/analyze_boundaries.py` and `tests/test_cp02_boundary_events.py`; reports, docs, and runtime evidence were SHA-256 bound only.

| Corpus | Nodes | Edges | Communities | Delta nodes / edges |
|---|---:|---:|---:|---:|
| KLAPS50 | 41451 | 86140 | 3347 | +13 / +23 |
| Cloud-BAL | 15623 | 27683 | 1380 | +13 / +23 |

The AST extraction produced 30 nodes and 75 edges per corpus. Multigraph diagnostics reported zero missing endpoints, dangling endpoints, and same-endpoint groups. The stage preserves the 87 KLAPS50 and 91 Cloud-BAL existing dated snapshots; the new date-specific snapshot is `2026-10-28-cp02-event-contract`.

Validation references: 39 focused tests passed; the captured actual-host comparison records original CLI exit 0 versus fixed CLI exit 1 with rejection and no output, with normal profiles containing 4,224 rows; the old profiles artifact was 465,042 bytes, with summary arithmetic unchanged. The KG stage did not rerun tests or an Intel/GDB/model replay.

Extraction limits: only the two selected Python files were structurally extracted; eight other changed paths are hash-bound only. Fortran cross-file CALL extraction remains partial. Graphify also did not resolve the regression test's module-alias call path to `validate_capture()`. Graph freshness does not establish runtime or scientific validation.

Full machine receipt: `docs/evidence/cp02_event_contract_20261028/kg_receipt.json`. Validation SHA-256: `ccb31869bda021a64c87cab6bf683cc38989b8ddd4278bba59e648c988ea97ba`. Team-review SHA-256: `46c9585443f118ea731a5072735cdc94fed5b9b5d1c17050f82c824e9e0efe38`.


Publication readback: the selective graph layer and derived wiki were published to the maintained KLAPS50 and Cloud-BAL roots. The new dated snapshots are `2026-10-28-cp02-event-contract`; 87 pre-existing KLAPS50 and 91 pre-existing Cloud-BAL snapshots remain byte-identical. Current maintained graph SHA-256 values: KLAPS50 `0a1cb5fddfbecea8f1c2856e51b18ed0b239ae3dd5e69d0e279be193c3f6fb7c`; Cloud-BAL `5df61251dde693afbcab35c4c556438cc3fce8132a7177250f4f46d40256a990`. The compact receipt includes the full snapshot and report/manifest hashes.
