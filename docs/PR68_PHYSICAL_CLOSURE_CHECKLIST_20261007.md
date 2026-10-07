# PR68 physical closure checklist (2026-10-07)

Base: `920c7048bc7376347aefed7eaef3ae50ee3946a9` (PR67).
Overall physical approval remains **FAIL/OPEN**. Implementation, replay,
runtime identity and physical acceptance have separate completion criteria.
Previous failed candidates and receipts remain immutable.

## Ordered work

| Priority | Item | Completion criterion | Current status |
|---|---|---|---|
| P1 | Velocity and transport units | Keep mass/number terminal speeds in m/s; derive rates in s⁻¹ at every sedimentation refresh; verify distinct speeds, repeated PSD calls, nonuniform thickness and halo indexing. | PASS_SCOPED: Intel O0/O2 helper and source wiring pass; fresh matched O2 strict native products are byte-identical. O3 differs and remains separately recorded; existing physical failures persist. |
| P1 | Rejected rain state | Locate the first completed process that creates the 25 positive-rain/zero-number states using source-bound captures, final mass/number and actual process rates. | PASS_SCOPED: 300 neutral source checkpoints locate all 25 first violations at the cold aggregate number limiter/update; 12 negative and 13 zero accepted number trials retain positive rain. Conservative coupled correction remains OPEN. |
| P1 | Host/internal moment units | Bind the source and runtime density conversion between host number/kg and internal source-required number/m³; compare the same boundary in readback. | OPEN: inspected driver and wrapper pass the number field directly, while internal PSD equations require volumetric number. No density conversion was found in those source paths; driver source/object lineage remains partial. |
| P1 | Coupled process acceptance | Derive process-specific mass/number/volume/energy transfers and constrain the accepted final particle state on the same carrier; account for source-defined number creation/destruction. | OPEN. A number limiter alone does not ensure positive rain has a realizable number state; no isolated sink patch is admitted. |
| P1 | Completed negative QC | Capture trustworthy changes across RK physics, scalar transport/diffusion, diabatic addition and boundary handling; reproduce the actual completed update and distinguish RK reference from current state. | PASS_SCOPED for source-bound boundary capture: 23,494 targets; neutral completed states and all 102 live inputs verified. RK1 aggregate PBL/CU and diffusion increments are separated; individual process/face-flux causes remain OPEN. |
| P1 | Carrier and water accounting | Express storage, bottom flux and numerical/process terms on declared same-call measures. Separate carrier conversion and reduction-order differences from physical sources. | PASS_SCOPED for algebraic reconciliation: about 4.62e6 kg carrier choice and 0.186 kg global reduction correction; about 1.91e6 kg remains unresolved. All 101 live declared inputs rehashed. |
| P1 | PBL dry carrier | Bind actual dry carrier, matrix/RHS, returned tendency, completed host update and surface/fog boundary terms. | OPEN; total-pressure DEL is not the dry measure. No one-line replacement or posterior rescaling. |
| P1 | Same-call energy | Derive native energy measure and include phase, precipitation enthalpy, cleanup, pressure work and host coupling. | OPEN; temperature change is not an energy budget. |
| P2 | All transported moments | Pair moments for species actually mixed by air; keep activation, collision and differential sedimentation equations separate. | OPEN beyond the scoped QC/NC research path. |
| P2 | Observed joint candidate | Independently declare radar errors/analysis, phase freedoms, moment policy, boundary authority and justified wind prior, then find a feasible candidate with observations retained. | BLOCKED on admission inputs for the 12 UTC case. A wind-fixed path still needs the other declarations. |
| Final | Native response | Bind an accepted candidate through WPS/metgrid/real and compare BASE/HYDRO/COUPLED first call and 10/30/60 minutes under identical settings and independent observations. | NOT RUN for an accepted joint candidate. |

## Review and publication

- [x] Finish source-bound unit, rain and completed-QC investigations; preserve unsuccessful attempts.
- [x] Cross-review implementation, arithmetic, capture identity and evidence with the agent team.
- [x] Address findings and run affected tests; report focused and whole-wrapper results separately.
- [x] Freeze reviewed changes, push the branch and create [PR #68](https://github.com/gonos2k/Cloud-BAL/pull/68).
- [x] Update separately dated KLAPS50 and Cloud-BAL Graphify snapshots and KG derived reports/log from the frozen source commit.
- [x] Review and publish the metadata follow-up; dated-copy correction passed two independent reviews.

## Interpretation rules

- Different research patch stacks are different candidates. A new observer must
  demonstrate neutrality before its process attribution is accepted.
- Speeds, per-layer rates and Courant coefficients have distinct units and
  lifetimes. Mass and number fall speeds need not be equal.
- Hybrid dry mass, PBL total-pressure DEL and local DEND×DELZ have different
  source definitions. A change of integration measure is not water creation.
- The remaining water residual is not an arithmetic tolerance. Endpoint
  subtraction and cellwise reduction differences are reported separately.
- Particle number is not universally conserved. Process-specific number
  creation/destruction must remain consistent with the final particle state.
- No moment floor, clipping without accounting, output replacement,
  endpoint-derived source, posterior tolerance increase or damping change
  establishes physical acceptance.
- Graph extraction and graph freshness do not establish runtime or scientific
  validity. Retained host objects limit full compiler/source closure.

## Frozen validation evidence

See [focused validation](evidence/pr68_focused_validation_20261007.json),
[team review](PR68_AGENT_TEAM_REVIEW_20261007.md),
[velocity/rate contract](PR68_VELOCITY_CONTRACT_20261007.md),
[rain-process origin](PR68_RAIN_PROCESS_ORIGIN_20261007.md),
[completed QC](PR68_COMPLETED_QC_20261007.md), and
[carrier reconciliation](PR68_CARRIER_RECONCILIATION_20261007.md).

The registered focused checks pass: 21 new Python tests, 3 prior default-path
regressions, and the pinned Intel O0/O2 rate helper/source wiring. The full unit
suite is NOT_RUN. These counts are separate from the matched native research
runs; their process completion does not approve their invalid particle states.

Graph/KG follow-up: [separate snapshots and limitations](PR68_KG_FOLLOWUP_20261007.md).
