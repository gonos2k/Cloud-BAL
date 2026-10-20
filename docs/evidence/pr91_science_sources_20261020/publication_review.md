# PR91 source/replay publication review — 2026-10-20

## Result

No concrete inconsistency found in the current PR91 science-source, host-store contract, or preserved-history reports after checking their cited evidence. The source-gap report keeps the original 162-pressure-cell support separate from the 27-column C7 outcome support and records the remaining source-bound horizontal/vertical influence weights as missing. Its C7 AUT/G table is correctly labeled as a trace-gated, area-weighted first-failure-associated proxy; it does not claim a unique causal partition or full-window join.

The C7 admission records do not provide a timestep, and their logged half-L1 activity excludes `DEN*DELZ` and area until the stated reconstruction. The report also keeps the `rain_g_alpha` versus collector `rain_process_alpha` mismatch visible. Alpha-scaled and withheld proxy values therefore are not presented as a reconciliation to the full-window collector totals. Printed ES24.16 REAL32 fields limit integration precision as stated.

## D3 binding and failure replay

Rechecked the immutable raw trace, gzip decompression, closed-run receipt hash, raw/gzip SHA-256 pins, and replay rows. The capture has 17 failure rows and 17 matching options rows. Both O0 and O2 replay reports contain all 17 rows as `REPRODUCED_FAILURE`, matching the captured candidate bits, stage, adjustment, and stored sentinels: 15 stage-2 failures and 2 stage-3 failures, split across 11 baseline and 6 source-first attempts. The closed D3 run is `INCOMPLETE`, rc=1, with nine completed steps and a T10 failure; the replay does not imply model completion or corrected-candidate validation.

The endpoint → virtual donor → full candidate source-chain fixture is consistent with the stated scope: stored endpoint reconsumption passes, the later source contribution produces an invalid virtual donor before air transport, and the full source-first candidate fails the volume gate. This identifies a source-stage arithmetic/state sequence for the captured fixture, not a general repair or proof that endpoint-contract alignment fixes the sequence.

## Regression scope

The focused pinned-Intel run passed 46 Python tests, plus the standalone `test_joint_qnb_transport` Fortran regression under O0. It includes four new PR91 test modules and affected joint-store, rain-store, warm-rain, and KDM6 warm-process tests. `test_pr91_source_first_diffusion.py` was excluded because it contains the C9 fixture currently being edited. No native/model run was started. Exact commands, logs, compiler identity, test hashes, and scope are in `focused_regression_command.txt`, `focused_regression.json`, and the two logs.

The standalone transport regression emits pre-existing Intel subnormal-conversion remarks and array-temporary runtime warnings, then prints `PASS test_joint_qnb_transport` and exits zero.

## Graph snapshot

The existing `graphify-out/graph.json` predates the PR91 work and does not contain the PR91 additions. I queried it read-only for the related relationships; it returned older Cloud-BAL nodes. No graph update was performed as part of this independent review, so graph freshness is not evidence for the reviewed PR91 content.
