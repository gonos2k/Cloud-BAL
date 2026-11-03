# Recount coverage and physical-lineage handoff — 2026-11-03

Base: latest research merge `83804668a02e20eeac686d00ff5b2ff6b9a71154` (PR142), whose tree equals `5e3bba43a7d471900ff7bef96934ec629f2dbd96`. The default branch remains separately identified in the status receipt. This batch changes the independent recount contract and the two existing status overviews. It does not change archived forecasts, score tables, selection criteria, or model policy.

## Recount result

The validator now requires the six ordered thresholds, all nine mandatory table cardinalities, exact unique admission keys, and final actual recount counts. The malformed empty-threshold fixture and duplicate-table/admission fixtures are rejected before an audit output is written. Normal saved arrays still pass with 432 categorical, 72 continuous, 396 transition, 152 admission, 1,980 observation-band and 3,300 observed/forecast-bin rows. Old and final source hashes and before/after commands are in `validator/`. A separate Git export passed 152 related Python tests; the full portable suite was not run.

## Physical investigation

`physics/rain_number_lineage.md` separates historical CP02 OFF/HYDRO/LIQUID from the current B1 input. The exact B1 initial file has 2,573,532 cells; 202,569 have positive QRAIN, while QNRAIN is zero everywhere. Retained metgrid products contain QR and no QNR. A nearby real-source rain-number policy is Thompson-only and is not bound to the historical real executable. The retained host-density algebra is a source observation, not a verified runtime density identity. No particle-number seed or forecast improvement is claimed.

## C2 scope

`c2/` records fresh pinned Intel O0/O2 bounded replays. The first group cell and separate fatal callback reproduce their retained local failures. No original producer stencil for the first group was captured, no coupled-constraint policy was changed, and no C2 H/A/N forecast was rerun. The initial callback attempt used a non-executable `/tmp` mount; the unchanged helper passed after a fresh build in executable `/var/tmp` scratch. Both attempt and successful evidence are retained.

## Next separate diagnostic batch

The next focus is +2–+6 h low-threshold recovery while protecting CURRENT B1's +1 h six-threshold performance and each lead's ≥5 mm CSI. This does not rewrite PR142's historical ORIGINAL-based admission rule. A separate 0–2 h diagnostic pair uses the same B1 initial and boundary files with the existing and zero-rate-fixed KDM6 executables. Detailed lost-hit, new-false-alarm, stable weak-hit and strong-hit samples are post hoc diagnostics; the full 3,688-point verification cohort remains unchanged. Preparation outside this worktree is not a completed or validated model trace.

## Evidence and maintenance

The root `validation.json` binds the final evidence and team review after scoped KG publication. Graphify extracts only the listed changed Python files; binary/NetCDF metadata, generated bounded Fortran replay copies, Markdown and receipts are hash-only. Existing dated snapshots and unrelated dirty maintained roots are preserved. Graph freshness does not establish runtime or scientific validation. RN1 timing/coverage, complete coupled budgets, independent-event validation and C2 completion remain open.
