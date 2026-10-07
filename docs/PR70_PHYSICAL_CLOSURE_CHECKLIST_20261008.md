# PR70 physical closure checklist — 2026-10-08

Base: `f4b2c82d42dd4dea87fa9f4a67515452c0049338` (merged PR69).
Overall scientific approval remains **FAIL/OPEN**. Research sources, manufactured full-module tests, neutral native observers and rejected candidate runs are separate evidence.

## Ordered work

| Priority | Item | Completion criterion | Current status |
|---|---|---|---|
| P1 | Cutoff activity search | Find a representable valid step in each supported activity interval; preserve exact stored-state validation and distinguish search failure from absence along the selected direction. | PASS_SCOPED; activity intervals select alpha 0.66666657 for the preserved counterexample; pinned Intel O0/O2 and exact source-extracted update pass. |
| P1 | Rain extinction state | Require zero rain mass to have zero rain number under the declared finite PSD model; reject orphan moments without a floor. | PASS_SCOPED; orphan rain number is rejected, with the existing pending full-evaporation transfer to NCCN represented before the strict stored-state gate. |
| P1 | Positive Kelvin temperature | Clip the common affine direction at T=0; reject nonpositive stored Kelvin temperature after a finite check, without a floor. | PASS_SCOPED; the -1 K false acceptance and exact-zero boundary are rejected in pinned Intel O0/O2 and source-extracted stored-state tests. |
| P1 | Unit/process integration | Build one hash-bound selected source containing public number conversion, density roles, common process fractions and stored Q/N/BG/T validation. Execute its actual cold path at nonunit densities. | PASS_SCOPED; one composed full module passes pinned Intel O0/O2 cold-gate and matched direct-volume tests at four dry densities. Separate PR69 prototypes are not combined into a native pass. |
| P1 | Signed volume process | Bind each process to supported donor/incoming bulk density and available mass/volume at its actual evaluation boundary. | OPEN; matched neutral captures trace the tiny donor to freezing with DENR=1000, outside the declared 100–900 bulk-density interval. All five density gates are inactive; 18 conditional INTENT(OUT) outputs are undefined there. Observed zero is not a source-defined density. |
| P1 | Same-carrier water/energy | Account for phase, cleanup, sedimentation, boundary export and energy using one declared carrier and time interval. | OPEN; PR69 source-measure ledger is not physical dry-water closure. |
| P1 | Dry-carrier PBL/completed transport | Derive matrix, returned tendencies, RK reference, complete Q/N update and boundaries on native dry mass. | OPEN; no posterior normalization or blind DEL substitution. |
| Parallel | Feasible atmospheric candidate | Use independent analysis errors/increments, phase authority, moment prior, boundaries and selected wind authority in one candidate. | Full-observation 12 UTC case remains BLOCKED; a separately declared conditional path does not fill missing observed-case authority. |
| Final | Native acceptance/time response | Consume one accepted candidate through WPS/metgrid/real and evaluate BASE/HYDRO/COUPLED with fixed settings at first call and 10/30/60 minutes. | NOT_RUN for an accepted joint candidate. |

## Team and validation gates

- [x] Review and resolve scoped activity search, source-order and temperature guards with the four-agent team; unsupported native volume policy remains OPEN.
- [x] Validate with pinned Intel `tests/intel_toolchain.sh` in fresh scratch, plus the four source-bound composition tests.
- [x] Preserve original counterexamples, failed builds/runs and exact source/object/executable/input/output identities.
- [ ] Commit, push and create PR after no unresolved scoped implementation blocker remains.
- [ ] Incrementally refresh separately dated KLAPS50/Cloud-BAL graphs and derived wiki audit from the frozen implementation.

## Interpretation

`NO_FEASIBLE_STEP` concerns the implemented process direction and admission policy; it is not a proof that all physically possible process combinations are infeasible. `SEARCH_FAILURE`, `UNSUPPORTED_VOLUME_RATE` and `INVALID_STORED_ENDPOINT` have different meanings. A valid zero-increment stored endpoint must remain distinguishable from an unavailable positive process step.

The cutoff policy is a declared candidate policy. Numerical species extinction must have a material/energy ledger, and gas density, dry carrier density and particle bulk density must retain their distinct roles. No result-dependent source, tolerance, density prior, moment floor, output substitution or damping change is introduced to pass a gate.

Graph navigation uses the maintained PR69 overlay (7,685 Cloud-BAL nodes). The isolated checkout's inherited graph is not the source identity of this work. AST/Markdown structure and partial Fortran CALL extraction do not establish runtime or scientific correctness.
