# PR90: internal rain admission and persistent storage

## Current candidate

| C7 window | OFF | COUPLED |
|---|---|---|
| 180 seconds | COMPLETE, 9 KDM6 calls | COMPLETE, 9 KDM6 calls |
| Same-executable 600-second request | INCOMPLETE after 180 seconds, rc=1 | INCOMPLETE after 180 seconds, rc=1 |

The 600-second requests fail in the timestep-10 host joint-moment candidate
check, before a tenth completed KDM6 call. This is a newly exposed host
transition; the T7/T8 rain rejection is not the recorded fatal. The exact
closed receipts, prefix comparison and failure classification are retained
separately from the completed 180-second baseline. Physical approval remains
`FAIL_OPEN`.

## Preserved reference

The base is merged PR89 `3bc7bb8df6a100b60c6f8908ad93a7c3d981f360`.
C5 OFF and COUPLED retain their completed 120-second, six-call
`PASS_SCOPED` receipts. Their incomplete 600-second attempts are unchanged.
The initial moment files, boundary inputs, priors and FP policy remain the
reference. Selected-object pinned Intel builds are partial-host research
configurations, not clean whole-WRF builds.

## Exact T7 classification

A diagnostic-only OFF request for 140 seconds completed the same first six
steps and stopped at the same `(timestep,j,i,k)=(7,222,193,4)` rain rejection.
The independent comparison found all 49 completed-prefix stage records
bitwise identical to C5 OFF through 120 seconds. This validates that prefix;
it does not establish FP status-flag neutrality of the diagnostic prototype.

The failure is **at the paired-store helper's internal-volume precheck**,
before that helper's division, joint storage, directed-Q correction and
next-call reconversion. The wrapper's earlier scalar
`volume_number_to_specific` call already succeeded. The precheck rejects
the original internal pair's lower bound, with helper stage 4 and core
stage −1.

| REAL32 input | Hexadecimal word | Exact promoted value |
|---|---|---:|
| QR, kg/kg dry | `308D0490` | 1.0260396976491393e-9 |
| NR, m⁻³ | `38AB5008` | 8.168822387233377e-5 |
| Dry density, kg/m³ | `3F904AFD` | 1.1272884607315063 |
| pidnr | `4644597C` | 12566.37109375 |
| Power | `40400000` | 3 |
| Minimum slope, m⁻¹ | `44704000` | 961 |
| Maximum slope, m⁻¹ | `4708B800` | 35000 |

The unchanged source predicate computes the lower number bound as
`8.168823412280135e-5 m⁻³`; the internal number is approximately
`1.0250467588992541e-11 m⁻³` below it. Both pinned Intel O0/O2 source-form
replays reproduced all twelve diagnostic REAL64 words exactly. These are
ordinary normal values, not a new subnormal/FTZ diagnosis. The existing
directed-Q storage path was not reached and is not replaced.

The [D1 archive](evidence/pr90_rain_roundtrip_20261019/d1/manifest.json)
binds the closed run, preflight, build, replay and exact compiled procedure
extracts. The prototype performed extra diagnostic conversions on accepted
calls; subsequent diagnostics defer those probes until rejection. Its
physical prefix equality is measured, while no claim of identical sticky
FP flags is made.

## Producer investigation

The D2 archived producer trace and warm ledger locate the first invalid
internal rain PSD. At the selected T7 cell, QR is `308D048E` immediately
before the warm commit and `308D0490` immediately after it; NR remains
`38AB5008` across the commit. The trace/ledger packet cross-checks the warm
state and producer boundaries, and the unchanged number falls below the
original internal PSD's lower number bound after that commit. The public
wrapper's `volume_number_to_specific` conversion had already succeeded. The
paired-store helper then rejected its own internal-volume precheck before
reaching that helper's division. The D2 run receipt remains `INCOMPLETE`:
steps 1–6 completed, then step 7 stopped at `(222,193,4)` with return code
128. See the [D2 target packet](evidence/pr90_rain_roundtrip_20261019/d2/t7_target_packet.json)
and its [bound run receipt](evidence/pr90_rain_roundtrip_20261019/d2/run_receipt.json)
(SHA-256 `a25df40c099f4475d30c11ea8bb2ffea4b4bd4b289a68e357d7e02fb7e6b3503`).
This identifies the producer boundary where the invalid pair first appears;
it does not authorize an NR floor, clipping, tolerance change, or storage
repair.

The separate C6 experiment tests a selected-object warm-packet
output/admission contract. The earlier warm-output tool source beginning
`10d8dc5…` is not a physical-source pin; the bare C5-to-warm transform output
is SHA-256
`732510e4b3e9aa83654452aafb10ef717037457c10cf40d328287f8a767868be`. C6 is
bound to its [archived source and closed-run manifest](evidence/pr90_rain_roundtrip_20261019/c6/manifest.json)
(SHA-256 `a04153886d70c656f91d4e0dda8afd4198711c14fd083ce82c76d56f20c54186`),
which records exact-byte copies of the source manifest, partial native build
receipt, and both arm preflight/run receipts; see the independent
[archive verification report](evidence/pr90_rain_roundtrip_20261019/c6/archive_verification.md).
The source manifest SHA-256 is
`95a239a529d06c8fed9f464f243eff20ab6424620da9457285ed1cb081b0195b`; the
build receipt SHA-256 is
`2b663971a0b9040c8ea7f157ede2e7c529373d7df23263fe443684d1160b7515`. The
compiled KDM source is `c4e7c9ceaf61d346556b5fe1d1ce52a4c2e9a1d224ed7d28dc1180c90db0186c`
and includes the column overlay. The manifest scopes this as warm-packet
output admission, with no initial-input, prior, or FP-policy change, while
the native overlay metadata marks `physics_changed: true`. These bindings
describe a design experiment, not physical validation or an unchanged
physical candidate.

C6 OFF and COUPLED both reached 140 seconds, passed the previous T7 failure
location, then stopped at the timestep-8 paired-store internal-volume
precheck with return code 128. The new failure is at
`(timestep,j,i,k)=(8,222,188,5)` with QR `3481DDEF`, NR `3C9BEEF8`, and dry
density `3F8E9DE1`; the exact diagnostic and receipt-bound RSL excerpt are in
the [C6 failure excerpt](evidence/pr90_rain_roundtrip_20261019/c6/failure_excerpt.md).
Both run receipts are `INCOMPLETE`, with seven completed steps. This records
that the prior T7 trigger was passed and that a new lower-bound miss remains;
it does not claim the warm-packet change is successful. Keep C6 separate from
the D2 producer diagnosis and preserved C5 history.

## C7 final PSD experiment (180-second pair complete)

C7 adds a final KDM6 rain-number reconstruction at the exact R64 PSD endpoints,
after the source's final `NR > nrmax` cap and inside the original active-rain
cutoffs. It reuses the existing PSD boundary helper, updates the `lamdr_tmp`
boundary cache, and makes no arbitrary NR floor, mass, or heat edit. At the
captured T8 pair, the R32 slope is `44704006`, strictly between the existing
slope limits, so the old lambda checks do not fire. The isolated pinned-source
fixture binds all seven input words to the C6 OFF replay JSON (SHA-256
`e084d1738cc14a5efe1c581975502f967ecb7464602fa011295e5626c61196b4`) and the
receipt-bound C6 capture. The fixture also forces an upper-bound miss through
the final `nrmax` cap; both repaired pairs pass public store, restore, and the
shared NG consumer under Intel O0/O2.

These are source-level reconstruction tests. The C6 failure occurred at the
paired-store internal-volume precheck before public store, restore, or NG, so
the full model's first producer of the T8 pair is still unknown. The final
correction owns a deterministic PSD-bound reconstruction: its NR change is not
evidence of physical nucleation or a physical water-budget term.

The [receipt-bound T8 event](evidence/pr90_rain_roundtrip_20261019/c7/science/psd_t8_event.json)
also connects the actual internal correction to persistent storage in both
completed 180-second arms. At `(timestep,lat,i,k)=(8,222,188,5)`, internal NR
changes from `3C9BEEF8` to `3C9BEEF9` m⁻³. The actual `POST_KDM6` public tuple
is QR `3481DDEF`, specific NR `3C8BF3B3` kg⁻¹, dry density `3F8E9DE1`.
The independently streamed stage payloads verify both arm tuples. The public
specific number and internal volume number have different units; this local
event does not establish a complete number budget.

The C7 partial overlay build reports `PASS_OVERLAY_BUILD` (not a clean
whole-model build); its build receipt is at
`/var/tmp/pr90_native_build_c7_20261019/pr87_native_overlay_build.json`,
SHA-256 `7a58ac2ae90eca9ffe0500515282b537e11db25ab9de8175856609bf812bba31`.
The executable SHA-256 is `5f5599e38759a9e2be27a9e7e0977370592c92cab328062d07eb359bddd19572`;
the compiled KDM source SHA-256 is
`983095a0aa0c76eab4efdda27f9435e61634e08e542ef9bd096aa4cf8004eca4`.
Both 180-second arm receipts now report `COMPLETE`, return code 0, and nine
model timestamps through `2026-08-16_13:03:00`. The exact preflight/run receipt
copies and hashes are archived in [C7/180](evidence/pr90_rain_roundtrip_20261019/c7/180/README.md);
the source/build metadata is in the [C7 build record](evidence/pr90_rain_roundtrip_20261019/c7/README.md).
The [independent C7 runtime audit](evidence/pr90_rain_roundtrip_20261019/c7/runtime/README.md)
preserves both completed-state audit results, the generic ice-gate FAIL outputs,
the separate source-inactive split, and the measured T8 public tuple.

The receipt-bound [C7 paired-history analysis](PR90_C7_HISTORY_20261019.md)
uses actual T0/T60/T120/T180 records. Its 27-column T0 support is descriptive
and outcome-selected, not the original 162-pressure-cell footprint. The source
history comparison does not validate an observation operator or physical
continuity. The separate 600-second paired experiment used the same executable.
Both closed receipts report `INCOMPLETE`, rc=1, nine completed steps, and
maximum seen timestep 10. Inputs and candidate build were unchanged. The
recorded fatal is `PR87 full joint moment candidate infeasible; see source/full diagnostics`
in the host update, not the rain public-store path. The 180-second completion
is not evidence of 600-second success or physical validation.

The [600-second archive](evidence/pr90_rain_roundtrip_20261019/c7/600/README.md)
verifies a 7,537,409,380-byte decompressed prefix identical to the corresponding
180-second trace in each arm. The 78-record longer trace contains that
73-record prefix plus five T10 records: PRE_RK, RK1, RK2 and two tendencies.
There is no completed T10 RK3, PRE_KDM6 or POST_KDM6. Its partial predictor
diagnostics are not a completed strict endpoint gate.

The [new host failure record](evidence/pr90_rain_roundtrip_20261019/c7/600/failure_classification.md)
confirms six `FULL` rejections per arm in the timestep-10 RK3 attempt: one cloud pair and
five graupel pairs at identical recorded coordinates. Its logger does not
retain exact REAL64 candidate words or the returned failure stage. Candidate
cloud-volume and graupel-density boundary explanations remain inferences;
the exact failing subpredicate and earlier producer remain open. No host
cutoff, tolerance, moment prior, or extra precision change was added to pass
this newly exposed transition.

The [C7 area-weighted activity summary](evidence/pr90_rain_roundtrip_20261019/c7/science/area_weighted_180s.json)
has complete coverage of all 64,960 columns at each of the nine completed
steps in both arms. Cumulative deferred/proposed half-L1 activity is
18.2058% / 84.6583% / 86.4382% for OFF NG/AUT/G and
18.2154% / 84.6576% / 86.4169% for COUPLED. These use actual native map area
and the local KDM6 DEN×DELZ carrier. They are group-vector request activity,
not individual reaction throughput, global water closure, or precipitation
suppression. The large AUT/G fractions remain a scientific open item.

The [C7 joint-absence audit](evidence/pr90_rain_roundtrip_20261019/c7/science/joint_absence/README.md)
uses the same event-selection and same-event geometry calculation as the
preserved C5 audit, with separately pinned C7 source and 180-second receipts.
It records 69,690 OFF and 69,698 COUPLED events in 48 timestep/RK/pair groups
per arm, pairs 1–2 only. Signed Q/number changes retain decimal-print
uncertainty bounds. These event counts are not unique-cell counts, and sums
across RK stages are not a final water or particle-number budget.

The [independent C6 runtime audit](evidence/pr90_rain_roundtrip_20261019/c6/runtime/README.md)
preserves the source/executable/receipt bindings, original generic ice-gate
FAIL outputs, and a separate source-inactive-ice classification. The C6 trace
prefix through 120 seconds matches the corresponding C5 trace byte-for-byte
in each arm; the receipt-bound `wrfout` artifact hashes also match the C5
history artifacts. These prefix comparisons do not convert the incomplete C6
runs into completed or validated runs. The saved T8 PRE_KDM6 record is
insufficient for a standalone whole-KDM6 replay.

## Parallel scientific diagnostics

The [C5 matched history](PR90_C5_HISTORY_20261019.md) uses actual bound
T0/T60/T120 files, same-position cross-arm differences, and separate carrier
and mixing-ratio contributions. The 27-column T0 difference support is a
descriptive subset, not an independent observation footprint. Mapping the
original pressure-analysis support into the native grid remains open; the
[prior source-gap audit](evidence/pr89_process_contract_20261019/review/pr89_observation_source_gap_20261019.md)
identifies the missing source-bound horizontal and vertical operator.

The [C5 joint-absence audit](evidence/pr90_rain_roundtrip_20261019/science/joint_absence/README.md)
is a separate weighted reconstruction from the preserved C5 OFF/COUPLED
120-second runs. It uses same-event carrier and geometry fields to estimate
signed mass and second-moment changes; it is not an exact binary budget or a
D2/C6 measurement.

The column-summary collector retains the old cold summary and adds actual
per-column DEN×DELZ group-vector activity before horizontal aggregation.
Area weighting requires source-bound single-layout evidence, a matching
native grid and actual map area. Historical receipts lacking that evidence
are not retroactively promoted to area-weighted results. This local KDM6
measure is distinct from the host hybrid dry-mass carrier. Water/energy,
physical continuity, momentum balance, observation fit and initial-shock
reduction remain open.
