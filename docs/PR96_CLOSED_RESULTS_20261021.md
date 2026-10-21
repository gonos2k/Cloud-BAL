# PR96 closed-run results — 2026-10-21

These results bind to the startup source commit `9191cd4a3cef3eaa897d2b0a7a2693f0ddd88b84` and the finalized, receipt-closed outputs under `KLAPS50/scratch/pr94_physics_20261021/`. This is a procedural/runtime record; it does not establish physical approval.

| Case | Requested | Closed runtime | Fatal / control outcome | Audit outcome |
|---|---:|---|---|---|
| OFF compact | 3600 s | INCOMPLETE; 31 steps / 620 s; rc 1 | `PR87 full joint moment candidate infeasible; see source/full diagnostics` | Generic completed-state audit FAIL; compact profile PASS; exact-source endpoints PASS; active-ice policy PASS |
| COUPLED compact | 3600 s | INCOMPLETE; 31 steps / 620 s; rc 1 | `PR87 full joint moment candidate infeasible; see source/full diagnostics` | Generic completed-state audit FAIL; compact profile PASS; exact-source endpoints PASS; active-ice policy PASS |
| HYDRO control | 600 s | INCOMPLETE; 25 steps / 500 s; rc 128 | `KDM6 invalid base before nongraupel admission` | Control incomplete; no normal 600-second response evaluated |

The generic completed-state audit reports negative Q cells beginning at timestep 2 and later ice mass/moment cone violations. Those are audit findings distinct from the runtime's fatal message; this record does not infer that either finding alone caused the fatal. The fatal wording in both longrun `rsl.error.0000.gz` archives is generic for the PR87 full-joint-moment guard and points to source/full diagnostics.

The 0–600 second compact-versus-baseline trace comparison PASSes for both OFF and COUPLED (180 retained state records; common completed prefix through step 30). A separate comparison of ten raw history fields—T, P, PB, PH, PHB, U, V, W, MU, MUB—PASSes at all 11 common timestamps from 0 through 600 seconds for both arms, with exact numeric equality and metadata checks. This validates only the compared prefix and fields; neither run completed 3600 seconds. The earlier C4 baseline OFF/COUPLED 600-second control remains a successful baseline result.

All seven startup reader dependency hashes match commit `9191cd4a3cef3eaa897d2b0a7a2693f0ddd88b84`; the closed receipt hashes, audit hashes, runtime bindings, and history results also match the original result record. Run receipts, audits, runtime bindings, trace comparison results, and history comparisons are summarized with SHA-256 references in [`evidence/pr96_local_closure_20261021/closed_results.json`](evidence/pr96_local_closure_20261021/closed_results.json). The original full result record remains at `/var/tmp/pr95_closed_results_20261021.json` (SHA-256 recorded in the bounded JSON); the complete archived run artifacts remain in their receipt-bound run directories. No model was rerun for this publication.
