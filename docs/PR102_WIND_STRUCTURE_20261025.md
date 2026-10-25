# PR102 native wind structure candidate design

## Frozen research policy

This branch contains the numerical solver, native geometry builder, synthetic
tests, and one actual-case research proposal. The proposal was generated from
the frozen HYDRO, COUPLED, and PR99 inputs. Its REAL32 candidate file remains in
the external generation scratch area; only the proposal receipt and bounded
generation records are archived in this repository. The candidate has no
physical approval, observation-skill result, or operational status.

Let `d=C-H` be the raw native U/V increment and let `bP` be the continuous
PR99 fixed-carrier projection for the same frozen carrier and control faces.
The optimization is

```text
minimize    ||G b||²
subject to  A b = 0
            b = 0 on exterior/fixed increments
            ||b-bP||₂ <= Δ - εstore,   Δ = ||d-bP||₂
```

`A` is the existing PR99 native dry-flux divergence operator. The velocity
norm is equal-face L2, the same control metric used by PR99; it is not a
background-error covariance or a kinetic-energy norm. The trust region is a
single global radius over all controlled U and V levels. For a continuous
feasible `b`, `bP` is the nearest feasible projection and
`||b-d||²=||bP-d||²+||b-bP||²`; with `||b-bP||₂ ≤ Δ`, this gives
`||b-d||₂ ≤ sqrt(2)*Δ` in continuous arithmetic. REAL32 storage does not retain
that exact feasibility identity; the stored candidate is checked separately
against the reserved storage bound and its declared consumer constraint. Require
`Δ < ||bP||₂` so zero is outside the trust region. `εstore` is computed before
solving from the maximum half-ULP error in the declared target REAL32 box and
the number of free faces; require `Δ-εstore > 0`. Recompute continuous `bP`
from the same `d`, verify
it matches the archived PR99 stored U/V bytes, and verify the final stored
candidate against the global budget after REAL32 conversion and the native
consumer replay.

Here `bP` in the trust/KKT equations is the continuous projection; `A bP=0`
describes that continuous solution, not bitwise REAL32 stored P. The archived-
byte check means converting the recomputed center to REAL32 reproduces the
stored PR99 P bytes. The stored-input geometry readback instead computes its
roughness and increment norms from actual stored H, P, and N. For this case,
the receipt records `||N_stored−P_continuous||₂ = 30.381125564760318`, versus
`||N_stored−P_stored||₂ = 30.381125727532083`; both round to 30.381126, below
the same frozen `Δ = 30.381336`. The trust check uses stored N against the
continuous center with its pre-reserved storage bound. The archived consumer
uses the final REAL32 candidate and passed its separate declared mass bound.
The receipt values come from
[`wrfinput_d01.proposal.json`](evidence/pr102_wind_structure_20261025/generation/attempt_03_success/wrfinput_d01.proposal.json).
These arithmetic distinctions do not imply physical approval.

`G` is a native-grid component roughness proxy: adjacent differences of U
among U faces and V among V faces, including links from free faces to the
fixed zero exterior. Horizontal face areas are `DX*DY/(MAPFAC_*X*MAPFAC_*Y)`;
dual volumes use that area and the adjacent-column average native layer depth.
Horizontal edge lengths use `DX` or `DY` divided by the average staggered
map factor, and vertical edge lengths use PH+PHB face-center heights from the
pinned promoted REAL32 gravity. Dividing by physical edge length gives
horizontal and vertical derivatives the same units. This operator is a grid
component roughness proxy, not a covariant momentum gradient, energy norm, or
statistically calibrated prior. The builder rejects nonfinite/nonpositive
metrics, nonmonotone heights, missing horizontal neighbors, and incomplete
geometry instead of substituting uniform spacing. No level-specific selection
or response-driven weights are permitted.

The trust-region multiplier is found as the dual root of the constrained
quadratic KKT system, not selected by scanning forecast outcomes. The solver
uses a sparse incidence-component reduction and matrix-free projected CG; it
does not construct a dense nullspace or global dense factorization. Its
admission check verifies both `A bP=0` and `d-bP∈range(Aᵀ)`, the latter being
required for the projection-distance identity. The candidate builder requires
the exact frozen policy hash, receipt-bound HYDRO/COUPLED/original-P inputs,
pinned gravity receipt, and PR99 support and parent hashes. It recomputes P,
checks its stored bytes, reserves a global REAL32 half-ULP margin before the
solve, and verifies the written candidate, nonwind arrays, stored distance,
cellwise A residual bounds, and source immutability. The storage margin may
not be repaired by changing the constrained candidate after solving. These
checks support a research proposal only; the archived native consumer and
source-capture checks are separate gates. The archived consumer completed
closed HYDRO and candidate calls and produced finite, correctly shaped output
with zero bottom and top faces. Those calls alone do not establish the
semantic dry-mass constraint result; the separately assessed
`reference_constraint` and `source_arithmetic` gates both pass for the exact
candidate in
[`assessment_receipt.json`](evidence/pr102_execution_20261025/archived_consumer/assessment_receipt.json).
Neither the consumer run nor these gates approve a model launch or physical
use.

## Actual-case proposal

The frozen policy was used for a single candidate-generation decision. Two
pre-write attempts failed and produced no candidate: attempt 1 rejected the
byte-identical PR99 composition mirror because its lexical path differed from
the old receipt path; attempt 2 rejected the stored-flux arithmetic bound. The
composition-path verification was corrected to allow only a hash-identical
relocation, and the FP64 bound was corrected with outward-rounded product
accumulation. Neither correction changed the physical policy, geometry,
weights, or candidate objective. Attempt 3 completed with unchanged frozen
policy and generated candidate SHA-256
`b26e5f3d712732c3459d59b82a4b44fe53eebd9be1fd450d13640d2d8398343f` and proposal
SHA-256 `451e4e9110d3b921507e311be56328ad05e13ee20e1fedd2d9c60ce8ef94eeb8`.
The candidate file is at
`/var/tmp/pr102_candidate_generation_v3_20261025/candidate/wrfinput_d01`; it is
not copied into this repository. The proposal receipt and the three attempts'
root GO records, execution records, and logs are in
[`generation`](evidence/pr102_wind_structure_20261025/generation/).

The proposal readback reports the equal-face increment norm decreasing from
101.143209 to 75.135313 m s⁻¹ (ratio 0.742861, or 74.286% retained increment
norm). This is not observation or physical-response retention. The stored
candidate N-to-continuous-P trust distance is 30.381125564760318 m s⁻¹; the
separate stored N-to-stored-P readback is 30.381125727532083 m s⁻¹. Both round
to 30.381126 m s⁻¹ and are below the frozen Δ of 30.381336 m s⁻¹. The
roughness functional decreases from 18,681,276.78 to 7,808,150.67
(ratio 0.417967). Since the fixed roughness operator is homogeneous, the
increment-norm ratio squared is 0.551842; the roughness-per-increment-squared
ratio is 0.757403, a further 24.26% reduction in this structure measure beyond
uniform amplitude scaling. This is a grid-structure diagnostic only; it does
not establish a causal forecast effect or observation retention. No second
candidate was created or tested.

The generation records bind the successful candidate to producer SHA-256
`f044c57605942504a0c8ece22b915e8bd64bc2ddacb46a9cecd6920081f15b85`, solver
SHA-256 `0ad9b38485b5d25f6fd70b3150688449e994665ffc6e16c5feb371c4ff3a35f5`,
policy SHA-256 `9ab0d468b9d46cce00fb9cc66162fa995beeda714f93cedba8c65d6e1891200d`,
and the recorded PR99 projection, PR94 support, and PR87 history-helper hashes.
The stored-input structural readback is
[`stored_input_structure_readback.json`](evidence/pr102_wind_structure_20261025/stored_input_structure_readback.json).

## Remaining gates

The closed HYDRO and candidate archived-consumer calls and their separate
input-reference and source-arithmetic gates pass over the fixed buffer's
7,840 vertical faces. This is the stored-input `calc_ww_cp` gate described in
[`assessment_receipt.json`](evidence/pr102_execution_20261025/archived_consumer/assessment_receipt.json),
with the preserved callee-compilation provenance limits; it is not the later
acoustic mass update or a physical balance approval. One-step/20-second HYDRO and
original-P source captures are complete. Their runtime noninterference check
matches all 30 selected T0 history arrays, the first POST_KDM6 trace record,
and all 17 returned KDM6 fields plus XLAND against the closed matched C2
controls. This is capture validation only. The comparison evidence is
[`hp20_capture_noninterference.json`](evidence/pr102_execution_20261025/hp20_capture_noninterference.json)
(SHA-256 `b41ad79bebfcaffea6ae86a89ca557c2ebcb08a52f6576e1db3d6f62aae85d44`).
The one-step candidate N comparison is also complete: BASELINE20_RUN on the
matched C2 executable and STRUCTURED_CAPTURE on the diagnostic overlay used the
same candidate, boundary, namelist, and launch environment. Their T0, first-20s
trace, and T1 post-call fields matched exactly. The N comparison report is
[`candidate_n20_capture_noninterference.json`](evidence/pr102_execution_20261025/candidate_n20_capture_noninterference.json)
(SHA-256 `c1e0468b6b23d55c08a69b0e0e2035ca1678a034767b03ffb77b71d14f46fd89`);
the closed-pair launch identity check is
[`n20_actual_launch_identity.json`](evidence/pr102_execution_20261025/n20_actual_launch_identity.json)
(SHA-256 `021e4c112b0a678d1612e679b9a9722823f4c99039cd5e8976e3e97fd2a0320a`).
The H/P controls also share a source namelist, matched boundary and launch
environment; their only 20-second namelist change is `history_interval`, while
the old 640-second control preflight diffs contain only duration/end-time and
history-interval changes. See
[`hp20_control_identity.json`](evidence/pr102_execution_20261025/hp20_control_identity.json)
for the pinned preflight and receipt details (SHA-256
`e64a20d90ee5f3f0e5c2e4eb4f9bbd345ed90b6f02a71b345067940f6e0f98fe`). These checks establish only
one-step capture noninterference for the compared fields. The first native
response is recorded in
[`PR102_RESPONSE_ANALYSIS_20261025.md`](PR102_RESPONSE_ANALYSIS_20261025.md).
The candidate's STRUCTURED integration completed all 32 steps over 640 seconds
with return code zero, no fatal lines, and unchanged staged and original inputs.
Its closed receipt is pinned by SHA-256
`313295e9cbf9e30a12a437c501bf3db2cf25c0e6762ec5d51c31d54ba311d4d6`; it binds
candidate input `b26e5f3d712732c3459d59b82a4b44fe53eebd9be1fd450d13640d2d8398343f`,
the matched C2 executable, boundary, and 640-second namelist. The closed
candidate run also passed the first-step prefix bridge against the same-input
base-C2 20-second baseline for T0, first-20-second trace, and T1 post-call
fields. The bridge is diagnostic noninterference evidence, not a response
acceptance test; its durations and namelists differ as intended. See
[`nbase20_prefix_bridge.json`](evidence/pr102_execution_20261025/nbase20_prefix_bridge.json)
(SHA-256 `e3ef62b6f9a2792434d3471005ec59b5f6a7441f377946500fd91cb64c598194`).

A five-arm saved-history readback is available for all 11 common times from 0
through 600 seconds on the frozen support and buffer. It is
`DESCRIPTIVE_ONLY`; observation skill remains `NOT_EVALUATED` and physical
approval remains `FAIL_OPEN`. The JSON readback is
[`fivearm_history_readback.json`](evidence/pr102_execution_20261025/fivearm/fivearm_history_readback.json)
(SHA-256 `d10f124bed615f0546594266971db263d6ba7db48ae3ee210e985f4c8c7db6b2`);
the execution manifest also pins its PNG and PDF products. The candidate and
policy were frozen before response analysis. This candidate-design report does
not determine response quality, observation skill, physical approval, or
operational use.

## Validation boundary

Synthetic tests check equality feasibility, trust-bound activity, independent
KKT stationarity, roughness reduction, zero exclusion, geometry dimensions,
horizontal boundary links, vertical physical spacing, bad metrics/heights,
REAL32 storage allowance, receipt generation, exact nonwind preservation, and
metadata/dimension/fill-value rejection. They do not establish actual-case
forecast response, observation skill, or science. Actual-case geometry, stored-P
identity, candidate generation, and the closed archived-consumer output checks
are recorded above. The initial stored-input consumer and one-step source-capture
results do not provide a 640-second POST_KDM6 trace analysis or establish
observation skill or physical approval.
