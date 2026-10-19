# C6 incomplete runtime audit

## Bindings and run result

Both receipts are for the same C6 executable SHA-256 `787dbe92f909db2cf1488378ad534c4b8873b0113d3ded146055ba9aaf762660` and native build receipt SHA-256 `2b663971a0b9040c8ea7f157ede2e7c529373d7df23263fe443684d1160b7515`. C6 build was pinned Intel ifx 2026.0.0 with the Cloud-BAL reproducibility flags. Source receipts and run receipts are separately bound below.

- OFF: receipt `90269ded1c1b2d5e1305face195540dcac9c0cc3f91b789440f2f833788b07f8`; source receipt `65fe21132d20292d9a6e20209e42fa63d96e7680b9ed1e29d0b1b6ee1a187a3e`; status INCOMPLETE, rc 128, seven completed steps (20–140 s), failure at T8 / 160 s.
- COUPLED: receipt `3c0c14fbb1ece6e136ff5838c396b7186b59ba5024b4144b29176cd67fba0b83`; source receipt `8dc7aa4c8b1cdffc72ab29da5a8db255ee96a271bb452fb5bd73a1e62f32d675`; status INCOMPLETE, rc 128, seven completed steps (20–140 s), failure at T8 / 160 s.

For each arm, the run receipt binds its preflight and source receipt; preflight binds the executable; build receipt binds the staged source inputs. Original and staged input-change lists are empty. Stage traces are receipt-bound: OFF compressed SHA-256 `e6a87d42d2d3542337ca048d324ce603cd67ac96c1a53b6e08f8804b58181ffc` (payload `e97b09b7ca12bf8c0285e2fdf9aef342494b60d7840ab9370025822374a8a18c`); COUPLED compressed `17688a4ec4ddf3ba5f0fa37fb3ab8dff88800c361fc93d2fc9255861f6521427` (payload `b9b8bc621b572593f4c40b04b7d6215617658d6db7aa8f88177cf9e797d72637`).

## Completed-state and C5-prefix findings

The receipt-bound stage audit has 64 raw records per arm. T1–T7 completed with POST_KDM6 records; T8 has only partial RK and PRE_KDM6 records, with no POST_KDM6. The generic existing 8-ULP ice check remains FAIL in both arms; this audit does not relax or replace it. Source-native inactive-ice classification shows all detected ice outliers are inactive under the existing `NEAREST(1.e-14,-1.0)` REAL32 source cutoff: zero active outliers. For completed states, outliers are T4 POST (2), T5 RK stage (20) and POST (1), T6 POST (1), and T7 POST (1). Partial T8 RK3 has six outliers, also all classified inactive; this is not a completed timestep. No tolerance changed.

The decompressed C6 stage trace prefix through the 120-s C5 trace matches byte-for-byte for 5,042,096,500 bytes in each arm. OFF prefix SHA-256 is `75aa062fe3786dbf538be91e5fadb701825b0ecdf4f2cda8b2b5fe6dc9f6389c`; COUPLED is `69bf38f5a02d685852a397da190101a194e8778537617fa8aedd3082d984e9e9`. This establishes exact trace equality through 120 s for each corresponding arm.

The C6 run receipts also bind the generated `wrfout_d01_2026-08-16_13:00:00` artifact to the same SHA-256 as the corresponding C5 history artifact: OFF `1eb247193d4fda3e34e73f13dd4ff979e9840965e7dcea9d7dbfbe939b5a93eb` (275,946,609 bytes), COUPLED `da3120606e8ac471242039c53410300d7ff7fee5027b636b93adeefb29d54543` (275,955,929 bytes). These are whole-file receipt hashes, supporting unchanged history output through the archived 120-s window for these artifacts.

## Failure and replay scope

The T8 failure is the existing paired rain public-store invalidity path. Do not interpret the generic ice FAIL as the run-stopping cause; it is a separate diagnostic finding. The stage trace’s T8 PRE_KDM6 record contains only the joint-state fields and is not enough to replay the full KDM6 call. A faithful whole-call replay would require the full caller arrays/scalars at the T8 call boundary, all required work arrays and external accumulators, the same module initialization state, and the exact C6 source/build/toolchain. The current first-call pre-dump is from timestep 1, not T8. A narrower replay of the failing store predicate can use the captured target inputs, but is not a whole-KDM replay.

No 600-s extension should be inferred from these incomplete runs. Full machine-readable detail is in `/var/tmp/pr90_c6_incomplete_runtime_audit_20261019.json`; the audit script is `/var/tmp/pr90_c6_prefix_ice_audit_20261019.py`.
