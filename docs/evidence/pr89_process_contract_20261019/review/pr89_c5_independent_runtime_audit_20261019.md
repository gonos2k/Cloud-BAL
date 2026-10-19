# PR89 C5 independent native runtime review

## 120-second paired run

Both closed candidate runs completed all six model steps (20–120 s), with six unique `POST_KDM6` states, 18 `RK_STAGE_END` states, six each `PRE_RK` and `PRE_KDM6`, and 18 feasible `JOINT_RK` records at `theta=1`. The executable hash is `beb2da6745606566074e15a043d173a8be01d277f00c4cc90ad3915f5de5a2d6`; its pinned Intel ifx 2026.0.0 overlay build receipt binds to the staged sources and reports `full_clean_build=false`. Both runtime receipts report no changed original or staged inputs.

The independent completed-state auditor reports `FAIL` for both arms because its generic all-positive ice cone check flags inactive-mass ice pairs beyond 8 REAL32 ULP: OFF has 2 at T4 POST, 20 at T5 RK3, 1 at T5 POST, and 1 at T6 POST; COUPLED has the same counts. The independent split against the source KDM6 limit `QI <= 9.999998977483753e-15` finds **all flagged pairs inactive** (0 active outliers in either arm); maximum QI among flagged pairs is `2.579533808777512e-15`. The generic FAIL is preserved in the attached auditor JSON. The source-coefficient gates for cloud, rain, and graupel are empty at all 18 required endpoints in each arm.

## 600-second paired run

Both runs stopped incomplete at the T7 rain public-store rejection (exact sub-predicate not captured) after the six completed steps. Each decompressed 120-second stage trace is an exact byte prefix of the corresponding 600-second trace: 5,042,096,500 bytes compared per arm, with matching prefix SHA-256. This supports preservation of the 120-second completed prefix; it does not establish 600-second completion.

## Provenance and artifacts

The machine-readable report records receipt, input, executable, source manifest, trace, prefix, audit JSON, and compressed audit JSON hashes. Full completed-state audit JSONs are compressed with deterministic gzip in this directory; originals under each runtime directory remain untouched.
