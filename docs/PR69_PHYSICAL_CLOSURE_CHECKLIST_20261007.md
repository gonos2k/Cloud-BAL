# PR69 physical closure checklist (2026-10-07)

Base: `40d9fe58bab6504806db66c4a5063c3cd17a1bd0` (merged PR68).
Scientific approval remains **FAIL/OPEN** until the same candidate satisfies the required gates. Previous failed native candidates and immutable receipts remain separate evidence.

## Ordered work

| Priority | Item | Completion criterion | Status |
|---|---|---|---|
| P1 | Host/internal number basis | Bind initializer, host storage, call adapter, density definition and time, then test number/kg ↔ number/m³ with source-bound executable and nonunit densities. | PASS_SCOPED for the selected-source dual-density prototype: 92 field comparisons at dry densities 0.25/0.5/1/2 and invalid output guards. The wrapper-only diagnostic remains FAIL_OPEN; qi0, native integration and historical host object closure remain OPEN. |
| P1 | Coupled accepted processes | Map each process to donor/receiver mass, particle number, bulk volume and thermal transfer; approve common process extents subject to the full final state, then recheck stored values. | PASS_SCOPED for source-extracted Intel O0/O2 common process fractions and stored Q/N/BG/T checks. The fresh native attempt is REJECTED: nonzero graupel mass process rate at zero bulk density makes its volume transfer unsupported, before the fraction gate. Number-only limiting and floors do not satisfy this gate. |
| P1 | Same-call water | Connect carrier-bound stored species, phase, cleanup, sedimentation and bottom flux; distinguish carrier choice and reduction arithmetic from actual process residual. | MEASURED_OPEN; the neutral source-carrier-equivalent ledger separates +2,126,112.845 kg entry QC cleanup, −3,398.492 kg mixed sedimentation, +104.240 kg first ice substep and −210,704.495 kg remaining evolution. These measured terms do not establish energy or whole-model closure. |
| P1 | Native energy | Establish the scheme/host energy definition and same-call precipitation enthalpy, pressure work and coupling terms. | OPEN; TH×PII alone does not establish energy closure. |
| P1 | PBL dry carrier | Derive matrix, RHS, returned tendency, completed host update and boundary/fog terms on the same dry mass measure. | OPEN; no posterior rescaling or blind DEL substitution. |
| P1 | Negative QC | Trace complete RK numerator, initialized process tendencies and face fluxes, with actual RK reference and current carrier. | OPEN beyond PR68 boundary capture. |
| Parallel | Observed feasible candidate | Keep observations and independently declare errors, analysis/phase increments, moment policy, boundaries and selected wind authority. | BLOCKED on independent admission declarations for the 12 UTC case. Wind-fixed authorization removes only the wind-change gate. |
| Final | Native acceptance and time response | Use one accepted candidate through WPS/metgrid/real, first microphysics and fixed-setting BASE/HYDRO/COUPLED at 10/30/60 minutes with independent observations. | NOT_RUN for an accepted joint candidate. |

## Interpretation rules

- Exact-arithmetic zero number with positive mass is a structural inadmissibility; increased precision cannot repair it.
- A source moment bound, a PSD rate diagnostic and an activation threshold are distinct conditions.
- Common accepted process quantities must reach all related mass, number, volume and latent terms. Particle number is not universally conserved.
- Air mixing and differential sedimentation require their respective physical fluxes; their moment speeds need not coincide.
- Dry density, total density, carrier and time must be explicit at every basis conversion. A density-one test cannot establish the bridge.
- Do not admit a rejected state with a floor, clipping without accounting, output substitution, residual-derived source or enlarged physical tolerance.
- Research source copies and retained host objects limit runtime claims; graph freshness establishes navigation only.

## Review and publication

- [x] Complete the scoped source-bound prototype and investigation; preserve draft mapping failures and the corrected native rejection separately.
- [x] Review bounded-source process math, units, conservation, provenance and stored acceptance with the agent team; scientific and native gates remain separate.
- [x] Validate affected paths with pinned Intel in fresh scratch and 12 focused Python tests; full suite is not claimed.
- [ ] Commit, push and create the PR after scoped implementation review passes.
- [ ] Refresh separately dated KLAPS50/Cloud-BAL graph/report/manifest snapshots and derived wiki audit from the frozen implementation; review metadata.

## Admission order and remaining evidence

1. Resolve number basis and density roles before interpreting PSD bounds physically. Preserve the direct-copy control and mixed-carrier failure; do not hide the original strict-O2 reference exception.
2. Verify source-connected donor/receiver mass, number, bulk volume and latent updates from the same accepted process fractions. A research run with unsupported volume transfer or no feasible fraction is `REJECTED`; fail-fast rejection does not imply a rollback-capable model API. The corrected run rejects nonzero `pgdep` with zero `rhox` before evaluating the fraction helper. Printed tiny-QI states are additional diagnostic conditions, not the exercised rejection branch.
3. Reconcile stored water and bottom export on each declared carrier. Promote each float32 snapshot before subtraction. The neutral source-carrier-equivalent endpoint residual is about +1,912,114.151 kg; the five-checkpoint reduction gives +1,912,114.113 kg. Their approximately 0.038 kg arithmetic difference does not explain the unresolved source-measure residual. Passed DEN is moist gas density while declared mixing ratios use dry air; these source-measure kg values are not yet a physical dry-carrier water budget.
4. Derive dry-carrier PBL and completed RK/transport updates, including boundaries and numerical cleanup. Same-matrix mixing alone is insufficient, and the remaining negative-QC states need independent process attribution.
5. Admit one observed candidate with independently declared errors, sources, phase authority, moment prior and boundary conditions. Wind-fixed studies may proceed within their own scope; they do not supply missing radar-analysis declarations.
6. Verify that same accepted candidate through WPS/metgrid/real and native first call, then compare unchanged-setting BASE/HYDRO/COUPLED at 10, 30 and 60 minutes. Include cloud/precipitation observation fit and the native energy budget.

No single percentage represents these gates. A scoped parser/helper/serialization pass is retained independently of native rejection, unsupported physics and unrun response tests.

## Evidence map

- [Coupled source update](PR69_COUPLED_PROCESS_20261007.md): common fractions, current-rate BG mapping, source-extracted stored endpoint checks and native attempts.
- [Unit basis audit](PR69_UNIT_BASIS_AUDIT_20261007.md): selected-source dual-density research tests and unresolved host/energy semantics.
- [Same-call accounting](PR69_NATIVE_WATER_BUDGET_20261007.md): neutral source-carrier-equivalent ledger; not a physical dry-water or energy closure.
- [Agent-team review](PR69_AGENT_TEAM_REVIEW_20261007.md): implementation findings and their resolutions.
