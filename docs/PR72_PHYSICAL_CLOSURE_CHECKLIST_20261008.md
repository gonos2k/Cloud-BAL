# PR72 physical closure checklist — 2026-10-08

Base: merged PR71 `3523fa7cddbf5641f86c8abc081c1479d3862352`.
PR71 was merged at `2026-10-08T02:42:38Z` (11:42:38 KST). Earlier open/unmerged publication text is historical. Overall physical approval remains **FAIL/OPEN**.

## Previous scoped closures retained

- Conservative process-fraction wording: closed in PR71; no global rounded-float maximum claim.
- All 18 `ProgB_param` outputs and explicit validity: closed within the selected-source contract.
- Defined native observer field and signed pre-NINT checks: retained; no rate cap, wider integer, or timestep workaround.

## Ordered work

| Priority | Item | Required evidence | Current status |
|---|---|---|---|
| P1 | Extreme ice rate source | One live first-rejected point: coefficients, QI/NI, all slope moments, both velocities/rates, density factor and thickness; source-bound identity and replay. | PASS_SCOPED: the live absent-ice point (lat2/i83/k7) reproduces the logged velocity/rate exactly from its captured operands; unassigned slope consumption is fixed. Historical i107/k5 is kept separate. |
| P1 | Ice/graupel branch independence | Ice slope assignments occur regardless of graupel absence; active formulas and absent velocities remain defined. | PASS_SCOPED: the PR71 nesting regression is corrected; O0/O2 poisoned-output and 3×3 nonunit-bound tests pass. |
| P1 | Number-velocity assignment order | Number-absence zero is retained for both rain and ice, with all active velocities unchanged. | PASS_SCOPED: rain/ice zero-number gates now follow the expressions; active ice ratio remains 4. |
| P1 | Exact absence and orphan states | Supported 0/0 states avoid undefined property operations; positive mass/zero moment and number-only states are not called absence. | PASS_SCOPED: 20 pinned Intel O0/O2 fixture runs cover declared clear/absent states and early rejection of orphan/negative/nonfinite input. Full process-domain closure remains OPEN. |
| P1 | Prior n0i failure attribution | Same source-bound EOS fixture on PR70, PR71, and fixed source; distinguish different earliest failures. | INVESTIGATED: PR70 and repaired source reject an infeasible moment trial; PR71 instead reaches an unset-slope divide. Prior inherited attribution is not supported. |
| P1 | Integrated native entry | Same input pretrace; one composed fixed source/object/executable; actual required pre/post endpoint. | REJECTED: ice-only repair reaches TRANSIENT; final combined source rejects unpaired positive mass before PSD work. Both preserve incoming pretrace; required post-call outputs are missing. |
| P1 | Freezing/tiny generation and extinction | Source-backed material/moment/thermal rules produce a state in the next property domain. | OPEN: 1000 kg/m³ freezing and 100–900 PSD domain remain incompatible; no invented density adjustment. |
| P1 | PBL/RK, water and energy | Same dry carrier, completed update, valid process and boundary terms. | OPEN; rejected calls provide no complete endpoint budget. |
| Parallel | Joint atmospheric candidate | Independent source/error/phase/moment/boundary/wind authority; feasible trial and readback. | Full-observation 12 UTC path BLOCKED; conditional fixed-wind phase baseline is separate. |
| Final | Initial shock and forecasts | Accepted identical candidate through WPS/real; fixed-setting BASE/HYDRO/COUPLED first call and 10/30/60-minute response plus independent observations. | NOT_RUN for an accepted joint candidate. |

## Delivery gates

- [x] Four-agent source, arithmetic, runtime identity and omission review.
- [x] Focused pinned Intel O0/O2 validation in fresh scratch, including poisoned outputs and active/absent transitions.
- [x] Preserve PR70/PR71 evidence, operational inputs, maintained native source and private profile.
- [ ] Commit, push and open the reviewed PR; no merge.
- [ ] Separate dated KLAPS50/Cloud-BAL Graphify overlays, derived wiki reports and audit log.

## Interpretation

The historical n0i receipt is not rewritten. New causal evidence corrects the earlier interpretation; a different earlier rejection is not a passing EOS fixture. Numeric safety, defined property interfaces, accepted local physical states, atmospheric balance and model time response remain separate gates. Fatal rejection does not promise rollback.

## Final source and evidence

The same combined research source has SHA-256 `1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819`. [Species validation](evidence/pr72_species_property_state_20261008.json) and [combined native rejection](evidence/pr72_combined_native_first_reject_20261008/receipt.json) bind it separately. The native run preserves all 100 staged inputs and pretrace `d2331e90…b9e7bb`, but returns 128 before required post-call capture. The strict pair rule changes research admission; it does not repair PBL/RK moment generation, freezing policy, water/energy balance, or provide rollback.

Python validation: six new declaration checks and two existing guarded-composer checks pass. The conditional single-cell phase/readback run uses pinned Intel O0; it is a repeat of the narrow background baseline, not a retained-observation or joint-wind candidate.
