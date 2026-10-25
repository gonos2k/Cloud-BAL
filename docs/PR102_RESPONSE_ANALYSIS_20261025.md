# PR102 STRUCTURED response analysis

`tools/pr102_response.py` is a reader for a closed `STRUCTURED` C2 640-second
run. It compares the candidate with the four receipt-pinned controls: OFF,
HYDRO, COUPLED, and the existing projected P run. It also reads the completed
one-step H/P/N source-capture cohort bound by the PR102 execution preflight.
The analyzer must only be invoked after the STRUCTURED receipt is complete and
its preflight and source artifacts pass their hash and identity checks.

## Response products

- Saved host history is compared at all common saved times from 0 through 600
  seconds on the original 613-cell QC support and the fixed 196-column,
  five-cell Chebyshev buffer. It reports per-arm RMS and paired candidate minus
  control signed sum, RMS, L1, and maximum absolute difference for pressure,
  geopotential, perturbation potential temperature, moisture fields, and
  destaggered U/V/W. The derived pressure and geopotential and destaggered
  winds follow the existing PR86/PR101 readers.
- The native POST_KDM6 trace is a separate 640-second measurement. It compares
  selected captured steps through step 32 for Q/QC/QI/QR/QS/QG on the same
  frozen support and buffer; it must not be described as host history.
- The H/P/N source-capture comparison reuses the PR98 native RU/RV/MUDF reader.
  RU and RV remain staggered native source-coordinate tendency diagnostics.
  MUDF is the captured native combined DMDT+MU_TEND output; the MU update
  divided by its captured timestep is checked against MUDF descriptively, with
  no invented pass tolerance. Separately, `pr99_native_mass_effect.column_mass_rate`
  converts each arm's captured MU change using that same input's C1H, DNW, map
  area, captured timestep, and pinned gravity on the fixed 16 support columns.
  It requires the H/P/N map area, C1H, DNW, and captured step size to match,
  and records the shared-geometry hashes. The report retains absolute H/P/N
  kg/s-per-column rates and their paired
  differences. It records the nonzero HYDRO baseline without treating it as a
  threshold. RU/RV and dry-column mass rates have different units/stages and
  are never combined into one norm or interpreted as acceleration, energy, or
  continuity closure.

The H/P/N aliases mean HYDRO, original projected P, and new candidate N source
captures. They are not the PR98 OFF/HYDRO/COUPLED forecast arms. The four 640-
second control labels remain OFF/HYDRO/COUPLED/P.

All comparisons are descriptive. The tool fits no thresholds or masks to
candidate response. It does not evaluate observation skill: no authorized
matched observation Y, operator H, and error/covariance authority is bound.
Physical approval remains `FAIL_OPEN`; observation skill remains
`NOT_EVALUATED`.

## Closed first-native H/P/N source capture

The receipt-bound one-step source assessment is closed and recorded in
[`first_native_response.json`](evidence/pr102_execution_20261025/first_native/first_native_response.json)
(SHA-256 `9fc8117c5dd46d625ec77d318d5ba8f50d58abb900d457417929bf1708fa6a98`).
The aliases are H = HYDRO, P = original projected, and N = candidate. The
assessment covers the first captured native source calls during a run that
completed one 20-second model timestep. The raw source snapshots do not encode
an RK ordinal; its placement is inferred from pinned source call order.

| Fixed-support diagnostic | H | P | N | Units / interpretation |
|---|---:|---:|---:|---|
| Physical dry-column rate L2, 16 column values | 17,899,337.373 | 15,276,840.849 | 16,298,636.853 | Each component is a native-column rate in kg/s; L2 aggregates the 16 rates and is in kg/s. Actual MU change uses each arm's captured timestep and shared area/C1H/DNW/gravity. |
| Raw assembled RU L2, 769 values | 24,361.966 | 37,999.028 | 30,302.067 | native staggered source-coordinate operator units |
| Raw assembled RV L2, 769 values | 23,908.715 | 33,199.724 | 28,311.700 | native staggered source-coordinate operator units |

N's dry-column-rate L2 is 6.69% above P and 8.94% below the nonzero H
baseline. This is a descriptive fixed-column response: it does not establish
continuity closure or physical approval. RU/RV are earlier source-coordinate
momentum diagnostics with different units and stages; they are not divided by
initial mass or merged with the later dry-column rates. The result is not an
acceleration or forecast-improvement claim.

For the same 16 columns, the paired dry-column-rate distances are:

| Pair | L2 distance | Signed sum of paired difference |
|---|---:|---:|
| P−H | 6,405,258.249 | −2,885,040.119 |
| N−H | 2,999,229.557 | −1,838,670.966 |
| N−P | 3,443,113.388 | +1,046,369.153 |

Each component of the paired vectors is a native-column rate in kg/s. The L2
distance and signed sum aggregate the 16 values and are in kg/s. These
distances and the absolute H/P/N norms describe proximity to the declared,
nonzero HYDRO baseline on those 16 columns. H is a reference state, not a truth
field; neither a smaller absolute norm nor proximity to H ranks response
quality or establishes observation skill.

The frozen-input geometry readback
([`stored_input_structure_readback.json`](evidence/pr102_wind_structure_20261025/stored_input_structure_readback.json),
SHA-256 `f5a3baaefce2046c700b7ef3c91459a7968dcb869d5cb7fd2e713bc89fdb6a4a`)
defines free-face increments `bP_stored = P_stored − H_stored`,
`bN_stored = N_stored − H_stored` and the homogeneous geometric functional
`R(b) = ||G b||²`. On those same free faces,
`R(bN_stored)/R(bP_stored) = 0.417967` (58.203% lower), while
`||bN_stored||/||bP_stored|| = 0.742861` and the squared-norm ratio is
`0.551842`. The normalized roughness ratio
`[R(bN_stored)/||bN_stored||²]/[R(bP_stored)/||bP_stored||²] = 0.757403`
describes structure beyond the uniform amplitude scale. These are input-
geometry descriptors, not an observation score or a causal decomposition of
the native forecast response. The stored displacement
`||N_stored − P_stored|| = 30.381125727532083` is below the declared budget
`Δ = 30.381336`; this readback does not supply a statistical-optimality claim.
These readback symbols denote actual stored REAL32 inputs, distinct from
continuous `bP` in the trust/KKT algebra, where `A bP=0` is the ideal
continuous equality, not a bitwise property asserted for stored P. The trust
check compares stored N with continuous recomputed P using the pre-reserved
storage bound; the archived consumer used final REAL32 data and passed its
separate declared mass bound. The receipt records continuous-center distance
`30.381125564760318` versus stored-P distance `30.381125727532083`; both round
to `30.381126` ([proposal receipt](evidence/pr102_wind_structure_20261025/generation/attempt_03_success/wrfinput_d01.proposal.json);
stored-P distance is from the linked stored-input readback above). The
source-response comparison still uses the frozen support and buffer, with no
response-selected mask or threshold.

### Predeclared buffer source diagnostics

The same closed H/P/N 57-file captures were also compared on the already
defined 39-level, 196-column buffer (7,644 mass cells), using the pinned
native face-union reader. The RU/i-face and RV/j-face unions each contain 8,190
values on this mask. Values below are equal-cell unweighted L2 norms in their
native coupled-tendency units. Increment columns mean P−H, N−P, and N−H.

| Buffer source field | H | P | N | P−H | N−P | N−H |
|---|---:|---:|---:|---:|---:|---:|
| Assembled RU output | 37,114.851 | 47,852.954 | 41,573.423 | 31,535.636 | 12,147.425 | 20,205.104 |
| Assembled RU output−input | 2,079.663 | 27,551.097 | 17,791.309 | 27,485.439 | 10,391.746 | 17,685.940 |
| Assembled RV output | 37,693.182 | 45,347.306 | 41,343.748 | 28,826.267 | 9,987.895 | 19,591.772 |
| Assembled RV output−input | 2,260.169 | 21,609.449 | 14,958.444 | 21,486.755 | 7,090.144 | 14,782.248 |
| Horizontal U diffusion output−input | 219.648 | 27,221.385 | 17,508.599 | 27,233.294 | 10,296.186 | 17,523.747 |
| Horizontal V diffusion output−input | 95.328 | 21,292.345 | 14,650.241 | 21,288.082 | 7,024.252 | 14,645.673 |

The mask was fixed before candidate evaluation and contains 196 columns,
including the 16 columns touched by the original 613-cell support. Face counts
are staggered-union counts, not 196-column counts. These buffer diagnostics
extend source-coordinate coverage; they do not generalize the physical
dry-column rate beyond its declared 16 support columns. Full pin and metric
detail is in
[`first_native_buffer_response.json`](evidence/pr102_execution_20261025/first_native_buffer_response.json)
(SHA-256 `2d9854dd6a6f00f782dbf0ac3ff35239a914bd5b594822e050d5908f2e66a566`);
its preserved external reader is `/var/tmp/pr102_first_native_buffer_20261025.py`
(SHA-256 `92b3696d8a54a4a2410b657accc7a65be6bb05fa704da6fbe594eafd73b0df57`).

## Closed 640-second five-arm history response

The matched `STRUCTURED` C2 integration closed at 32/32 steps and 640 seconds
with return code 0 (run-receipt SHA-256
`313295e9cbf9e30a12a437c501bf3db2cf25c0e6762ec5d51c31d54ba311d4d6`). The
frozen final-v2 five-arm reader completed after the separate root GO. It
compares actual `STRUCTURED`, P, HYDRO, COUPLED, and OFF histories at all 11
common saved times from 0 to 600 seconds on the fixed 613-cell support and
fixed 196-column buffer. The report and execution are
[`fivearm_history_readback.json`](evidence/pr102_execution_20261025/fivearm/fivearm_history_readback.json)
(SHA-256 `d10f124bed615f0546594266971db263d6ba7db48ae3ee210e985f4c8c7db6b2`)
and
[`execution.json`](evidence/pr102_execution_20261025/fivearm/execution.json)
(SHA-256 `cfb54c75dfd6d6b6e101a98a7f24e7ecd3b3cd1beba1d949c03ec7d5a7ddcd9d`);
the reviewed GO is
[`root_postclosure_go.json`](evidence/pr102_execution_20261025/fivearm/root_postclosure_go.json).
The four-panel
[`PNG`](evidence/pr102_execution_20261025/fivearm/fivearm_history_response.png)
and
[`PDF`](evidence/pr102_execution_20261025/fivearm/fivearm_history_response.pdf)
show the RMS differences for the fixed support and buffer at every saved time.
The independent readback review is
[`fivearm_independent_review_20261026.md`](evidence/pr102_execution_20261025/fivearm/fivearm_independent_review_20261026.md)
(SHA-256 `175c32fdd8ee6605ebbbfa7384a1455829e69d31abd9315b58b85bc7cb167fe7`).

At 600 seconds, the support RMS values below are for each arm minus actual OFF.
N is lower than P by the shown percentages, but remains above HYDRO H in all
four fields:

| Field | H | P | N | N vs P |
|---|---:|---:|---:|---:|
| Pressure (Pa) | 4.241214 | 5.701822 | 4.941320 | 13.34% lower |
| Geopotential (m²/s²) | 4.439463 | 11.106138 | 8.790352 | 20.85% lower |
| W (m/s) | 0.112018 | 0.219394 | 0.166380 | 24.16% lower |
| QCLOUD (kg/kg dry) | 2.2861×10⁻⁵ | 3.2713×10⁻⁵ | 2.4990×10⁻⁵ | 23.61% lower |

This endpoint is not uniform over time: at 60 seconds, N−OFF RMS is 9.13%
higher than P for geopotential and 0.23% higher for W. On the 196-column
buffer at 600 seconds, N−OFF RMS is lower than P by 10.58%, 8.24%, 20.68%,
and 11.98% for pressure, geopotential, W, and QCLOUD respectively. N is above
H for the first three buffer fields, while buffer QCLOUD is below H (1.0534×10⁻⁵
versus 1.1157×10⁻⁵ kg/kg dry). These are descriptive RMS differences against
OFF, not observation scores or quality rankings.

The initial QCLOUD contrast against actual OFF is bitwise identical for H, C,
P, and N on both fixed masks, and is nonzero (initial contrast RMS: 1.25094×10⁻⁴
kg/kg dry on support and 3.54247×10⁻⁵ on buffer). At 600 seconds, the cosine of
each arm's QCLOUD contrast with its own initial contrast remains negative:

| Region | N | P | H |
|---|---:|---:|---:|
| Original support | −0.15249 | −0.38319 | −0.09225 |
| Fixed buffer | −0.10244 | −0.29660 | −0.05353 |

The candidate's lower QCLOUD RMS difference than P does not indicate
preservation of the initial QCLOUD contrast. These cosine and projection
diagnostics are fixed-pattern summaries from `pr94_cloud_response.pattern_metrics`,
not Pearson correlation or observation skill.

The frozen full-response analysis is complete and published as
[`response.json`](evidence/pr102_execution_20261025/closed_response/response.json)
(SHA-256 `c336cbf5ede5a19f073f0ce195ee928c1daa4074fe7dafe817e2734fdfb04ebf`),
with a COMPLETE, return-code-0 execution record
([`execution.json`](evidence/pr102_execution_20261025/closed_response/execution.json),
SHA-256 `5ebefc02d93a117c4ae9e8318a6a02542df7697aeaf17153d1ab7ab7526bfa45`)
and a COMPLETE_DESCRIPTIVE_ONLY publication record
([`publication.json`](evidence/pr102_execution_20261025/closed_response/publication.json),
SHA-256 `a90286c734c97c21be5178783fdf61c19f11094e9b3db6da876a7db93cb8bb4a`).
The candidate-minus-OFF count, RMS, maximum absolute value, and signed sum
agree exactly between the full-response report and final-v2 five-arm report
for all 11 saved history times, four shared fields, and both fixed regions
(88 comparisons; zero mismatches). The 0–600 second host history is distinct
from the POST_KDM6 source trace at 20, 60, 300, 320, 480, 500, 600, and 640
seconds. The first-source section covers H=HYDRO, P=original projected, and
N=candidate captures, 57 files per role; dry-column kg/s rates and raw
staggered RU/RV norms remain separate quantities and match the published
first-native assessment. The bounded independent check is recorded in
[`fivearm_independent_review_20261026.md`](evidence/pr102_execution_20261025/fivearm/fivearm_independent_review_20261026.md).
This is a GO for report scope, coverage, provenance, and cross-reader
consistency only. Physical approval remains `FAIL_OPEN`; observation skill
remains `NOT_EVALUATED` because no authorized matched observations, operator,
and uncertainty/covariance authority are bound.
