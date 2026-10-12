# Team05 / Team12 Cloud-BAL accounting audit

Date: 2026-10-12  
Target: `scratch/pr77_native_state_20261012/Cloud-BAL`, PR77 snapshot (base `9701ef2` per assignment)  
Mode: read-only source/evidence review; targeted checks compiled in fresh `/var/tmp` scratch using the pinned `tests/intel_toolchain.sh` Intel ifx profile.

## Result

No exact conservation or rollback counterexample was reproduced in the scoped Cloud-BAL accounting code. The fixed-geometry endpoint budget, one-cell pressure-domain activation/removal budget, float64 remap, and internal phase transfer tests passed. The code distinguishes those ledgers carefully: a pressure-analysis endpoint difference is not source transport closure; internal phase transfer is calculated on fixed dry-air mass; pressure-domain geometry adds an explicit mass measure; and the native observer labels its DEND-based output as source-carrier-equivalent rather than physical water mass.

The material remaining issue is an evidence limitation, not a reproduced implementation bug: the PR69 native carrier is not established as the physical dry-air carrier for all six dry-air-specific water fields, so its nonzero storage-plus-export residual cannot establish physical whole-water closure. Native energy, pressure work, and kinetic energy are also not captured. The reports already state these limits; keep them attached to any use of the measurements.

## Findings

### A. PR69 ledger is source-carrier accounting, not a physical water closure — P1 for any physical-closure claim; evidence gap

At `tools/pr69_water_budget.py:278-288,304-322`, the observer extends captured `DEND*DELZ*area` to all six water fields and replays bottom export from `FALL*DELZ/DENR*DTCLD*1000*area`. Its output labels the quantity `SOURCE_CARRIER_EQUIVALENT_NOT_PHYSICAL_WATER_MASS`, states that the source density basis is not established for dry-air-specific Q, and marks physical water mass unsupported pending selected-source density routing. The recorded result has a `+1,912,114.113` source-carrier-unit return storage-plus-export residual; the interval ledger records cleanup `+2,126,112.845`, mixed sedimentation `-3,398.492`, first ice substep `+104.240`, and remaining-call evolution `-210,704.495` in the same units. Those are measured terms, not closure errors or inferred process causes.

`docs/PR69_NATIVE_WATER_BUDGET_20261007.md:56-80,107-153` explicitly documents the carrier ambiguity, unsupported energy, failed/incomplete candidate attempt, and unsupported boundary/other-timestep scope. The captured host moist `DEN` is formed from `1/ALT*(1+QV)`, while the public Q basis is dry-air specific. The same-call geometry audit independently gives a `DEN*DELZ*area` diagnostic `0.00058556` above hybrid dry mass, but does not equate these measures. This is a carrier/science-evidence gap, not a falsified arithmetic replay.

Next check: resolve selected-source `DEN`/`DEND` routing and its relation to the dry-air Q basis at the exact call; if physical closure is desired, instrument source-compatible dry carrier, all water source/sink and boundary terms, then independently review. Capture full source-defined energy (including work and kinetic terms) before claiming energy closure. Do not reinterpret the current residual as physical kg closure.

### B. Pressure-analysis and domain budgets are endpoint ledgers with explicit scope — no defect found

`src/common/cloud_bal_column_physics.f90:500-580` computes species mass changes as `ma*ra - mb*rb`, with the exact split `mb*(ra-rb) + (ma-mb)*ra`; dry mass is reported separately; vapor is included; and the total identity is `Δdry + ΣΔspecies - Δpressure_mass`. Enthalpy is the endpoint change in the declared linear moist-mixture convention and is split algebraically into composition and mass-metric terms. Incomplete species remain visible through counters on same-domain calls and cause domain-change bookkeeping to fail closed. Geometry/domain change requires explicit opt-ins; neither opt-in grants application/source authority.

`src/common/cloud_bal_column_physics.f90:582-1123` and `:827-858,886-1027,1031-1042` treat the newly activated strip as a boundary donor with dry mass `A*ΔPS/g/(1+Σr)`, remap piecewise-constant extensive density per Pa, and revalidate the float32 state against pressure mass and full-mixture enthalpy. The code itself says the prior is reconstruction input, not observation authority, and that boundary conservation needs its own contract. Thus successful domain-budget closure confirms the supplied endpoint identity; it does not independently validate the reconstructed boundary thermodynamics.

`src/common/cloud_bal_column_physics.f90:2767-2867` uses real128 overlap/moment accumulation, conserves the declared dry mass, six species, and linear mixture enthalpy in the public float64 remap arrays, and only commits outputs after the residual gate. The canonical float32 casts have a separate post-remap check. This is numerical accounting evidence, not native total energy or scientific validation of the assumed profile/remap model.

### C. Internal phase budget and rollback — no defect found

`src/common/cloud_bal_column_physics.f90:2869-2916,2930-3052` accepts a caller-supplied water-conserving phase transfer, checks its finite-transfer enthalpy equation, accounts the stored float32 endpoint using the unchanged `dry_air_mass_measure`, and commits only once all selected cells and state validation pass. The budget reports water/enthalpy roundoff after storage; it does not call those residuals physical sources. Saturation adjustment is a separate state-changing path, and its thermodynamic/model basis should not be presented as a native KDM6 closure absent independent evidence.

## Targeted validation

Compiled from PR77 snapshot source in a new `/var/tmp/cloud_bal_audit12/team05/build.*` working directory using the verified Intel profile and `CLOUD_BAL_FREE_FLAGS` (`-check all -fpe0 -fp-model strict -no-ftz`):

- `test_pressure_domain_budget`: passed; covers activation, removal, opt-in rejection, missing newly active species, same-domain partial accounting, and independently computed endpoint masses/enthalpy.
- `test_pressure_domain_transition`: passed; covers the single-center transition, independent `A*ΔPS/g` pressure mass, full six-species extensive changes, enthalpy, geometry, and failed-input rollback to the original candidate with zero budget.
- `test_pressure_column_remap`: passed.
- `test_pressure_thermo_state`: passed; includes selected-cell transaction rollback and six-species budget checks.
- `test_pressure_phase_transfer`, `test_water_phase_transfer`: passed.
- `test_pr63_transition_replay.py` (13 tests), `test_pr69_water_budget.py`, `test_pr68_carrier_budget_replay.py` (7 tests): passed as parser/provenance/decomposition contract tests.

The Intel checked build emitted only array-temporary runtime warnings in test oracle routines; all six executables returned success. No GNU/gfortran or ifort was used. No full model or broad suite was run. The historical PR63/67/69 evidence was inspected, not re-run; the PR69 report notes its older receipt predates later stricter runner checks and that compile argv was not retained in the v6 build record.

## Graphify navigation and scope

Read the Graphify skill and its code-review reference. Queried the maintained KLAPS50 graph for `account_pressure_analysis`, pressure-domain mass/enthalpy accounting, and PR63/68/69 carrier tools; it located the expected source routines, tests, and evidence docs. The checked-in reports keep KLAPS50 and Cloud-BAL snapshots separate: KLAPS50 report is 34,375 nodes / 74,275 edges at `2026-10-08T10:05:49Z`; Cloud-BAL is 8,542 nodes / 15,847 edges at `2026-10-08T10:05:56Z`. Both identify selected PR72 overlay `2f27b3f` against `fd7e1be`; neither is a PR77 full extraction. The reports say cross-file Fortran call extraction is partial and native research source copies appear through evidence/patch files. No graph update was run in this read-only audit; graph deltas for PR77 are therefore unmeasured (not zero). Graph freshness is not runtime or scientific validation.

## Coverage inventory and exclusions

Reviewed: `cloud_bal_column_physics` water/pressure budget types and accounting, pressure-domain transition construction and mass/enthalpy checks, pressure-column remap, phase-transfer budget and rollback, geometry dry/pressure mass identities, PR63 transition replay parser, PR68 carrier decomposition, PR69 water capture/parser/geometry/process alignment and result limitations, matching tests and retained evidence.

Excluded: radar particle-process implementation outside its ledger interfaces, wind/mass solver, writer/output transaction, top-level pipeline orchestration, full KDM6 source kinetics, other host boundaries/timesteps/domains, operational comparison, and full model reruns. Those were assigned elsewhere or need separate native/scientific evidence.
