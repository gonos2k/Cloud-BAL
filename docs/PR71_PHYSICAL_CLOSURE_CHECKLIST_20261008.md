# PR71 physical closure checklist — 2026-10-08

Base: `0ef49d1770db6d9ed0d35f60e35dcbd5d3e0db15` (merged PR70).
Overall physical initialization approval remains **FAIL/OPEN**.

## Ordered gates

| Priority | Item | Completion criterion | Status |
|---|---|---|---|
| P2 | Fraction maximum claim | Describe conservative interval selection or prove maximum rounded-state fraction. | PASS_SCOPED: wording narrowed; neighboring valid float32 counterexample reproduced with pinned Intel O0/O2. |
| P1 | Defined particle outputs | Every `ProgB_param` return defines all 18 outputs and an explicit state status; all seven callers and consumers require applicable properties. | PASS_SCOPED: selected-source contract, seven-call consumer review and pinned Intel extracted routine/absence branches; no supported freezing policy implied. |
| P1 | Defined observer fields | Native stage-0 trace records an assigned current ice transport rate. | PASS_SCOPED: the default selected-source patch records assigned `mass_velocity_rate(:,:,4)`; historical legacy values remain untrusted. |
| P1 | Representable sedimentation step count | Reject nonfinite or out-of-integer-range arguments before `NINT`, without capping the physical rate. | PASS_SCOPED: signed-domain guard preserves representable legacy results; Intel O0/O2 boundaries pass. The integrated native first call rejects before unsafe ice `NINT`. |
| P1 | Ice fall-rate state | Trace the source parameters and moments that produce the measured extreme ice rates. | OPEN: final guarded call rejects at `(i=107,k=5)`, rate `8.29940373290303e8 s^-1`, `dtcld=20 s`. Trace moments, PSD parameters, terminal velocities and `DELZ` at that same point; no physical rate cap is authorized. |
| P1 | Generation→property domain | Freezing Q/B/heat transition produces a state supported by the next property model, with no invented density adjustment. | OPEN: source freezing density 1000 and PSD range 100–900 disagree; tiny transient is below the property gate. |
| P1 | Tiny generation/extinction accounting | Approve the same material, moment and thermal transfer at creation and disappearance. | OPEN: no source-backed replacement policy identified. |
| P1 | Integrated source execution | Unit conversion, common process limit and property validity use one selected source; test EOS-consistent state and native entry with exact lineage. | PASS_SCOPED integration evidence: one guarded source, Intel O0/O2 density and EOS-active fixtures pass; actual native call is REJECTED by integer-domain guard. Native physical acceptance remains OPEN. |
| P1 | Native water/energy closure | Same dry carrier, call time, domain, source/cleanup and boundary terms. | OPEN. |
| P1 | PBL/RK completed transport | Matrix, returned tendencies, actual RK reference and completed Q/N state share carrier and boundary accounting. | OPEN. |
| P1 | Ice diagnostic absence | The full module defines its ice intercept when the ice slope is zero. | OPEN: absence fixtures stop at an inherited `n0i` division; failed attempts are retained. |
| Parallel | Atmospheric joint candidate | Independent observations/background errors, source/phase authority, moments, wind and boundary conditions produce feasible trials. | Full-observation 12 UTC path BLOCKED; separately declared conditional development remains possible. |
| Final | Initial shock/forecast effect | One accepted candidate, fixed model settings, BASE/HYDRO/COUPLED first call and 10/30/60 minute response plus independent observations. | NOT_RUN for an accepted joint candidate. |

## Delivery gates

- [x] Four-agent review of implementation, source domains, integrated execution and evidence; no unresolved implementation blocker within this research scope.
- [x] Pinned Intel validation in fresh scratch; selected-source composition, native build/input identity and final artifact checks.
- [x] Preserve prior inputs, evidence, failed runs, maintained native sources and private profile; see final preservation receipt.
- [ ] Commit, push and open PR after scoped implementation blockers are resolved.
- [ ] Incremental separate KLAPS50/Cloud-BAL snapshots, derived wiki reports and audit log.

## Interpretation

Defined inactive output placeholders are not valid particle properties.
Validity must precede numerical use. A controlled fatal rejection prevents
publishing an invalid result but does not roll back already updated native
state or establish a supported physical transition. Manufactured module
acceptance, actual native rejection and accepted candidate time response are
distinct evidence.

The PR70 publication record was written while its PR was open. GitHub now
reports PR70 merged at `2026-10-07T23:56:21Z` (2026-10-08 08:56:21 KST).
That current metadata does not alter historical receipts or their source IDs.

## Next implementation batch

1. Reproduce the rejected ice point using its same-call QI/NI, density, PSD slope, terminal velocities and layer thickness. Resolve the equation or input-domain cause before selecting a physical substep policy.
2. Specify freezing creation and transient extinction with the scheme's material, moment and thermal transfer; then ensure every generated state is admitted by its next consumer. Keep the inherited zero-ice intercept division as a separate regression.
3. Re-run the composed source through the first call with valid pre/post state. Only then close dry-carrier water/energy and boundary budgets on that execution, alongside PBL/RK moment transport.
4. In parallel, construct a conditional joint atmospheric candidate from independently declared source, phase, background/observation errors, wind authority and boundaries. Deliver the identical candidate through WPS/real before BASE/HYDRO/COUPLED time-response comparisons.

No current native run supports water/energy closure or an accepted joint initial state. The guard terminates execution rather than restoring preceding updates.
