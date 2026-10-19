# C5 joint-absence reconstruction

This read-only audit examines the preserved C5 OFF and COUPLED 120 s runs. It selects `STORED_PAIR` ledger rows where the stored Q and second moment are both zero while both same-event candidate values are positive. Results are grouped by timestep, RK stage, and pair. The reported signed change is `stored - candidate`; the grouping never sums across RK stages as a final budget.

| Arm | Stored-pair rows | Joint-absence events | Group count | Pair 1 events | Pair 2 events | Pair 3 events | Pair 4 events |
|---|---:|---:|---:|---:|---:|---:|---:|
| OFF | 56,778 | 43,128 | 30 | 41,635 | 1,493 | 0 | 0 |
| COUPLED | 56,743 | 43,126 | 30 | 41,633 | 1,493 | 0 | 0 |

Each run has groups for steps 2–6, RK 1–3, pairs 1 and 2. The hash-bound `solve_em` source maps pair 4 to QG/QIB. The compiled `module_em.F` source identifies QIB as rime-volume mixing ratio (`m3 kg-dry-1`) and bounds graupel bulk density to 100–900 kg m-3. Thus pair-4 signed bulk volume is directly `-candidate_QIB * md` in m3; no graupel-density conversion is needed. Neither run has a matched pair-4 event, so the event-set volume contribution is zero.

For every matched event, the dry-air mass weight uses only same-event fields printed on that `STORED_PAIR` record:

`md = newcarrier * (-1/rdnw) / (g * rdx * rdy * msftx * msfty)`

`newcarrier = c1(k) * (munew(i,j) + mub(i,j)) + c2(k)`

For pairs 1–3, signed mass is `-candidate_Q * md` in kg and signed number is `-candidate_N * md` in count. For pair 4, the second candidate field is QIB, so its product with `md` is volume in m3. Gravity is the promoted REAL32 value `9.81000041961669921875 m s-2` from the pinned constants receipt, SHA-256 `7b6cc54597b1d67c35ec112decab192cae3d1d5035ec03f5fb418a081df38670`.

The default list-directed ledger values are decimal rounded. Each is represented by a half-last-printed-digit input interval. The script performs 80-digit Decimal interval operations with lower endpoints rounded toward negative infinity and upper endpoints toward positive infinity through the event weight, products, grouped sums, and exact endpoint serialization. Center values are approximate 16-digit decimal displays. Bounds cover printed-decimal uncertainty only; they do not cover ordinary REAL32 candidate/storage rounding, transport residuals, or other model budget terms. Both compressed and decompressed ledger hashes match their run receipts.

Reproduce with:

```sh
python3 docs/evidence/pr90_rain_roundtrip_20261019/science/joint_absence/audit_joint_absence.py --off /var/tmp/pr89_OFF_120s_c5_20261019 --coupled /var/tmp/pr89_COUPLED_120s_c5_20261019 --output docs/evidence/pr90_rain_roundtrip_20261019/science/joint_absence/result.json
```

Audit script SHA-256: `d2efd32aaa289ce75551cd817086024a8edf07c249f8f0cbbfdf3fd8057ac547`.
