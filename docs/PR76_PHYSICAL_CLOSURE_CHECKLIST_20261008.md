# PR76 closure checklist — 2026-10-08

Review/source base: merged PR75 `fd7e1be37075a7ba80ee3a0be080111a5be03a26`.
The previous PR75 receipts remain immutable. This checklist updates their interpretation with new, separately bound executions.

## Completed in this batch

- [x] Reproduce the reported equality/box singleton: prior source rejects the exact optimum `(0,0)`, cost 1. Preserve the declaration and an exact legal KKT witness.
- [x] Construct multipliers over all bounds actually active at the returned state, including a bound reached by a coordinate treated as free during the primal solve.
- [x] Restore the full normalized equality row span when certifying stationarity. Fixed bounds have unrestricted multipliers; lower/upper multipliers retain their sign restrictions.
- [x] Search nonnegative projected bound-normal supports and reconstruct the complete stationarity equation. Retain the existing `4096*epsilon` certificate threshold, primal, dual-sign, complementarity, finite-value and rank checks.
- [x] Expose normalized equality rows, targets and witness multipliers for independent certificate replay.
- [x] Validate 162 exact dyadic manufactured optima, variable permutations, coordinate unit changes, redundant equalities, mixed lower/upper/fixed faces, and a feasible nonoptimal control.
- [x] Run 68 Python test methods with the frozen source and final oracle; retain the earlier scalar, covariance, unit and negative-certificate regressions.
- [x] Compile fresh pinned Intel O0/O2 endpoint evaluator/writer/readers in separate scratch directories and pass the estimator fixture's component readback.
- [x] Run the full canonical diagnostic on the new O2 fixture: retain its expected `UNBOUND/REJECTED` outcome. `run_cloud_bal_pipeline()` was not run.

The small solver remains a manufactured quadratic reference limited to eight variables. Projected support enumeration and Gram solves do not establish robustness for arbitrary ill-conditioned or operational problems. Numerical inability to certify remains distinct from physical infeasibility.

## Native FP policy comparison

The native experiment is a copied partialhost research build. It changes only the runtime FTZ/DAZ policy and adds diagnostics. It does not repair hydrometeor values or modify maintained model inputs/sources.

- [x] Freeze the paired native receipt and exact same-coordinate NI conversion. Baseline `0x0093B134 * 0x3F449EE9` becomes `+0`; treatment returns positive subnormal `0x00716F5A`. Both preserve identical 100 inputs, pretrace and driver capture.
- [x] Verify MXCSR `0x9FFD -> 0x1FBD` at the calling thread entry and preservation of all bits outside `0x8040`. The compiled Intel helper test and three transformation tests pass. Conversion later adds status bit `0x02`; underflow status was already set before.
- [x] Record the thread-persistent KDM6-entry policy and its limited coverage. Treatment passes the NI adapter, then exits 128 at `orphan number/volume state without positive mass`; no coordinate is claimed for that later fatal. Required post-call files are absent, and native remains `REJECTED`.

## Remaining physical gates

| Priority | Item | Closure condition |
|---|---|---|
| P1 | Whole host/thread FP policy | Source-bound main/worker configuration and physics entry agree; rounding, masks and status are preserved; required threads are covered. |
| P1 | Completed Q/N/B state | Same carrier/time/boundary for generation, PBL, advection, RK, phase, sedimentation and representation cleanup; each completed state lies in the next process's domain. |
| P1 | PBL `DEL` versus dry carrier | Derive matrix/RHS/returned tendencies and completed host update in the native dry-mass measure with boundary terms. |
| P1 | Freezing and transient QG/BG | Define species creation, activation, sublimation and disappearance with coherent mass, volume, particle properties and thermodynamics. |
| P1 | First native call | Valid pre/post Q/N/B/T/q, all required outputs and same-call geometry; no floor, unilateral deletion, rate cap or arbitrary rescaling. |
| P1 | Water and energy | Same candidate/carrier/time/region, analysis/phase/source/boundary/cleanup terms and precipitation enthalpy; no receipt splicing. |
| Parallel | Spatial joint candidate | Independent H/B/R, authority and boundary declarations; neighboring columns with pressure/Phi/face flux and hydrometeor constraints, reconstructed through the common pipeline. |
| Final | Native delivery and time response | Identical candidate through WPS/metgrid/real; fixed-setting BASE/HYDRO/COUPLED first call and 10/30/60 minutes, retaining observed cloud/precipitation/updraft signals and using independent verification. |

Overall physical initialization remains **FAIL/OPEN**. Estimator-fixture correctness and FP diagnosis are separate from native state acceptance and initial-shock reduction.

## Evidence

- `docs/evidence/pr76_degenerate_reproduction_20261008.json`
- `docs/evidence/pr76_degenerate_kkt_oracle_20261008.json`
- `docs/evidence/pr76_degenerate_endpoint_20261008/receipt.json`
- `docs/evidence/pr76_native_fp_policy_20261008.json` (separate native execution)
- `docs/PR76_TEAM_REVIEW_20261008.md` (final team review)

## KG maintenance

Pending the frozen code batch's incremental Graphify/KG update. KLAPS50 and Cloud-BAL will retain separate dated snapshots, old artifacts and derived report/index/log synchronization. Graph structure and freshness do not establish runtime or scientific validation.
