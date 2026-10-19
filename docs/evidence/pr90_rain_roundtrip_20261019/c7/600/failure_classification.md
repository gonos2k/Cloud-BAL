# C7 600-second fatal record classification

## Confirmed

Both C7 600-second arms terminate at timestep 10, RK stage 3 before T10 KDM6 with the full-candidate infeasible fatal. The receipt-bound `pr85_joint_source_failure.raw.gz` ledger contains six `FULL` rejections per arm, with identical pair indices, coordinates, and printed operands. Each `FULL` row shows the full-candidate helper returned invalid and the stored Q/N sentinels remained `-1`. This uses only `FULL` rows; `SOURCE` rows and trailing graupel trial-reject messages are not treated as the fatal cause.

The six cells are: pair 1 at `(i,j,k)=(130,182,2)`; pair 4 at `(194,80,22)`, `(132,201,19)`, `(196,211,16)`, `(168,225,20)`, and `(231,240,20)`. The pair-call mapping and validation options are from compiled `module_em.F`, SHA-256 `090b9329c817f52f0fba45d6d97f93a6bdb35adc5f46cfed0ae198b15401819b`.

## Predicate status

The logger does not emit `failure_stage` or exact REAL64 candidate bits. Therefore the exact failing subpredicate is **OPEN** for all six rows. The call mapping narrows the available validation paths, but does not reveal whether failure occurred in continuous mass/volume validation or a later REAL32/public-store or directed-Q check.

For the five pair-4 rows, printed Q/N values are near the strict upper bound 900; two print below 900. Strict upper-bound rejection is consistent with the data, but is not directly established without exact operands or a captured stage. For pair 1, a cloud volume-number upper-bound rejection is consistent with the printed candidate and call options, but is likewise inferred rather than captured. See the JSON for all row text, hashes, and receipt bindings.

Both run receipts are `INCOMPLETE`. This is a source/full-host endpoint finding outside the earlier T7/T8 rain cases. It does not establish a global budget or the cause before these recorded checks.
