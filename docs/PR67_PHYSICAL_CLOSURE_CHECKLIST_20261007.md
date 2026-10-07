# PR67 physical closure checklist (2026-10-07)

Base: `3405d25aa62f0ebecd7e1b94a3915e7c1bb2aa6e`.
Overall physical approval remains **FAIL/OPEN**. A checked implementation or
replay item does not close the parent physical gate. Prior experiment receipts
and failed attempts remain immutable.

## Ordered gates

| Gate | Required evidence | Current status |
|---|---|---|
| PBL carrier | Capture the actual PBL invocation's native dry carrier, matrix, donor Q/N and returned rates. Compare `DEL` and dry-mass left invariants, then account for actual boundary and settling terms. | OPEN; same-call DEL/dry comparison now measured with STATIC_INPUT_LINKED hybrid coefficients. Dry left invariant and separate fog settling remain explicit. |
| Completed moment state | Evaluate Q/N/volume together after completed PBL, air advection, RK and process updates. Locate new violations with the same carrier and global support. | FAIL/OPEN; incoming negative QC and moment gaps remain. |
| Same-call water | Integrate the same call's six species and measured bottom precipitation, other boundary fluxes and numerical cleanup. Establish whether accumulators represent totals or subsets before summing. | OPEN; PR67 captures bottom fall and identifies an ice-speed normalization defect. Residual remains +6.53e6 kg and both research candidates fail output safety. |
| Same-call energy | Derive the selected scheme's energy measure and include phase transfers, precipitation enthalpy, cleanup and host coupling terms. | OPEN; `TH*PII` is temperature, not an energy budget. |
| Observed joint candidate | Independently admit radar analysis/error/source, internal phase exchange, moment policy, boundary authority and a justified wind prior; generate a feasible nonzero candidate with observations retained. | BLOCKED on admission inputs; no valid observed omega target–sigma pairs in this case. |
| Native handoff | Bind that same candidate through WPS, metgrid, real, initialization and the first physical call. Verify the consumed units, carrier, geometry, moments and actual wind representation. | OPEN for an admitted joint candidate. |
| Initial response | With identical settings compare BASE/HYDRO/COUPLED at the first call and 10/30/60 minutes, including observed cloud/rain/ascent preservation. | NOT RUN for a valid joint candidate. |

## This batch

- [x] Measure the actual PBL carrier and test both left invariants on one
  source-bound research invocation.
- [x] Establish a source-bound path for same-call precipitation and cleanup
  capture; preserve a separate uninstrumented control.
- [x] Inventory the available joint-input admission path without endpoint-derived
  source arrays or invented wind uncertainties. The 12 UTC observed candidate
  remains BLOCKED; the separate 13 UTC model-target API compatibility passes.
- [x] Fix large integer-mask reads that exceeded the ordinary 8 MiB stack;
  validate the reader in fresh pinned-Intel O0/O2 builds.
- [x] Protect the scratch model-target derivation from existing output and
  source aliasing; preserve the original artifact.
- [x] Review the resulting changes independently with the agent team, fix
  findings and validate the affected paths.
- [ ] Freeze reviewed source and push/create the PR directly after validation.
- [ ] Update separately dated KLAPS50 and Cloud-BAL Graphify snapshots and
  derived KG reports against the frozen commit, then publish the metadata.

## Interpretation rules

- A `DEL` invariant is a pressure-weighted invariant. It becomes a native
  dry-mass invariant only after the actual source relationship is established.
- Internal matrix solutions, returned mixing-ratio rates and completed host
  mass-coordinate updates are different states and require separate evidence.
- The PR65 shared-PBL experiment and the earlier donor-control budget use
  different research stacks. Their results cannot be combined into one budget.
- Common air mixing and differential sedimentation have separate equations.
  Activation, collision and extinction retain their process-specific number
  rules; overall particle number is not universally conserved.
- No moment floor, output substitution, endpoint-to-source copying, posterior
  tolerance increase or damping change constitutes physical closure.
- Source labels and graph freshness do not authenticate physical authority or
  establish runtime/scientific validation.

## Evidence added by this batch

- [Same-call PBL carrier](PR67_PBL_SAMECALL_CARRIER_20261007.md): DEL differs
  from linked dry pressure by up to 1.86%; static hybrid coefficients and
  reused host objects limit source closure. Matrix, returned rates and fog
  settling are separate measurements.
- [Completed negative-QC replay](evidence/pr67_negative_qc_completed_boundary_20261007.md):
  all 23,494 first-call incoming negative cells reproduce their completed
  binary32 update. First appearances are RK1/RK2/RK3: 21,441/1,139/914.
  Invalid per-process channel captures are excluded; no process correction is
  justified by this aggregate replay alone.
- [Same-call KDM6 budget](PR67_KDM6_SAMECALL_BUDGET_20261007.md): post-rain
  slope refresh left ice fall speeds in m/s where the first ice loop consumes
  per-layer rates. Research-only normalization substantially reduces the
  measured storage loss. Both ice-only and combined candidates are **REJECTED**:
  26 and 25 reflectivity NaNs respectively. The combined 25 coincide with
  positive rain mass and zero rain number. No production patch is enabled.
- [Joint-input admission and mask reader](PR67_JOINT_INPUT_ADMISSION_20261007.md):
  large integer masks now read by vertical slabs under the ordinary 8 MiB
  stack. Fresh pinned-Intel O0/O2 actual reader evidence is retained. The
  separate 13 UTC model-origin target passes API compatibility; the 12 UTC
  full observed physical candidate remains BLOCKED.

## Next actions and closure criteria

1. Bind the selected PBL carrier coefficients to a compatible live host layout;
   derive a dry-carrier mixing equation, including boundary and separate
   settling terms. Test the completed host update before enabling a change.
2. Capture trustworthy process terms for completed negative-QC updates and
   locate the 25 rain-number defects in the rejected combined experiment.
   Preserve Q/N/volume together without floors or output substitution.
3. Reconcile hybrid and sedimentation carriers, numerical extinction, bottom
   fall and all other water terms. Derive energy terms separately; the measured
   residual cannot be declared arithmetic tolerance without a bound.
4. Admit independent radar errors, analysis/source/boundary declarations,
   moment policy and exact-time wind prior. Generate the full observed feasible
   trial without deriving authority from its endpoint.
5. Only after a valid candidate, connect native consumption and identical-setting
   BASE/HYDRO/COUPLED time responses and independent observations. Keep all
   unsupported and failed gates visible until their own criteria pass.
