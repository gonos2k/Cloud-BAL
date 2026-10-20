# PR93: active ice production, storage and freezing consumption

Base: PR92/main `984cbf9a3b658c218448912d6b3e25100d72e1f3`.
Candidate: **PR93-C4**, selected-object Intel partial-host overlay, one domain,
rank, thread and tile. It is not a clean rebuild of WRF and its libraries.
The [candidate binding](evidence/pr93_active_ice_20261020/candidate_binding.json)
pins the input/output native source, compiler profile, unchanged shared core,
freezing helper and executable. Scientific approval remains **FAIL_OPEN**.

## What the preserved C18 evidence establishes

The exact public T24 PRE_KDM6 point is valid under the freezing consumer's
existing active-ice rule. Its number field is per dry mass; converting it to
internal volume number gives `44167A96`, not the later failing `441BBBE7`.
The later PINU input has mean particle mass approximately 10.8 REAL32 ULP
above the configured upper bound, outside the unchanged 8-ULP allowance.
This narrows the first departure to inside KDM6. It does not identify the
first internal write from the old trace alone. See the
[exact origin investigation](PR93_ICE_ORIGIN_20261020.md).

At the failing input, the source's REAL32 exp/log slope rounds to
`9080.0009765625`, one REAL32 value above its lower slope boundary. The old
slope-only guard skips reconstruction even though the freezing consumer
rejects the direct mean mass. The focused replay confirms this guard hole;
it does not replay every intervening process.

## Focused source change

[The generator](../tools/pr93_active_ice_contract.py) accepts only the pinned
C18 native source. It extracts the original freezing helper's exact `in_cone`
predicate into one shared external pure function. The three existing ice
PSD reconstruction blocks and freezing helper call that function using the
same density, coefficients, promoted arithmetic and **original eight ULPs**.
The original activation guards, inactive cutoff, PSD number-bound helper,
number/slope cache updates and physical freezing requests remain in place.
Invalid active inputs are rejected before exp/log evaluation.

When the slope guard misses a direct mean-bound violation, the existing PSD
boundary helper reconstructs internal number and its cache. The new cases
use its existing reconstruction ledger. These changes are numerical PSD
reconstruction, **not physical nucleation**. The shared host transport/store
core is unchanged. The [compiled-source patch](evidence/pr93_active_ice_20261020/compiled_source.patch)
records the exact transformation selected for the overlay build.

An opt-in diagnostic records one selected column immediately before and
after the existing successful ice sedimentation call. Its coordinate/step
selector controls I/O only. Attribution to the original C18 first writer
requires matching original inputs/prefixes; candidate-only records alone
cannot establish that historical claim.

## Invalid base, deferred packet, and accepted packet

The existing helper already returns these separately:

| Outcome | `base_valid` | `accepted` | Action |
| --- | --- | --- | --- |
| Invalid input | false | false | Reject at its producer/consumer boundary. |
| Valid, unrepresentable positive packet | true | false | Keep all endpoints; record the entire packet as deferred. |
| Valid accepted packet, including zero | true | true | Reflect the coupled approved amount. |

The captured cloud donor requests are below both donor half-ULPs. Making
the ice base valid therefore does not make a nonzero stored packet possible.
No extra halving iterations, input-specific floor, or new return API are
needed. [The packet contract](PR93_PACKET_CONTRACT_20261020.md) retains this
distinction and the exact Intel O0/O2 checks.

The producer fixture checks the three exact transformed blocks and shared
freezing predicate. The actual ice export uses the REAL32 scalar
volume-to-specific converter; the fixture converts that public number back
with the actual specific-to-volume helper before freezing consumption.
It separately exercises the common store API with declared strict options.
The REAL64 `Nspec64 = REAL64(Nvol32)/REAL64(rho32)` adapter belongs to the
rain/cloud paired-store path; that component test is not labeled as the
actual ice export or the complete host transaction. The closed native state audit separately covers the actual integrated
path. Its scoped gates and generic-policy failures are reported below;
the component fixture alone does not establish that integration.

## Execution and validation boundaries

The paired 600-second request uses one frozen executable and the same
OFF/COUPLED initial and boundary inputs as C18. The runner requests completed
480-, 500- and 600-second state snapshots in addition to its prior schedule.
Bare PR85 invalid-base rejections are now collected as fatal even when no
generic `ERROR STOP` line is emitted. The [paired prelaunch check](evidence/pr93_active_ice_20261020/prelaunch.json)
checks the combined disk requirement; reference receipts are arm-specific.
Both collectors are now closed. The [execution summary](evidence/pr93_active_ice_20261020/runtime/execution_summary.json)
and preserved arm receipts record:

| Result | OFF | COUPLED |
| --- | --- | --- |
| Requested/completed model time | 600 / 600 s | 600 / 600 s |
| Distinct completed KDM6 calls | 30 | 30 |
| Receipt / process return code | COMPLETE / 0 | COMPLETE / 0 |
| Collector errors / changed inputs | 0 / 0 | 0 / 0 |
| Required 480, 500, 600 s snapshots | present | present |

Both execute SHA `20aaa6058797e7d1ec7a874ae92ed44f9ac19876ef2f14477b5eedb6a1ae44be`.
These receipts establish completion under this research configuration;
independent closed-state and selected-call audit results are recorded separately.

The initial C4 launch completed one step per arm, then stopped because the
inherited diagnostic writer required `PR91_RUN_ID`. These closed
**INCOMPLETE** receipts and the exact launch runner are preserved in
[the launch-failure record](evidence/pr93_active_ice_20261020/launch_environment_failure/summary.json).
The runner now supplies the same deterministic diagnostic identity that it
records in preflight, launch provenance and receipt. The corrected launch
uses a new output identity with the **same executable**; it does not change
the physics or relabel the failed request as successful.

The independent exact-source audit and declared active/inactive ice policy
are distinct gates. A policy pass must not relabel generic exact-source
failures as exact passes. No runtime result by itself approves water/energy
closure, observation skill, mass–wind balance, or reduced initial shock.

Validation is recorded separately:

- [Canonical suite](evidence/pr93_active_ice_20261020/validation/canonical.json):
  exit 0, pinned Intel, 6,526 frozen files unchanged. Read-only metadata from
  the exact isolated worktree supplies the commit identity required by legacy
  tests; the initial missing-Git harness failure is retained.
- [Final focused suite](evidence/pr93_active_ice_20261020/validation/focused.json):
  23 tests pass, including both Intel profiles of the exact transformed
  producers/store/reconsumption and freezing outcome fixtures.
- [Snapshot-to-final delta](evidence/pr93_active_ice_20261020/validation/canonical_final_delta.json):
  no production Fortran changes after the canonical freeze. The final Python runner and
  contract-fixture changes are covered by the separate focused suite. These
  results are not presented as one all-final-files canonical invocation.

## Science work performed in parallel

[The QC transfer chain](PR93_QC_CHAIN_20261020.md) uses the *same actual*
met_em identity for horizontal and vertical component replays. A fixed
source-derived native support is used for C18 matched QC/pressure/Phi/W
response through the last actual stored history time, T420; T460 execution
does not imply a T460 history file. C18/C14 process activity is compared over
their common first twelve steps. These are scoped transfer/response results,
not independent observation skill or a closed mass/energy budget.

## Closed-state gates remain separate

The [independent closed audit](evidence/pr93_active_ice_20261020/runtime/closed_runtime_summary.json)
hash-checks compressed and expanded traces and covers 180 states per arm:
90 completed endpoints (RK3, KDM6 pre/post) and 90 predictor states.
Full metadata reports are [published as exact gzip JSON](evidence/pr93_active_ice_20261020/runtime/audit_publication.json);
no native field arrays are added to the repository.

| Gate | OFF | COUPLED |
| --- | --- | --- |
| PR87 source REAL32 cloud/rain/graupel endpoint checks | PASS | PASS |
| Existing 8-ULP active/inactive ice policy, all 180 states | PASS | PASS |
| Generic Q/N/B audit | FAIL | FAIL |
| Generic precomputed-policy exact bounds | FAIL | FAIL |

Completed endpoints have no negative/nonfinite fields, orphan/negative pairs,
or number-conversion failures. Generic ice-cone findings beyond 8 ULP are
inactive pairs: 921/861 endpoint cell-state events (OFF/COUPLED); active ice
beyond 8 ULP is zero. The generic predictor audit additionally records
1,527/1,528 negative-QV cell-state events. Those are not completed endpoints.
Raw exact active-ice outliers remain diagnostic: 78/83 endpoint events are
within the unchanged allowance. Counts are repeated cell-state events, not
unique cells or forecast error rates.

The source gate and generic-policy check use different coefficient bases.
The source gate derives rain bounds from REAL32 `PIDNR=12566.37109375` and
source lambda limits; the generic policy reads its precomputed bounds.
Consequently the latter has 351 exact-outside rain endpoint events per arm,
all within 8 ULP, while the source-defined gate passes. Neither result
relabels the preserved historical C18 FAIL. The [scope split](evidence/pr93_active_ice_20261020/runtime/qnb_scope_split.json)
retains each basis and stage category.

The corrected-environment launch also has the exact same serialized step-1
state/PBL prefix as its corresponding initial launch (883,241,700 bytes per
arm). Its runner hash changes as recorded; executable and model input pins
do not. This supports that launch-pair comparison only, not C18 historical
first-writer attribution.

## Actual T24 call replay

The [selected-call evidence](evidence/pr93_active_ice_20261020/runtime/ice_replay/call_origin_summary.json)
replays the actual C4 ice sedimentation helper for each arm with its captured
39-level QI/NI/density/geometry/rates. Pinned Intel O0 and O2 both reproduce
all 39 AFTER bit pairs exactly. This is one `(loop,n,mstep)=(1,1,1)` call per
arm, not an independently rerun whole KDM6/WRF forecast.

At k20 the captured mean changes from `2.000467184384699e-9` to
`2.098277117513574e-9 kg`, approximately 10.8029 REAL32 ULP above the raw
maximum, hence 2.8029 ULP beyond the existing allowance. The following stage-1
PSD completion reconstructs internal volume number from `622.935974121` to
`622.936706543 m^-3`; the resulting mean `2.098274650450637e-9 kg` lies
inside the raw upper bound `2.0982747187893314e-9 kg`.

The differential sedimentation output is an intermediate pending PSD pair.
The subsequent PSD producer owns its completion before freezing consumption.
The fix closes the old slope-only guard gap at that completion; it does not
force common settling velocities or label every transient PSD departure as
an invalid completed endpoint. These observations identify the C4 call
boundary. Historical C18 first-writer attribution remains unproven without
matching original inputs/prefixes.

## Current C4 scientific response

The [closed-runtime science summary](evidence/pr93_active_ice_20261020/runtime/c4_runtime_summary_20261020.md)
uses the actual C4 receipts and eleven common history records, T0 through T600.
It retains the same source-derived support: 613 native QC points in 16 columns.
The unweighted QC difference RMS is `1.2509394e-4 kg/kg` at T0 and
`3.2945245e-5 kg/kg` at T600. The RMS of `deltaQC(T600)-deltaQC(T0)` is
`1.4059544e-4 kg/kg`. A smaller OFF–COUPLED difference is not evidence that
observed cloud is better preserved; these are paired response diagnostics,
not observation skill or inventory closure. Pressure, Phi and W are in the
bound response JSON with their units.

Current area-weighted cold half-L1 deferred/proposed activity is:

| Window | Group | OFF | COUPLED |
| --- | --- | ---: | ---: |
| T1–T23, 460 s | NG | 17.2989% | 17.3117% |
| T1–T23, 460 s | AUT | 69.0003% | 68.9957% |
| T1–T23, 460 s | G | 71.4175% | 71.4086% |
| T1–T30, 600 s | NG | 18.6589% | 18.6710% |
| T1–T30, 600 s | AUT | 67.8982% | 67.8939% |
| T1–T30, 600 s | G | 69.3621% | 69.3528% |

These nested windows come from the same C4 runs. They are group-vector
activity ratios, not reaction throughput or precipitation suppression.
Large AUT/G deferral remains a scientific limitation. Global water/energy
closure, native face-flux continuity/momentum closure, observation skill,
and reduced unnecessary initial adjustment remain **OPEN**.
