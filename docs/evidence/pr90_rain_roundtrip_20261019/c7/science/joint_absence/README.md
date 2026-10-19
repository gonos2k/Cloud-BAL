# C7 180-second joint-absence event audit

This is a C7-scoped evidence copy of the preserved C5 audit. It applies the same selector and arithmetic to receipt-bound C7 `STORED_PAIR` rows; the original C5 script/result are unchanged.

## Identity and calculation equivalence

- C7 result: `result_180s.json`, SHA-256 `e6a0eeab15e2d19f62e764afdce69c3831479f4b1777b47965f33c62e9078627`.
- C7 audit copy: `audit_joint_absence.py`, SHA-256 `1fde09917422f9cbec507454b5cb9f1657749e59b575dc4f53d56e81573b8e9f`.
- Original C5 audit: SHA-256 `d2efd32aaa289ce75551cd817086024a8edf07c249f8f0cbbfdf3fd8057ac547`; original C5 result remains SHA-256 `2e7b8c25ff5102e46862a4cf5fc18b6522e31bd363754aee0b1faf0e223e25f2`.
- AST comparison found exact equality for `print_interval`, `stored_pair_rows`, the nested `weight` and decimal-serialization functions, and the entire `for fields in stored_pair_rows(ledger)` event-selection/geometry-validation/interval-arithmetic/aggregation loop. Differences are confined to C7 180-second receipt/preflight/build/source guards, run arguments, and C7 scope/reproduction metadata.

C7 guards pin build receipt `7a58ac2ae90eca9ffe0500515282b537e11db25ab9de8175856609bf812bba31`, executable `5f5599e38759a9e2be27a9e7e0977370592c92cab328062d07eb359bddd19572`, compiled `module_em.F` `090b9329c817f52f0fba45d6d97f93a6bdb35adc5f46cfed0ae198b15401819b`, and `solve_em.F` `412183300ea8dd6af028ac1a5254f937477b054630db4eb1f5910a6bf974c3c5`. It also pins both arm receipt and preflight hashes. Each receipt binds its compressed and decompressed event-ledger hashes; the result records those bindings.

## Reproduction

```sh
python3 docs/evidence/pr90_rain_roundtrip_20261019/c7/science/joint_absence/audit_joint_absence.py \
  --off /var/tmp/pr90_OFF_180s_c7_20261019 \
  --coupled /var/tmp/pr90_COUPLED_180s_c7_20261019 \
  --output docs/evidence/pr90_rain_roundtrip_20261019/c7/science/joint_absence/result_180s.json
```

Both runs are `COMPLETE`, nine timesteps, 180 seconds. The audit scanned 96,573 OFF and 96,459 COUPLED `STORED_PAIR` rows. It selected 69,690 OFF and 69,698 COUPLED same-event joint-absence events. Each arm has 48 groups: steps 2–9, three RK stages, and pairs 1 and 2. No matched pair-4 event occurred.

## Physical meaning and limits

For a selected row, the stored-to-candidate signed change is `stored - candidate`. For Q and pairs 1–3 N, the signed quantities are `-candidate_Q * md` (kg) and `-candidate_N * md` (number count); pair 4's candidate second field is QIB volume mixing ratio, giving `-candidate_QIB * md` (m³). The same event supplies `newcarrier`, `rdnw`, `msftx`, `msfty`, `rdx`, and `rdy` for

`md = newcarrier * (-1/rdnw) / (g * rdx * rdy * msftx * msfty)`.

The audit checks the event geometry signs before calculating its weight and uses the source-pinned promoted REAL32 gravity. Printed-decimal intervals cover text-rounding uncertainty only, not REAL32 candidate/storage rounding or transport residuals. Grouping is by timestep, RK stage, and pair. No totals across RK stages or timesteps are presented as a final budget, and these selected events are not a complete model number or water budget.
