# PR87: joint moments through two model steps

## Status and scope

Base: PR86 `c84cbd3a0bc366112afe9ebad1087a220eb23b46`.
PR85 v17, original OFF/COUPLED initial inputs and boundaries, and prior receipts
remain preserved. Every native candidate has a separate source manifest,
selected-object build receipt, executable identity, and closed runtime receipt.
No maintained WRF source or original operating input is modified.

**V42 completes both matched 40-second native runs and their completed-state audit.**
OFF and COUPLED return zero with two distinct POST_KDM6 timesteps, unchanged
inputs and full common-air application fraction one. Each completed RK3,
PRE_KDM6 and POST_KDM6 boundary passes the exact selected cloud/rain/graupel
gates and the unchanged global ice 8-float32-ULP criterion. Exact-source ice
counts remain visible nongating diagnostics; this is not an exact-arithmetic
PSD theorem or scientific approval.

| Gate | Current status |
| --- | --- |
| Original PR85 v17 baseline | preserved |
| Final focused suite | 194 PASS; Fortran uses pinned Intel O0/O2 |
| V42 OFF/COUPLED40 execution | COMPLETE; two full steps and KDM6 calls |
| Completed Q/N/B, finite/unit, source-domain audit | PASS_SCOPED for both arms |
| Common-air fraction | all six applications per arm theta=1 |
| Step2 QV intermediate predictors | 4 PRE_RK, 4 RK1, 5 RK2 negative cells per arm; separately reported |
| Same V42 60-second extension | RUNNING |
| 600 seconds | NOT_RUN, pending valid60 |
| Water/energy, host hybrid carrier, native mass–wind, observations, initial shock | OPEN |

Native wall times are 353.25 seconds OFF and 353.76 seconds COUPLED. These
measure the whole selected run and do not isolate REAL128 overhead.

The [independent closed-run review](evidence/pr87_two_step_v42_20261016/runtime/independent_review/review.json)
binds stage and budget hashes to receipts, source/build/executable, initial
inputs and model timestamps. The [integration receipt](evidence/pr87_integration_20261016.json)
and [history](PR87_TWO_STEP_INVESTIGATION_HISTORY_20261016.md) retain earlier
failures. V39 completed40 but failed13 global ice pairs per arm; its unchanged60
extension stopped at T3 RK1. Read-only V40/V41 diagnosis connected the13 cold
extinction witnesses and the exact900 graupel diffusion witness to V42's fixes.

## Repair the producer and the timestep cycle

Generic host cleanup cleared six small positive QC values without QNC after
the first KDM6 call. At `(230,70,3)`, QC `8.4692146629095078e-9` became zero
while QNC `2021875.875` remained. The values persisted through STEP_END,
STEP_BEGIN and FogDES. The opt-in MP37 moisture policy preserves the paired
QC/QI/QR/QG fields; KDM6 joint cleanup owns their QNC/QNI/QNR/QIB partners.
QV, QS, other scalar/tracer calls and `microphysics_zero_outb` retain their
existing rules. No number is regenerated at FogDES entry.

Common air transport retains old-time donors and shared-face Q/N/B fluxes.
Its full application fraction must be one. An opt-in source-first retry applies
only at RK3 after a failed baseline cloud/ice pair; any rain/graupel failure
forbids that retry. It stages the physical source, includes later non-air rates
once, and recomputes the conservative common air tendency from virtual source
prepared interior donors. The exterior donor ring keeps its declared old state.

This remains a first-order transport research baseline. Positivity and moment
validity do not establish transport accuracy or observation retention.

## Preserve source precision through the real driver

Independent replay of a native 39-level Shinhong column matches every returned
REAL32 Thomas solution in both moments and calls. The subsequent independent
REAL32 `(f3-qx)*rdt` operations can move the returned cloud tendency outside its
selected cone; the same stored matrix/RHS and tendency in REAL64 remain valid.

The explicit four-channel payload `[QC,QNC,QI,QNI]` carries

```
delta64 = desired_tendency64 - REAL(returned_tendency32, REAL64)
weighted_source64 = captured_source_carrier * (REAL(raw32, REAL64) + delta64)
                    + later_non_air_source64
```

It is solve-owned and step-bound, not a saved cache. The source carrier is
applied once. The shared existing horizontal stencil is also evaluated in
REAL64 for all four pairs, with explicit RK cadence and registry mappings;
BG remains specific bulk volume. A selected graupel stencil gives density
900.0000008473793 with REAL32 rates and 899.9999534236954 with the same operands
in REAL64. These one-column/cell replays do not attribute every failure.

FogDES keeps its Stokes proposals and shared column process fraction. Its
optional path approves the corrected combined PBL/Fog tendency with the selected
cloud coefficient `523.59881591796875` and lambda `12000..500000`, using direct
linear mass inequalities. It stores the legacy REAL32 rate plus an explicit
REAL64 residual, consumed once. The legacy no-sidecar path is unchanged.
Changes to precision and process admission can change effective model physics.

## Match the validation domain to the next consumer

V29 exposed a quotient/product disagreement at the second-step cloud source
`(106,55,6)`. A quotient rounded onto the lower mass bound while the continuous
volume product missed by one binary64 ULP. V30's direct mass-product check
rejects that exact old witness, but its nearby accepted source still failed
an additional density product.

The source-first temporary state is **specific Q/N used only by air fluxes**:

```
virtual_source = beginning_of_step_specific_pair + dt * physical_source64
virtual_source -> donor_values -> common_air_tendency
```

It does not consume a number-per-volume PSD or perform an N*rho conversion.
V31 therefore checks its strict specific mass cone and REAL32 representability.
It omits the volume-number bound only at that virtual cloud source store.
The full grouped endpoint, post-RK density adapter, KDM6 entry/return and public
storage retain the actual-density continuous and REAL32 number-volume gates.
A raw continuous pair that fails those final contracts is still rejected.

The targeted pinned Intel O0/O2 regression accepts the virtual donor under the
specific contract, rejects the same raw pair under the volume contract, then
checks the staged REAL32 pair through the strict completed-volume store.
See [the bound regression](evidence/pr87_virtual_source_domain_20261016/).
No number floor, wider final PSD range or reduced whole-air fraction is used.

V32diag then records a context-6 graupel pair with QG bits `2B621F22` and
BG bits `2681EB95`: density is about 891.118 kg/m3, but both native activity
thresholds are unmet. The default process endpoint validator allowed that state;
the pair-only validator and ProgB reject it. V33 applies the existing activity
domain to the default validator and partitions the process search at the same
QG/BG boundaries. This preserves proposals and their joint Q/N/B/T updates,
while changing which process amounts can be admitted. It does not activate tiny
particles, clear them, or establish the physical fidelity of the admitted rates.
V33 source/build and 166 focused tests passed, but final team review found a
stale source-rate finiteness gate reading an unassigned REAL32 variable. Its two
runs were stopped and preserved as incomplete; they are not completion evidence.
The next composition validates the actual assigned REAL64 payload and removes
the unused variable. Historical staged transforms remain separately identified.

The signed Q/N storage changes remain numerical representation terms, not
physical phase changes or conservation compensation.

Rain retains distinct mass/number settling velocities with a common admitted
face amount. Pending ice extinction clears number only when the approved mass
actually vanishes. Warm intermediate pair-only states remain distinct from
completed PSD states. These are explicit research model changes; their physical
impact and full budget closure remain open.

## Parallel cold-process result

The frozen v17 analysis separates individual NG/AUT/G alpha from composite
gamma. AUT suppression is mostly rain PSD incompatibility; about 84.44% of the
G full-proposal reason activity is bulk-density incompatibility. These are
first failed full-proposal conditions, not unique accepted-alpha constraints.
No corresponding NG reason classification is claimed.

The next cold-specific physical target is G receiver/volume compatibility;
AUT rain remains separate. The 417 kg absent-graupel freezing case is preserved
but does not take priority over the large cold groups. Group half-L1 activity
is not gross reaction throughput, lost water or latent-heat suppression.
These v17 results are not budgets for the changed V31 model.
See [the cold distributions and scope](PR87_COLD_CAUSE_DISTRIBUTION_20261016.md).

## Validation and execution contract

- Current focused Python tests: 143 PASS. Fortran helpers use the pinned Intel
  profile in fresh scratch directories; no GNU or ifort substitute is used.
- The complete joint transport regression, including the virtual-source case,
  passes pinned Intel O0/O2. The effective kernel hash remains
  `60917061915e0452251c27db7b5d4e97061729605c3218cd291c2cbc3e519e74`.
- V28b O0/O2 first20 agrees bitwise across six recorded stages and all 12 state
  fields, plus exact KDM6 pre/post dumps. This is not every WRF field.
- V27bcompact's observer-only OFF20 agrees with V26c in first KDM6 pre/post and
  final recorded state. It reduces PBL diagnostic volume; no controlled timing
  or I/O attribution is claimed.
- Builds replace nine selected objects plus support in the preserved partial
  host archive. Untouched parent objects/libraries and link settings remain;
  this is not a full clean WRF build. Native scope is one domain/rank/thread/tile.

The [V31 archive](evidence/pr87_two_step_v31_20261016/) binds sources, build and
tests. Archived `composition_kernel.f90` files are intermediate staging
artifacts; effective code is the module embedded in the actual compiled EM
source. The superseded V29 replay using the intermediate is retained alongside
the corrected compiler-input replay.

The duration schedule is `{20,60,300,600} <= duration`, plus the final duration.
Preparation, parsing and completion use the same schedule. Missing/duplicate
snapshots, fatal termination, incomplete timesteps, changed inputs/executable,
and truncated traces remain failures. First-step evidence cannot certify a
longer requested window. Completed RK3/PRE_KDM6/POST_KDM6 gates are reported
separately from intermediate RK predictors.

## Scientific gates remain open

A valid repeated model step is a necessary condition, not scientific approval.
The original analysis inputs remain fixed; model process precision/admission
and numerical transport have changed. Current candidate water/energy closure,
host hybrid dry-mass accounting, pressure/Phi/face-flow/W balance, observation
retention and 10/30/60-minute shock/forecast response require separate evidence.
The v17 cold and water budgets cannot be relabeled as current-candidate results.

After matched40 completion, extend to 60 and then 600 seconds with the same
candidate and inputs, preserving each requested-window receipt. Judge retained
cloud/precipitation/updraft signals together with unwanted pressure/divergence
adjustment. Do not select a quieter forecast by deleting the observed signal or
use analysis increments to offset internal model errors.

## Exact second-step process search replay

V35diag captures the actual G-call vectors at step 2, `call_lat=63`, `i=204`,
`k=17`; the older fatal message printed stale temporary vectors. Pinned Intel
O0/O2 replay reproduces a valid base and a failed search. An endpoint enclosure
proves that every stored rain pair in its narrow continuous G-active interval
violates the rain upper PSD condition. V36 excludes only such proven empty
stored intervals, leaving all other search-failure classifications intact.
The existing valid zero-G deferral then becomes available, with linked mass,
number, volume and heat withheld together. This does not establish the
physical fidelity of those withheld rates.

[The bound replay](evidence/pr87_stored_interval_gap_20261016/) records the
source, compiler, exact operands, baseline and diagnostic clone separately.
Historical V36 focused tests pass 171 cases. Both V36 matched 40-second runs
closed INCOMPLETE at the later ProgB unsupported-state check; V39 is recorded
separately above.

## Preserve prognostic volume through properties and melting

V37 records ProgB call 6 at `call_lat=116, i=33, k=20` changing BG bits
`35F68E57` to `35F68E56` with Q bits `3AD8B31A` unchanged. The next call
rejects its density `900.00002624039394`. The source-extracted Intel O0/O2
regression reproduces both that captured pair and an independent manufactured
pair. Its isolated property comparison uses fixture constants and a deterministic
`rgmma` stub; it does not validate the native Gamma initialization. The reciprocal
volume mechanism is independent of that stub. Source dataflow shows that removing
the final BG rewrite leaves the current-call property calculations unchanged.

V38 then exposes the old melt equation's dependence on that rewrite: a fully
melted QG can leave a negative BG because it subtracts through rounded `rhox`.
V39 proposes the volume sink from the actual stored donor,
`delta_BG = BG * delta_QG / QG`, with exact `delta_BG=-BG` at full exhaustion.
The existing process-fraction and stored-state validator jointly admit
QG/BG/QR/NR/T using the warm-stage pair policy and strict graupel domain.
No pending-transfer moment exception is enabled. A valid zero step withholds
all linked components; search failure remains distinct. Signed mass, volume,
number and temperature storage residuals are recorded; the last is in Kelvin
and is not a total-energy budget. This changes partial-melt volume arithmetic
and process admission, so current-candidate science gates remain open.


## V42 candidate: cold ice-category extinction

The read-only V41 replay binds all 13 T2 POST ice failures to an NG proposal
that can exhaust the ice mass. Ten have a cap-matched Pidep component; three combine
sublimation and ice accretion into snow. The old marker was evaluated before
both sublimation caps, and did not authorize aggregate category exhaustion.
The search consequently rejected the zero-QI/positive-NI intermediate and
backtracked to a small positive ice mass with unchanged number.

V42 marks full sublimation after the original caps and authorizes NG/G
extinction only when their net proposal can exhaust the current fixed ice mass.
NG uses the original fixed state; G uses the state after accepted NG/AUT.
This is search eligibility, not an assertion that the accepted endpoint is zero.
Every retry evaluates the existing source-order REAL32 transaction. Remaining
ice number terminates only for a finite, nonnegative candidate whose actual
stored QI is exactly zero; positive QI retains its number. The normal strict
stored-state validator runs before atomic commit without a pending exception.
Caps, process-rate equations and global PSD bounds remain unchanged.

The matched V42 two-step aggregate extinction ledgers record 103,695 / 103,679 accepted pending
authorizations in OFF / COUPLED, with 65,272 / 65,252 actual positive-number
termination events. These are process events over two steps, not unique cells
or particle inventory. The policy affects more than the 13 causal witness
cells and changes the effective category-number update; unchanged rate
equations do not imply unchanged physics. Weighted number and physical process
budgets remain open. The [event summary](evidence/pr87_two_step_v42_20261016/runtime/ice_extinction_event_summary.json)
binds the underlying ledgers.

`PR87_ICE_EXTINCTION` rows describe accepted pending authorizations, including
cases where backtracking leaves QI positive. Only `extinctions=1` denotes actual
number termination; `dN` is a category-number sink, not a water-mass or storage
residual. Cause bits are 1 (capped sublimation), 2 (NG aggregate), and 4
(G aggregate). This research admission change still needs physical process and
budget evaluation; it does not prove the original rates' physical accuracy.

## V42 candidate: same diffusion operator with wider intermediates

The V41 T3 graupel stencil has one nonzero i+ donor at exactly 900 kg/m³.
The existing REAL64 stencil rounds its two source channels to a ratio just
above 900, which the strict common-state gate correctly rejects. Captured
operands replay identically in pinned Intel O0/O2. REAL128 geometry, face
weights, differences and accumulation give a REAL64 source pair accepted by
the unchanged continuous and stored-state gates for that witness.

The spatial operator, REAL32 input fields and REAL64 output/API remain the
same. One scalar REAL128 accumulator avoids a full additional three-dimensional
workspace. No clipping, bound expansion, coordinate-specific repair or changed
acceptance tolerance is introduced. REAL64 output conversion still has rounding
error: this is not a universal cone or exact-conservation proof.

The isolated 64×64×39 stencil benchmark (12 calls, pinned Intel O2) measured
0.01320 seconds in REAL64 and 1.7916 seconds with REAL128 intermediates, about
135.7 times slower for this helper. These are helper timings, not full-model
runtime attribution. The actual candidate runtime must be reported separately.
The [captured replay and timing](evidence/pr87_graupel_r128_diffusion_20261016/review.md)
records the scope and conservation residuals.
