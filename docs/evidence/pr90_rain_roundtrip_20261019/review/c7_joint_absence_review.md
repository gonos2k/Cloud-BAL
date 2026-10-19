# Independent C7 joint-absence evidence review

Read-only review of the preserved C5 audit/result and C7 180-second audit/result/README. No model runs, code edits, or evidence changes were made. The C7 600-second paired runtime remains pending and is outside this audit's scope.

## Findings

- **C5 originals remain intact:** `science/joint_absence/audit_joint_absence.py` SHA-256 is `d2efd32aaa289ce75551cd817086024a8edf07c249f8f0cbbfdf3fd8057ac547`, and its `result.json` SHA-256 is `2e7b8c25ff5102e46862a4cf5fc18b6522e31bd363754aee0b1faf0e223e25f2`, matching the preserved C5 pins.
- **C7 is separately bound to its 180-second run:** result `result_180s.json` SHA-256 `e6a0eeab15e2d19f62e764afdce69c3831479f4b1777b47965f33c62e9078627`; audit SHA-256 `1fde09917422f9cbec507454b5cb9f1657749e59b575dc4f53d56e81573b8e9f`. It requires COMPLETE, return code 0, nine steps, 180-second/20-second preflight, arm-specific receipt/preflight hashes, the pinned C7 build (`7a58ac2a…`), executable (`5f5599e3…`), compiled `module_em.F` (`090b9329…`) and `solve_em.F` (`41218330…`). The four C7 archived run-receipt/preflight files hash exactly to the C7 result's recorded pins; each receipt binds its source receipt and compressed/raw ledger hashes. Build/executable and receipt hashes match archived `c7/build_receipt.json` and `c7/180/{OFF,COUPLED}/run_receipt.json`.
- **The event filter and arithmetic are unchanged:** AST equality holds for `print_interval`, `stored_pair_rows`, `weight`, decimal serialization, and the full `for fields in stored_pair_rows(ledger)` event-selection/geometry-check/interval-calculation/aggregation loop. The changed audit code is in the C7 scope and provenance guards/output metadata.
- **Counts and grouping agree with the C7 README:** OFF scanned 96,573 rows and selected 69,690 events; COUPLED scanned 96,459 and selected 69,698. Each has 48 groups over steps 2–9, RK 1–3, pairs 1–2; pair-4 event totals are zero. README explicitly says printed-decimal intervals cover only text-rounding uncertainty and does not present RK-stage or timestep sums as final budgets.

No concrete scientific-evidence blocker found in the requested scope. The audit supports only the stated selected joint-absence STORED_PAIR diagnostic; it does not establish a complete model budget or physical acceptance.
