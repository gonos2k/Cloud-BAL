# PR89: shared process-consumer admission and repeated native consumption

## Frozen scope

The review base is merged PR88 main `f1809781e8be49e063de6728a85374a4ebcc334f`.
V50 OFF/COUPLED 60 seconds and three KDM6 calls remain the preserved
`PASS_SCOPED` reference. Its failed 600-second attempts are not rewritten.
The latest research candidate is **PR89-C5**; C1, C2, C3, C4 and V50 receipts remain
separate. The setup is one domain/rank/thread/tile,
with the same initial Q/N/B, boundary inputs, prior, precision and FP policy.
Selected objects are rebuilt under the pinned Intel O2 strict reproduction
profile in fresh scratch; this is a partial host, not a clean whole-WRF build.

## Shared predicate and coupled packet

The original strict NG rain branch is factored into one small module procedure,
`kdm6_rain_ng_pair_valid`. Full NG admission and the freezing transaction call
the same branch with the same binary64 bounds, coefficient values and operation
order. Its zero/paired semantics and reason codes 3/6 remain unchanged.
The full validator retains its cloud/ice checks, temperature checks, graupel
density support and pending-state policy. Ice's existing 8-ULP policy at
completed-state audits is not broadened.

At PFRZ, the transaction validates only quantities it changes: rain mass and
internal volume number, graupel mass and specific bulk volume, and stored
absolute temperature. It reuses the existing ProgB density predicate. Later
stage2 PSD reconstruction can legitimately update untouched cloud/ice number;
the freezing gate does not incorrectly move the full NG check ahead of that
stage. Full NG admission still runs at its original consumption boundary.

The original capped integrated proposals are held fixed. A bounded common
halving retry calls the existing packet helper on local candidates. If its
internal fraction is theta and the outer scale is gamma, the reported global
fraction is gamma*theta for mass, number and volume. Heat is computed from the
same approved mass, converted in the original REAL32 storage order, and checked
before all QR/NR/QG/BG/T stores commit together. Exhausted trials explicitly
defer the whole packet and leave all stored fields and approved amounts
unchanged/zero. This bounded search is not an exhaustive feasibility or
maximal-fraction proof. NR clipping, density/cap changes, new floors and NG
permission widening are not used.

## Source-pinned T4 regression and focused validation

The test binds the actual OFF T4 ledger gzip and its unique `(i,call_lat,k,loop)
= (26,115,18,1)` packet, verifies its recorded after-state REAL32 bits, and
executes the **transformed production call block** with the exact appended
packet helper and shared consumer procedures. It reproduces the old full
packet's reason-6 conflict; the new transaction defers this packet with all
approvals zero. A separate nonzero packet commits and passes the unchanged
full downstream validator. Zero proposals, invalid graupel, invalid cloud and
wrong/nonfinite temperature are checked at Intel O0/O2 in fresh scratch.

The retained amounts are source-capped integrated `pfrzdtr/nfrzdtr`, not the
uncapped primitive rates before `dtcld` and donor MIN. No raw-rate capture is
claimed. Latent storage rounding remains a separately auditable numerical
change; this test does not establish enthalpy closure.

The [focused receipt](evidence/pr89_process_contract_20261019/review/focused_validation.json)
binds 43 passing focused tests plus the original joint transport program at
Intel O0/O2, the pinned profile, ten maintained source/test hashes and logs. The
[independent packet review](evidence/pr89_process_contract_20261019/review/pr89_packet_contract_independent_review_20261019.md)
is separate from actual host execution.

## Existing inactive-ice contract at the host boundary

C1 passed the former T4 failure and exposed a different T5 source-only ice
candidate at native indices `(i,j,k)=(151,187,37)`. The rejection label says
`GRAUPEL_TRIAL_REJECT`, but pair 2 maps to QI/QNI. Its candidate is
`Q=4.246248455315979e-22 kg/kg dry`, `N=1.9903235415769328e-6 /kg dry`.
The active mean-particle-mass ratio is about 18% below its minimum. This is
neither an 8-ULP boundary case nor underflow: actual full NG admission accepts
it under the existing positive inactive-ice rule
`Q <= REAL(NEAREST(1.e-14,-1.0),real64)` with positive number, while generic
joint storage rejected it. The source-derived Intel replay and provenance
are retained in the [T5 audit](evidence/pr89_process_contract_20261019/review/pr89_t5_ice_consumer_contract_20261019.md).

C3 introduced that exact existing limit only for pair 2 through the shared
candidate, storage and diagnostic gates. The default remains the old active
PSD policy. Finite/nonnegative, exact absence, positive partner and
representable volume-number conditions remain required. Pairs already valid under the original continuous PSD predicate retain the
original storage path, including its declared numerical quantum-absence and
rounding repairs. Only a pair rejected by that predicate but accepted by the
existing inactive contract enters the additive fallback: it stores the two
rounded REAL32 values directly with adjustment 0, rejecting zero rounding or
failed unit representation. That fallback does not invoke Q repair, quantum
erasure, an N floor or clipping. Above the limit, active PSD checks apply. Positive inactive limits cannot override strict bulk-density or
volume-number contracts. No new physical cutoff is introduced.

The V50 host source embeds its own joint transport module. The hash-bound
transform replaces that body with the exact reviewed maintained module
before updating the host call sites. The native build compiles this complete
prepared source; modifying only a separate repository module would not have
changed the executed implementation. The regression chains the joint
update, actual transformed pair-2 certifier call and actual full NG consumer;
its test and [independent review](evidence/pr89_process_contract_20261019/review/pr89_ice_contract_c3_review_20261019.md)
retain active/default, invalid, orphan, rounding and unit-underflow controls.
The T5 candidate and coupled source RHS use captured hexadecimal values;
computed REAL64 candidate bits are checked before conversion. The density
`0.1140736_real32` is an explicit positive adapter from the rounded full-state
record: exact RK1 density bits were not captured. The separate T5 PRE_RK
observer value is not substituted. This is a source-form contract replay, not
an exact whole-cell input replay.

This harmonizes an existing intermediate-state contract; physical activation,
growth, count reconstruction and conservation still require evaluation.

## Current process and existing-history diagnostics

The [cold summary](PR89_COLD_SUMMARY_20261019.md) records current NG/AUT/G
proposal/applied/deferred water-vector activity after the final composite
factor. It does not enable the multi-GB primitive ledger. Actual DEN*DELZ
weights give **kg m-2 SUM_COLUMNS**, not grid-area/global kg: KDM62D has no
horizontal area argument. This half-L1 group-vector measure is not individual
reaction throughput or latent-heat suppression. Legacy header-only ledgers
remain NOT_EVALUATED; incomplete compact call records are rejected.

The [matched V50 history comparison](PR89_HISTORY_DIAGNOSTICS_20261019.md)
uses actual same-position T0/T60 arrays, per-arm temporal and cross-arm carrier
identities, and a fixed T0-derived 27-column water-increment support. That support
is descriptive analysis support, not independent observation validation. Actual
pressure/Phi/staggered-wind changes and computational-grid differences are
reported with their spatial and temporal limits. These are not momentum,
continuity, water or energy closure claims. Historical v17 process suppression
and first-call local residuals are not copied into C1 results.

## Native execution

The same C1 executable completed four KDM6 calls and the first 80 seconds in
both matched 120-second requests, passing the former T4 freezing-to-NG failure.
Both closed receipts are `INCOMPLETE`, return code 1: the fifth timestep stops
at the joint moment candidate validator before the next KDM6 call. The candidate
build and staged/original inputs remain unchanged. This is an audited completed
prefix, not a successful 120-second execution. The new failure is being
localized from its stored operands. A 600-second attempt remains conditional
on completing the repeated 120-second consumer test. C2's first implementation of the inactive branch caused a regression: it
intercepted an already PSD-valid underflow pair before the existing joint
quantum cleanup. Both attempts stopped after 20 seconds. Its source, tests,
receipts and audit are preserved; this is not reclassified as a new host error.
C3 restores the old valid-pair flow and adds the inactive path only as fallback.
The C3 executable
`ab8ff2312b8cb8cd65a44b78801d2938367f6e8793148d2ed1211479fe04ff97`
closed both attempts as `INCOMPLETE`, return code 1, after four completed
steps (80 seconds). It passed the prior T5 positive representable inactive
pair but stopped at another pair-2 candidate `(i,j,k)=(188,220,1)` whose
Q/N both round to zero in REAL32. The continuous number-volume check rejected
it before the declared joint-quantum storage policy could classify stored
absence. C3 source/test pins and its frozen archive remain preserved.

C4 adds only an explicit representation case: with a positive inactive limit,
the existing joint-quantum-absence option, finite positive Q/N, valid density
and ratio configuration, and both REAL32 rounds exactly zero, store 0/0 and
record adjustment 3. The full signed Q/N losses use the existing caller
ledger. The positive continuous validator is unchanged, as are default and
legacy-valid storage. A one-zero result, invalid configuration, active mass,
strict-mass/volume contract, or disabled option cannot use this case. This
is recorded numerical representation, not physical sublimation or a new
PSD tolerance. C4's pinned Intel partial-host build passes; executable SHA-256 is
`5c7f6ff646d4867e4e21194d071a12db9bfad6ad4ef303d7d3bc75fd150268a4`.
Both C4 120-second attempts closed as `INCOMPLETE`, return code 1, after
80 seconds. The next rejection is the same inactive-ice column at k=2:
Q64=`1.5521916836884197e-60` rounds to zero, while
N64=`1.1916375247192763e-44` rounds to nine minimum REAL32 subnormal units.
The C4 both-zero rule does not cover this orphan representation. Its 80-second
prefix and source/test archive are preserved.

The [C5 design review](evidence/pr89_process_contract_20261019/review/pr89_ice_contract_c5_design_review_20261019.md)
examines a shared numerical error envelope for this class: when Q rounds to
zero, permit a declared joint-absence store only if N carries no more than
one REAL32 minimum mass quantum under the existing minimum particle mass.
This count bound is derived from source coefficients and storage precision,
not a new physical prior or number floor. Full signed losses remain numerical
ledger terms. C5 implements this as a fallback only when the prior canonical predicate
fails. It rounds the derived count cap one REAL64 ULP downward, preserving a
conservative one-mass-quantum upper bound. Legacy-valid storage and its old
quantum handling remain unchanged. The regression covers the exact fatal k=2
payload, the safe cap and next value above it, and all 11 printed ICE candidates;
[fixture provenance](evidence/pr89_process_contract_20261019/review/c5_full_fixture_check.json)
checks those literals against the SHA-bound ledger without promoting their
printed decimals to exact runtime bits. Exact signed-loss/rollback controls
remain separate from physical-phase accounting.

The pinned Intel C5 partial-host build passes; executable SHA-256 is
`beb2da6745606566074e15a043d173a8be01d277f00c4cc90ad3915f5de5a2d6`.
Both matched 120-second attempts are **COMPLETE**, return code 0, with six
completed KDM6 steps and unchanged staged/original inputs and executable.
The same C5 executable and inputs are now running the matched 600-second
requests. Those long-window outcomes are pending; no completed 600-second
claim is made before CLOSED receipts. Current [120-second receipts](evidence/pr89_process_contract_20261019/manifest.json)
bind the closed window separately from the ongoing 600-second attempts.

The [paired output projection](evidence/pr89_process_contract_20261019/native/c5_600s_resource_plan.json)
uses each completed 120-second run's measured raw and other output bytes,
scales by 600/120 and a factor of three, and totals 305,012,053,365 bytes against
581,977,018,368 available bytes. This is an engineering estimate, not a proven
upper bound; separate run directories, space monitoring and the unchanged
per-run historical disk gates remain in use.

The [G diagnostic review](evidence/pr89_process_contract_20261019/review/pr89_graupel_t5_contract_20261019.md)
distinguishes initial direct-store diagnostic failures from the existing strict
source-witness fallback. Rounded FULL text alone does not establish a runtime
cone violation or fallback failure; no G bound or precision is changed.

The independent C1 audit found no completed T4 strict cloud/rain/graupel
violations and no active ice pair beyond the retained 8-ULP cone. Two positive
ice pairs lie outside that active cone but below the actual native inactive
mass threshold; applying an active-only diagnostic to them is a policy
mismatch, not proof of an active PSD violation. The first step matches V50
bitwise; the second step first differs at POST_KDM6 in a few stored cells,
with propagation at step three. C1 changes packet admission, so later
first-60-second identity is not asserted.

Water/energy closure, native mass-wind compatibility, independent observation
agreement and initial-shock reduction remain **OPEN / FAIL_OPEN**.

The [13 UTC observation audit](evidence/pr89_process_contract_20261019/review/pr89_observation_source_gap_20261019.md) verifies available input products but records the missing native-history-to-pressure-grid operator. The 162-cell prehost analysis support and 27-column outcome-selected native support are not substituted for one another; no independent observation-fit claim is made.

## Review provenance

The [C3 integration review](evidence/pr89_process_contract_20261019/review/pr89_final_integration_review_20261019.md) covers the C3 ten source/test pins and its preserved 43-test receipt; C4 source/storage reviews are separate: [C4](evidence/pr89_process_contract_20261019/review/pr89_ice_contract_c4_review_20261019.md), [C5](evidence/pr89_process_contract_20261019/review/pr89_ice_contract_c5_review_20261019.md). The preserved `pr89_final_code_review_20261019.md` is the earlier C1 six-file, 42-test review; its historical filename does not identify the latest validation. C3 inactive-ice review and closed native audit are separate evidence.

The final Python whitespace cleanup is bound in [generation equivalence](evidence/pr89_process_contract_20261019/review/c4_generation_equivalence.json): regenerating both native sources from the final tools reproduces the frozen C4 inputs byte-for-byte. Build-time generator hashes refer to the preserved preformat archive; the focused receipt binds the final formatted tools. The core, native source files and executable were not changed after build.

The [C4 completed-prefix audit](evidence/pr89_process_contract_20261019/review/pr89_c4_completed_audit_20261019.md) binds both closed 120-second requests to four completed steps. Each corresponding C4/C3 stage trace has the same compressed SHA-256, and the decoded comparison found no field mismatch through 80 seconds. Strict cloud/rain/graupel checks pass in the completed states; both generic active-ice cone outliers at T4 lie below the native inactive limit. This does not establish an active PSD violation or a successful fifth call.
