# PR73 constrained joint-analysis trial (2026-10-08)

## What this adds

> **Scope limit:** this is an estimator-to-endpoint-evaluator/writer/readback
> fixture. The writer's analysis-only branch requires pipeline and producer
> stage statuses to be `STATUS_FAILED / REASON_AUTHORITY` (blocked/unrun). It
> therefore does not yet support a production `run_cloud_bal_pipeline`-generated
> analysis candidate or establish producer-stage lineage.
> The focused component-contract reader passes, while the canonical standalone
> SHADOW diagnostic validator reports this artifact `INVALID/UNBOUND` and the
> candidate `REJECTED`; it is not an accepted SHADOW candidate.

`tools/pr73_joint_analysis.py` solves a small declared linear analysis problem
from independently supplied observation operator `H`, background covariance
`B`, observation covariance `R`, background state, observations, and analysis
change authority. It minimizes the standard quadratic background-plus-observation
cost subject to declared equalities and component bounds. The resulting
six-component increment is estimator-produced; it is not copied from the
candidate endpoint. The manufactured fixture includes a total-water increment
equality, bounds, synthetic wind/thermodynamic observations, and distinct zero
phase, external-source, and physical-boundary ledgers.

The Fortran `physical_joint_candidate_contract` now carries an optional,
identity-bound eight-component `analysis_increment` separately from source,
boundary, and internal phase increments. Physical endpoint accounting includes
all four increments. The canonical dry-air pressure-mass closure includes the
analysis water components, and the supported analysis dry-mass metric is
required to be zero. The NetCDF writer serializes the new analysis variable,
identity, and extension only when supplied; artifacts with no analysis payload
retain the previous zero-analysis interpretation. The independent validator
replays component and mass closure and rejects incomplete or malformed payloads.

The fixture connects the estimator output to canonical component calculation,
`evaluate_joint_candidate`, the SHADOW writer, and independent NetCDF readback.
It does **not** execute `run_cloud_bal_pipeline`; its test supplies an estimator
candidate to the endpoint evaluator. This is not evidence that the production
pipeline proposes such a candidate or that the candidate passes all production
stages. `READY_FOR_ENDPOINT_EVALUATION` means the manufactured estimate has
been connected to endpoint evaluation and artifact checks.
The SHADOW fixture artifact records `STATUS_FAILED / REASON_AUTHORITY` for
pipeline and stage status fields to show those stages were not run; the writer
accepts this explicit estimator-only status only alongside a passing physical
endpoint contract. It does not synthesize successful stage receipts. The
general publication validator remains a rejecting gate for this artifact.

## Mathematical and scientific scope

For state increment `x`, the solver uses the declared quadratic form

`J(x) = 1/2 xᵀ B⁻¹ x + 1/2 (H x - d)ᵀ R⁻¹ (H x - d)`

with declared equalities `C x = c` and box bounds. The fixture's observation
operator is manufactured, as are `B`, `R`, prior, observations, bounds, and
analysis-change authority. Its output is an algorithm check, not a real-data
analysis. The candidate changes vapor/cloud water and horizontal wind; it keeps
temperature and omega unchanged in this instance. Water equality conserves the
declared two-species analysis increment.

This is a constrained linear objective and endpoint contract check. It does not
establish full nonlinear positive-semidefinite moment feasibility,
thermodynamic consistency, precipitation-phase physics, dynamic mass/wind
balance, storm-motion relevance, or operational pipeline-stage lineage. The
broader atmospheric solution remains open. The analysis dry-mass component is
intentionally restricted to zero; nonzero analysis water that violates local
canonical pressure-mass closure is rejected. No actual 12 UTC / NE57 source,
boundary, phase, observation, or uncertainty authority is asserted here, and
this fixture confers no scientific or operational approval.

## Verification

- `python3 -m unittest tests/test_pr73_joint_analysis.py -v`: 12 tests pass,
  including scaled-unit invariance, lower/upper/fixed bounds, consistent
  redundant and inconsistent equalities, malformed covariance, infeasibility,
  and atomic failure behavior.
- `PR73_PROFILE=O0 tests/run_pr73_joint_analysis.sh`: pinned Intel O0 compile,
  estimator-to-endpoint-evaluator/SHADOW-writer fixture, NetCDF readback and
  corruption checks pass in a fresh `/var/tmp` directory.
- `PR73_PROFILE=O2 tests/run_pr73_joint_analysis.sh`: same checks pass with
  pinned Intel O2 flags in another fresh `/var/tmp` directory.
- `CLOUD_BAL_WORKSPACE_ROOT=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
  tests/run_real_shadow_io_contract_tests.sh`: existing focused SHADOW and
  physical-reader suite passes, including old no-analysis artifacts and the
  compatibility case that removes the complete analysis payload.

The compiler emitted Intel array-temporary warnings in the existing NetCDF
writer path; no test failed. The runner receipts are retained under
`/var/tmp/cloud_bal_pr73_joint_analysis.CmeKG7` (O0) and
`/var/tmp/cloud_bal_pr73_joint_analysis.uLf5LK` (O2) for this session. Their
hashes and source-file hashes are recorded in
`docs/evidence/pr73_joint_trial_receipt_20261008.json`; the generated estimator
output is retained in `docs/evidence/pr73_joint_trial_output_20261008.json`.
These scratch receipts are not a source-data provenance record.
