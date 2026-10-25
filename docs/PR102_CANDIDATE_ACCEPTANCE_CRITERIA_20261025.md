# PR102 candidate acceptance criteria

## Scope and disposition

This note defines evidence gates for a bounded research candidate. It adds no
thermodynamic or wind physics and sets no new observation-error tolerance.
Source replay validity, descriptive response, observation skill, and physical
approval are separate outcomes. Existing PR101 evidence leaves physical
approval `FAIL_OPEN` and observation skill `NOT_EVALUATED`.

## Evidence authorities

| Question | Authority and use | Limit |
|---|---|---|
| What does the liquid adjustment do? | PR101's source-ordered observer records source `T,p,qv,qc`, liquid `qs`/RH, branch inputs, `work1`, `pcond`, `dtcld`, carried `xl`/`cpm` and their producer inputs, source transfer extent, and stored QV/QC/T changes. Source Fortran values and assignments govern. | Observer replay establishes the recorded source response and noninterference, not that a change is desirable or observation-preserving. |
| Which cells and columns are compared? | The receipt-bound PR99 composition artifact's `composed_qc_vertical_influence` and `composed_qc_source_links` define the original 613-cell QC support. The derived fixed five-cell Chebyshev buffer contains 196 horizontal columns across 39 native levels. | Preserve artifact identity, support, and buffer for all paired comparisons; do not choose a mask after seeing results. |
| Does the candidate improve observation fit? | Requires an authorized, matched observation `Y`, observation operator `H`, masks and coverage, and a declared uncertainty/covariance authority. | These are absent for this candidate. No sigma or covariance may be inferred from response spread, residuals, or algorithmic weights. Keep skill `NOT_EVALUATED`. |

Relevant records are `docs/PR101_CLOUD_THERMO_20261023.md`,
`docs/PR100_QC_PROCESS_20261022.md`, `docs/PR101_INTEGRATION_20261023.md`,
`docs/PR65_OBSERVATION_JOINT_PREFLIGHT_20261007.md`, and the PR99 fixed-support
composition artifact bound by `tools/pr101_projected_c2_response.py`.

## Candidate admission

Before a 640-second run, bind the raw COUPLED-minus-HYDRO wind increment,
continuous projected increment `P`, and candidate increment `N` on the same
native U/V faces and fixed carrier. Report the Euclidean velocity-space
distance budget

`Δ = ||(raw COUPLED − HYDRO) − P||₂`.

The research candidate must satisfy both `||N − P||₂ ≤ Δ` and
`Δ < ||P||₂`. Record component norms and units with the aggregate. This is a
bounded distance-to-projection policy only: without authorized covariance it
does not establish statistical optimality, physical benefit, or an observation
fit threshold.

Bind the projection premise independently: `P` must be the nearest feasible
Euclidean projection of `d` under the same `A` and fixed/exterior constraints.
In addition to checking `A P = 0`, verify the projection optimality condition
that `d − P` lies in the row space of the complete constraint operator. This
is required for the Pythagorean distance identity; feasibility alone does not
establish it. Apply the `||N − P||₂ ≤ Δ` gate to the final stored REAL32
readback as well as the continuous candidate.

Admission also requires receipt-bound prior norms, the declared native mass
constraint and solver residual, finite values, and checks after stored
REAL32 conversion. Verify unchanged non-U/V inputs and the actual source
consumer path. Reject missing or mismatched support, carrier, units, face
layout, source identity, failed constraint, non-finite values, or storage
that violates the declared bounds. These checks admit a research run; they do
not approve a forecast candidate.

## Thermodynamic and fixed-support response

Keep two states distinct: the incoming initial `T,qv,qc` in the model input,
and the internal `T,qv,qc` immediately before each source liquid adjustment.
The PR101 first-call cell `(i=136,j=17,k=11)` illustrates why: OFF enters at
liquid branch RH `0.82032` and evaporates, while COUPLED enters near RH `1.0148`
and condenses. These are arm-specific internal states and source outcomes;
they do not authorize suppressing evaporation or forcing cloud saturation.
Do not substitute an initial-input contrast for the state at the adjustment.

For the retained source replay, preserve the original assignments and report
each arm's absolute incoming adjustment state, liquid saturation state,
branch (`full` or `general`), request, bounded source extent, and stored
`ΔQV`, `ΔQC`, and `ΔT`. Partition QC-positive cells into evaporation,
condensation, and zero stored QC change, and separate zero-QC cells. Keep
source extent distinct from rounded stored deltas. Liquid saturation is the
source formula used in PR101, including below-freezing calls; it is not an
ice or mixed-phase saturation diagnostic. No preferred RH, phase direction,
or cloud amount is imposed as a pass condition.

For forecast response, compare receipt-bound PROJECTED/candidate and OFF,
HYDRO, and COUPLED histories at the common declared times using the unchanged
613-cell support and 196-column buffer. Report arm absolutes and candidate
minus-reference signed sum, RMS, L1, and maximum absolute difference for the
selected fields, levels, and times. Show incoming/pre-call contrast
separately from post-call response; keep staggered-face wind operators
distinct from destaggered history winds. No mask, time, level, or metric may
be selected because it favors the candidate. Existing PR101 response values
are descriptive and supply no pass cutoff.

## Outcome labels

| Outcome | Required evidence | Permitted conclusion |
|---|---|---|
| `PASS_SOURCE_REPLAY` | Source identities and event keys match; original stored assignments reproduce the captured returned fields; required source equations and storage checks hold. | The bounded source replay is internally consistent and noninterfering. |
| `DESCRIPTIVE_ONLY` | Receipt-bound fixed-support and buffer comparisons are complete with absolute arm values and paired differences. | Report the measured response, without a benefit or skill claim. |
| `NOT_EVALUATED` observation skill | No authorized matched `Y`, `H`, and uncertainty/covariance authority. | Observation skill remains unevaluated; do not replace missing uncertainty with an invented sigma. |
| `FAIL_OPEN` physical approval | Full physical budgets, source/boundary terms, and applicable independently authorized science gates are not closed. | No physical or operational approval. This is the current disposition. |

Passing source replay, candidate admission, or a 640-second execution does not
change the last two outcomes by itself. Report unresolved authority, closure,
or response items alongside every candidate result.
