# Team07 estimator and inverse-problem audit — 2026-10-12

Source snapshot: `scratch/pr77_native_state_20261012/Cloud-BAL`, base `9701ef23f04576d875508a0882d0e0af67282587+PR77`.

## Result

No incorrect optimum, physical mapping error, constraint acceptance error, or false KKT pass was reproduced in the declared small, well-conditioned manufactured fixture class. The estimator is explicitly an algorithm fixture. Its provenance IDs are required labels, but do not authenticate evidence or prove that an optimum came from an authorized real-data source.

One valid but very ill-conditioned SPD case is rejected fail-closed. This is a numerically unsupported class, not a wrong answer. Two larger gates remain open: there is no spatial producer that constructs and binds a real-data optimum, and scientific/operational evidence remains absent.

## Reproduced numerical limitation — P3

At [pr73_joint_analysis.py:74](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/pr73_joint_analysis.py:74), `_solve` treats pivots at or below `1e-13` of the matrix maximum as singular. A two-state probe with `B=I`, `H=I`, no constraints or bounds, `y=[1,0]`, and `R=[[1,1-1e-14],[1-1e-14,1]]` has valid positive-definite `R`, but `evaluate` returns `NUMERICAL_FAILURE: declared linear constraints and state bounds have no certified face` at the face solve ([line 645](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/pr73_joint_analysis.py:645)). The exact Gaussian minimizer is `(I+R)^-1 y`, approximately `[2/3,-1/3]`; changing correlation to `1-1e-13` succeeds. The solver emits no bad candidate. If this covariance class is in scope, define a condition envelope or use a more stable solver and independent high-precision check.

## Contract and authority review

`evaluate` requires separate `H`, `B`, `R`, background-prior, and analysis-change `evidence_id` fields ([lines 466–472](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/pr73_joint_analysis.py:466)). It accumulates phase, external-source, and physical-boundary increments separately before optimizing ([lines 474–493](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/pr73_joint_analysis.py:474)). Covariance diagonal scales normalize control and observation units before the precision-form objective and equality reduction ([lines 575–601](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/pr73_joint_analysis.py:575)). Box faces are enumerated, candidates are checked against original equalities and bounds, and the selected endpoint must pass normalized KKT residuals ([lines 603–684](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/pr73_joint_analysis.py:603), [lines 693–791](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/pr73_joint_analysis.py:693)). The output keeps the analysis increment separate, records the objective and fit, and sets `scientific_approval=false` ([lines 792–840](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/pr73_joint_analysis.py:792)).

The optional fixture adapter maps float32 temperature and six water species into component order 1–8 using pressure mass measure and specific enthalpy; it requires all separate process increments be zero ([lines 388–438](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/pr73_joint_analysis.py:388)). `READY_FOR_ENDPOINT_EVALUATION` means a manufactured endpoint can be presented to the physical endpoint evaluator; it does not confer producer, authority, or scientific approval.

## Open gates

- **Spatial generation and optimum authority — P1 gate:** the fixture tool declares itself non-operational ([line 4](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/pr73_joint_analysis.py:4)); PR77 describes the common inlet as assessing an externally estimated endpoint, with no spatial reconstruction or real H/B/R authentication ([PR77 progress, line 8](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/docs/PR77_INTEGRATION_PROGRESS_20261012.md:8)). Next check: construct, authenticate, and bind one common spatial endpoint and follow it through the same-candidate handoff.
- **Scientific evidence — P1 gate:** the tool emits `MANUFACTURED_ALGORITHM_TRIAL`, `scientific_approval=false`, and does not assess physical closure ([lines 809–830](/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL/tools/pr73_joint_analysis.py:809)). PR77 records canonical validation `UNBOUND/REJECTED`, science assessment false, rejected native candidates, and open real-data handoff. Next check: close those PR77 evidence gates on the same authorized candidate.

PR76's degenerate-corner/multiplier defect is considered fixed; its focused cases pass and it is not listed as unresolved.

## Validation, coverage, and exclusions

`python3 -m unittest tests.test_pr73_joint_analysis tests.test_pr74_independent_oracle -v`: **28 tests passed**, including 396 signed scalar-box cases, the six-variable covariance-form oracle, partial and common unit rescaling, authority declarations, bounds, equality rank/reduction, KKT certificates, and CLI output preservation/atomic writes.

Graphify was queried first. Its maintained 1499-node graph returned related constraint/covariance/operator references but did not directly surface the estimator Python file; source review supplied that missing link. No graph update was made because no code changed. No native or broad pipeline run was repeated; root reports related regression checks passed. No source/input/evidence files were changed. See `audit.json` for the machine-readable findings and exact trigger/expected/actual/next-check records.
