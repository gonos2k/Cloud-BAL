# PR87 historical candidate investigation

These are preserved observations at each numbered candidate. Statements about
then-current status are historical. See PR87_TWO_STEP_COMPLETION_20261016.md
for the final integrated identity and outcome. Earlier failures are not
relabeled as successful runs.

# PR87: preserve the completed joint state across timesteps

## Scope

Base: PR86 `c84cbd3a0bc366112afe9ebad1087a220eb23b46`. The PR85 v17
executable, original OFF/COUPLED inputs, and historical receipts remain fixed.
This candidate has a separate source manifest, overlay build receipt, and ELF
identity. It is a selected-object partial-host research build, not a clean WRF
rebuild or scientific approval.

## Current integrated candidate: V14

V14 is the current research candidate. Earlier numbered sections and receipts
below retain the investigation history; they do not represent a completed
40-second window. Its selected-object executable is
`f75ceadfe03ad4ce91fa29ba6ea51828df354ae389cb3134a73fdb69c1921c81`.
The matched OFF/COUPLED runtime result is being collected in
`docs/evidence/pr87_two_step_v14_20261016/`.

The original FogDES error was traced to host cleanup and corrected at that
producer. Subsequent execution exposed a distinct rain contract mismatch:
60 first-POST and 285 second-PRE rain states in V11b passed the 8-ULP pair
predicate but violated the exact KDM6 rain PSD bound. V12 diagnostics confirmed
one such state immediately before the unchanged nongraupel admission guard.
The initial first-PRE had no strict rain violation.

V13 closes this producer chain with the live default-REAL source coefficients:
`pidnr=12566.37109375`, `dmr=3`, `lambda=961..35000`. The coefficient is also
independently reconstructed from a captured runtime PSD-boundary row. The
native air update, rain sedimentation, warm rain process admission, and
completed public rain store use the same strict cone. Continuous invalid
states remain rejected. A valid continuous state may select one adjacent Q
storage value while keeping N fixed; both the REAL64 density product and the
actual REAL32 re-entry product must then pass. Signed Q/N representation
changes are recorded separately and are not called phase change, energy
closure, or conservation improvement.

This is a changed numerical model: distinct rain mass/number velocities and
one shared admitted face fraction replace independent sedimentation updates;
strict warm admission and bounded final representation can change downstream
processes. V11b already changed first-call outputs relative to v17 despite an
identical incoming first call. V13 must be assessed under its own identity.
The parent v17 and all original inputs remain preserved.

V13 then exposed a warm caller control error on its first call. An exact
input component replay captured `(timestep,lat,i,k,loop)=(1,2,46,3,1)`:
`NO_FEASIBLE_STEP`, alpha zero, a valid base, and no attempted trial. The
caller skipped zero, then incorrectly reported endpoint search failure.
V14 evaluates that retry-zero/status-one case through the existing full
trial body and validator, including pending rain-number-to-CCN transfer.
Other search failures and exhausted positive endpoint searches stay fatal.
Zero applied warm processes are withheld physics, not a successful physical
reaction. Only those status-one warm rows are emitted into the existing
warm budget ledger; this sparse file is not a complete warm activity census.

The frozen V13 source/build and exact native-fragment O0/O2 evidence are in
[the compact archive](evidence/pr87_two_step_v13_20261016/archive_manifest.json).
Static team review found no remaining source/API blocker. Runtime completion,
completed-stage validity, predictor-state diagnostics, and scientific
acceptance are separate gates. In particular, existing negative QV predictor
states are retained in full audits and cannot be hidden by a Q/N/B PASS.

## Producer correction

A diagnostic-only 40-second OFF run reproduced the second-step failure. The
first KDM6 pre/post public dumps are byte-identical to v17. Six valid cloud
mass/number pairs become `QC=0, QNC>0` in the subsequent generic host cutoff;
they remain unchanged through step end, next step begin, and FogDES input.
The first observed coordinate is `(i,j,k)=(230,70,3)`: QC changes from
`8.4692146629095078e-9` to zero while QNC remains `2021875.875`.

The correction appends an optional argument to `microphysics_zero_outa` and
passes it only on the MP37 moisture call. It preserves scheme-committed
QC/QI/QR/QG, whose QNC/QNI/QNR/QIB partners are separate scalar fields. The
KDM6 joint cleanup remains responsible for those pairs. No number is
regenerated and no condensate is deleted to bypass FogDES. Generic vapor
nonnegativity, snow cutoff, scalar/chemistry/tracer calls, and the distinct
`microphysics_zero_outb` boundary protection retain their original behavior.

The exact cleanup and FogDES source replay passes pinned Intel O0/O2 with the
saved pair. Ordinary cleanup reproduces the fatal; the scoped correction
allows a second FogDES consumption. See [the state trace](PR87_STATE_CYCLE.md)
and [the source regression](PR87_NATIVE_CYCLE_REGRESSION.md).

## Second exposed boundary: joint REAL32 storage

The cleanup-only candidate v2 preserves the cloud pairs through FogDES(2),
but both 40-second windows stop at the subsequent RK source/transport update.
Its existing source-only diagnostic contains 582 pairs per arm: all continuous
values pass the declared constraints. Independent REAL32 storage loses Q to
zero in 577, and crosses a ratio bound in the other five. These are
source-only diagnostic operands; they do not identify every failing full
source-plus-transport candidate.

Candidate v3 opts into a bounded joint quantizer at the completed candidate
store. The public transport kernel's default remains strict. Only a valid
continuous pair with positive subnormal Q can use the new paths:

- If ordinary rounding already makes Q zero, store both moments zero. This
  adds no Q loss beyond ordinary Q rounding; it does change the number store.
- If positive rounded Q/N crosses a ratio endpoint, try exactly one adjacent
  Q value toward the interval, leaving N unchanged. Every stored constraint
  must still pass. No normal-Q repair, floor, wider PSD bound, or larger
  tolerance is permitted.

Opt-in requires signed per-pair storage deltas and counts. It accepts only the
full air-transport candidate (theta=1), with atomic commit. The additional
storage ledger is a **numerical representation term**: it measures rather than
compensates loss or gain, and does not establish conservation. It records
`carrier_new*(stored-continuous)` for adjusted cells, separately from transport
rejection, with sparse coordinate/current-carrier geometry records. These
pressure-coordinate sums are not labeled kg or energy. Temperature is not
changed as a fictitious evaporation/condensation repair; energy closure stays
OPEN. Even this tiny-range quantizer is an explicit model representation
policy, rather than a neutral refactor.

The v2 failed receipts remain preserved. See [failure classification](PR87_SOURCE_STORAGE_FAILURES_20261016.md)
and the pinned [O0/O2 kernel test receipt](evidence/pr87_native_cycle_20261016/joint_storage_ifx_o0_o2.json).

## Third exposed boundary: final-RK operator ordering

V3 passes the second FogDES and RK1/RK2, then rejects 17 full cloud candidates
at RK3. These have normal Q, rather than subnormal Q. Source-only diagnostics
are not sufficient to explain them; the retained full candidates and the
source-based classification remain bound to that failed identity. No tolerance
increase or repair of an invalid continuous candidate is allowed.

The frozen WRF final-RK path prepares its physical source before air advection.
The grouped replacement had instead combined that source with an old-donor
flux. V4 applies source-first ordering within the existing grouped low-order
operator at RK3, keeps the outer donor ring unchanged and validated, and
retains REAL64 face rates through the endpoint calculation. A dyadic two-cell
counterexample shows why source-first transport preserves a valid pair cone
while the additive old-donor construction can leave it. See [the equations,
source connection, and limitations](PR87_SOURCE_FIRST_GROUPED_TRANSPORT.md).

V4 also explicitly expands the constrained-store policy: an already valid
continuous normal-Q pair can use the same single adjacent-Q choice when
ordinary REAL32 rounding alone crosses its interval. Invalid continuous
states remain rejected. The signed representation ledger and theta=1 gate
are mandatory. Strict legacy and subnormal-only interfaces retain their
previous scopes. Pinned Intel O0/O2 cover normal and subnormal storage, both
directions, invalid-state rejection, atomicity, and the source-first case.

V4 then exposes ten first-step RK3 ice storage failures with continuous Q
between 0.5094 and 0.7453 REAL32 quanta. Ordinary Q rounds to one quantum
outside PSD; adjacent Q=0 leaves a positive N. V5b's separately enabled
quantum-absence rule selects `(0,0)` only after both attempts fail and only for
`0<Q64<min_positive_REAL32`. This bounds Q removal below one storage quantum,
while removing the complete valid N moment. Both changes remain explicit
numerical ledger terms. The old strict/subnormal-only policies are preserved.
V4 completed zero timesteps and remains a failed historical receipt.

V5b passes RK3, but its first KDM6 call rejects a newly incoming graupel
transient. Existing pre/stage records locate its first appearance at RK3,
`(i,j,k)=(41,237,13)`, rather than inside ProgB. The original v17 pre has QG=BG=0
there. See [the closed partial-run evidence](PR87_SOURCE_FIRST_STORAGE_V5B_20261016.md).
V5b completes zero timesteps; no post-call state is available.

V6 confines source-first preparation and REAL64 face-rate retention to the
paired PBL cloud/ice channels (QC/QNC and QI/QNI). Rain/graupel retain their
established old-donor REAL32 source/rate path. The separately enabled constrained
representation policy remains generic across all four pairs; unchanged R/G
source/rate code does not itself prove bitwise equality of an incoming state.
No ProgB range expansion, number floor, or special coordinate correction is
introduced. Actual incoming G comparisons and requested-window completion are
bound separately in the integration receipt.

V6 reaches KDM6 with the original v17 graupel input, but changed cloud/ice
inputs subsequently expose an unsupported ProgB state inside that first call.
It completes zero timesteps and is retained as a failed candidate.

V7 first evaluates the established old-donor endpoint using the same full
continuous-state and constrained-store predicates as the commit kernel. If
that endpoint is admissible, its rates are retained. Only at final RK3, and
only when failed endpoints belong to the PBL cloud/ice pairs, it retries the
failed **whole pair across the domain** using source-prepared donors and shared
face fluxes. A rain/graupel failure blocks this retry. It never mixes the two
operators cell by cell or reduces the common air fraction. The source enters
once, outer-ring donors remain unchanged and validated, and the full candidate
is committed atomically after one retry. This conditional operator is a new
numerical policy; it does not prove native dry-carrier closure.

An exact native-fragment pinned Intel O0/O2 regression verifies both baseline
retention and a two-cell shared-face retry, including the unchanged neighbor
and source counted once. See [its bound receipt](evidence/pr87_state_cycle_20261016/source_first_fragment_ifx_o0_o2.json).
Actual baseline identity and two-step completion are evaluated separately from
this component test.

V7 preserves the first pre/post dumps exactly but stops at second-RK3 source
preparation: the cloud virtual donor at `(146,103,4)` has Q/N about 8.28
REAL32 ratio spacings below the nominal minimum, just beyond the unchanged
8-spacing endpoint tolerance. That split intermediate is not a stored state
or a PSD input. V8 therefore requires finite, nonnegative, paired,
representable transport donors, while deferring the ratio interval test to
the combined source-plus-air endpoint. The unchanged boundary ring retains
its full PSD check, and every committed endpoint still passes the original
continuous and stored PSD predicates. No source is scaled, no value is
floored, and no endpoint tolerance is enlarged. If the combined endpoint
fails, the complete candidate is still rejected. The earlier cone-preserving
argument is sufficient when prepared donors satisfy the cone; it is not a
guarantee for every such virtual intermediate.
The extended pinned Intel O0/O2 [virtual-donor fixture](evidence/pr87_state_cycle_20261016/source_first_virtual_donor_guarded_ifx_o0_o2.json)
passes baseline retention, whole-pair fallback, and the valid combined-endpoint
case; negative virtual donors and invalid final PSD endpoints still fail
without committing Q/N.

These are new physical/numerical candidates, not claims of bitwise reproduction
of native high-order PD or of the v17 first call. The latest kernel's explicit
quantum option and prior-mode compatibility pass pinned Intel O0/O2 in
[the opt-in receipt](evidence/pr87_native_cycle_20261016/joint_quantum_optin_ifx_o0_o2.json).

## V9: explicit intensive-source handoff

The V8 final cloud candidates miss the unchanged lower pair bound by about
8.1603 and 8.0014 REAL32 ratio ULP. The FogDES endpoint arithmetic precedes
`calculate_phy_tend`, which couples the stored source to the hybrid carrier in
REAL32. Widening that rounded coupled rate in the grouped updater does not
recover the original intensive source. A source-extracted pinned Intel Gamma
probe rules out the earlier coefficient-initialization hypothesis; no bound
or tolerance is changed.

V9 captures the actual unweighted QC/QI/QNC/QNI source by calling the existing
`update_phy_ten` on local shadow tendency outputs before carrier coupling. It
passes total raw tendencies, the actual coupled references, carrier and timestep
explicitly from part2 through solve to the updater. Source inputs are read-only;
the original weighted update remains in place. The retry rejects stale payloads,
changed coupled sources and a source/old-carrier mismatch.

For a failed whole cloud/ice pair only, RK3 stages the source with explicit
REAL32 multiply then add. This virtual donor is embedded once in the local
kernel base, with the separate local source zeroed; common air transport then
uses it. Virtual donors require safe nonnegative paired operands, while the
complete continuous/stored endpoint retains every existing PSD and conversion
check. An orphan due to storage can use only the existing bounded joint store
on a continuously valid pair. No invalid full endpoint is repaired.

This is a declared change to source representation and operator ordering,
not exact preservation of the old weighted update. Its ledger records original
`dt*coupled_source`, represented `W*(staged-old)`, signed difference, L1 and
maximum absolute difference. These are pressure-carrier amounts, including
producer coupling and staging effects; they are not kg, energy, phase transfer,
or proof of conservation. The pinned Intel exact-fragment regression passes
nine modes at O0/O2, including no-air bitwise reproduction and stale-payload
atomic rejection. See [the fixture receipt](evidence/pr87_state_cycle_20261016/source_intensive_stage_ifx_o0_o2.json).

V9 OFF and COUPLED each reproduce one 20-second step, then reject at the
coupled-reference guard before second RK3 commit. The source capture is
complete at part2 return, but `rk_scalar_tend` later adds horizontal diffusion
at RK1; optional diabatic and boundary tendency operators also live in that
assembly path. PD advection is separate. The V9 reference therefore omits
legitimate later non-air tendency assembly. The closed receipts remain
`INCOMPLETE`; no source-representation row was emitted before rejection.

V10 retains the original intensive physics capture and explicitly carries
those later weighted additions. At the first grouped RK consumer only, solve
records `D=REAL64(live_tendency)-REAL64(coupled_physics_reference)` after all
scalar-source and boundary assembly and updates the live reference. RK2/RK3
retain that reference and reject further mutation. The selected virtual donor
is `z=REAL64(physics_stage32)+dt*D/W_old`; the local kernel base is the physical
stage, and the explicit source is D. Thus physics and later additions each
enter once, with PD advection supplied solely by the common air flux.
The ledger's represented amount becomes `W_old*(physics_stage-old)+dt*D`.
This separates the actual later assembly from an inverse estimate of the
original raw physics rate and leaves the final PSD/tolerance gates unchanged.
Both closed V10 runs complete one 20-second step, pass the second RK3 and
KDM6 entry checks, then reject an invalid rain base inside the second KDM6
call. The saved pre-state's NR is public number per dry kg; the freezing
record's NR is internal volume number. They must not be compared without the
same dry-density conversion. At `(i,j,k)=(114,2,18)`, the entering rain pair is
valid near its lower mean-mass bound, while the later freezing input is below
that bound. Source order points to the intervening differential rain
sedimentation, but no second-call process snapshot directly captures its
first invalid update. No empty initial receiver is inferred from the
first-call-only cutoff ledger.

The next candidate routes rain mass and number through the existing paired
sedimentation kernel, retaining distinct prescribed velocities and admitting
the two extensive packets with one face fraction. Both continuous and stored
donor/receiver PSD conditions are checked without widening the existing
8-REAL32-spacing allowance. Rejected packets remain in their donor; approved,
withheld, surface and storage changes are recorded separately on every call.
This changes the numerical sedimentation operator and can suppress transport;
it is not a neutral refactor or proof of sedimentation accuracy. ICE and
G retain their existing modes. The unlaunched V11 full-module build exposed an
outdated helper interface. V11a adds the current explicit interface, but a
copied parent compiler-generated interface still conflicts. V11b excludes that
single stale genmod while preserving unrelated modules and their conflict
checks. The full module compiles and links under the pinned Intel profile;
93 focused tests pass, including applied-source ICE/G and rain O0/O2 cases.
Both V11b 40-second windows are now closed `INCOMPLETE` (return code 128).
They complete one step and pass second RK3/KDM6 entry, then reject
`KDM6 invalid base before nongraupel admission`. No second post-call state
exists. The rain ledger covers all of timestep 1 and only four wrapper calls
of timestep 2; it is not a completed two-step sedimentation budget.

The V11b incoming first-call dumps remain byte-identical to v17, but its
post-call dumps change. For OFF, QR changes in 91,100 cells with a local-measure
inventory difference of about +1.1494 million kg; downstream coupled cold
responses also alter other species (QC about +5.6871 million kg). These are
candidate-minus-baseline differences under the fixed first-call
`rho_d*DELZ*area` measure, not mass creation, host hybrid closure or skill.
The [bound comparison](evidence/pr87_two_step_v11b_20261016/first_call_change.json)
retains signed and L1 changes. Rain sedimentation's changed proposals and
rounding can affect later nonlinear admissions even where its face fraction
is one. V12diag changes only the failing guard's printed diagnostics to identify
the next base violation; no physical correction is inferred before operands.

## Execution and diagnostics

`pr86_time_response.py` now shares one duration-dependent schedule between
collection and completion: milestones 20/60/300/600 seconds within the window,
plus its endpoint. A 40-second run requires 20 and 40 seconds. Missing,
duplicate, truncated, fatal, or changed-input records still fail the gate.
Candidate mode explicitly binds a new build receipt and replaces only the
staged executable; original baseline hashes are checked before and after.

Repeated formatted cold/warm cell rows are omitted in the new source copy.
The original full v17 ledgers remain available. A diagnostic run proves this
change preserves the first public KDM6 pre/post dumps exactly. This is an
output reduction, not evidence that I/O dominated the earlier runtime.
Cloud-state boundary summaries and existing full joint-state stages remain.

## Cold process investigation

Saved-ledger analysis separates individual group admission from the later
shared composite scale. G and AUT suppression is dominated by the former;
the shared scale contributes less than one percentage point of their proposal
activity. Targeted records classify G full-proposal failures predominantly by
bulk-density checks and AUT failures by rain PSD checks; their precise
emitted-row denominators are retained in the report. Targeted first-call AUT/G probes annotate the existing validator's
first failed full-proposal endpoint check. They use the actual private
coefficients and pending-transfer flag, and leave the admission calculation
unchanged. This label identifies a failed full proposal; it is not a proof of
the unique constraint that determines the optimal admitted fraction.

All weights use the explicitly bound first-call KDM6 measure. Half-L1 group
vector activity is not primitive reaction throughput, lost water, or a
latent-heat suppression rate. See [the admission distribution](PR87_COLD_CAUSE_DISTRIBUTION_20261016.md).

## Reproduction

From the repository root, create fresh scratch directories:

```bash
python3 tools/pr87_prepare_native_cycle.py \
  --output /var/tmp/pr87_sources_new \
  --preserve-kdm6-joint-cleanup --admission-reasons --joint-subnormal-storage \
  --source-first-donors --joint-rain-sedimentation
python3 tools/pr87_build_native_overlay.py \
  --scratch /var/tmp/pr87_build_new \
  --source-overrides /var/tmp/pr87_sources_new/overrides.json \
  --extra-source tools/pr87_cloud_cycle_observer.f90 \
  --quiet-arg-temporaries
PR87_PROBE='230 70 3' python3 tools/pr86_time_response.py \
  --arm OFF --duration-seconds 40 \
  --candidate-build /var/tmp/pr87_build_new/pr87_native_overlay_build.json \
  --output /var/tmp/pr87_OFF_new --execute
```

Run COUPLED separately with the same candidate build and duration. The runner
uses the preserved v17 runtime inputs and pinned Intel environment. Existing
output directories are refused. Native identities and completed-state results
will be bound in `docs/evidence/pr87_integration_20261016.json`.

## Remaining scientific gates

Normal termination and local moment validity do not establish host hybrid
mass closure, total energy closure, observation preservation, force/continuity
balance, or reduced initial shock. First-order transport and held physical
processes remain part of this research model. Scientific approval stays
`FAIL_OPEN`; later 60/600-second windows must be reported by their actual
completion, not inferred from a successful shorter run.

## V12diag: strict next-consumer predicate

The diagnostic-only OFF replay reproduces the V11b first pre/post bytes and
then captures the same second-call rejection at `(i,j,k)=(110,5,18)`. Its exact
REAL32 words give QR=`1.2257382608904521e-11`, internal NR=`0.02628232352435589`
and dry density=`0.6284514665603638`. The later NG validator requires

```
NR <= (rho_d * lambda_max**dmr / pidnr) * QR
```

Its right side is `0.02628232244432478`; the stored NR is larger. The V11b
rain helper admitted this endpoint under the 8-REAL32-spacing mean-mass
allowance inherited from the separate freezing consumer. NG uses a strict
number inequality, so the helper's output domain was wider than its next
consumer's domain. Positive transient ice is paired in this capture; the
separate source-only early ice-number-zero hazard is not this failure.

The next revision uses the same source coefficients, operation order and
strict continuous/stored number inequalities as NG. It tightens the producer,
without changing NG's accepted domain or inserting a count/condensate repair.
The ledger and distinct velocity channels remain. The old 8-spacing V11b and
its failed receipts remain separately identified. Actual new-run completion is
still required. See [exact captured operands](evidence/pr87_two_step_v12diag_20261016/OFF_ng_strict_rain_mismatch.json).

V12 logged `n` after sedimentation, not the current cold-loop ordinal; its
metadata retains that value as a legacy counter. Future diagnostics report
`loop` explicitly. This correction does not affect the captured state words or
location.


## V25–V30: producer precision and common source admission

V25 diagnostic replay matched every returned REAL32 Thomas solution in the
selected native 39-level column. The invalid cloud source arose in separate
REAL32 `(f3-qx)*rdt` formation, rather than the solver outputs. A selected
horizontal graupel stencil similarly crossed 900 kg/m3 in REAL32 while the
same operands in REAL64 remained inside. V26c carries explicit PBL corrections
and the existing horizontal stencil in REAL64 across all paired categories.
Both matched arms then completed only 20 seconds: 20 cloud candidates failed
second RK1; the earlier 14 graupel failures were gone.

V27bcompact is diagnostic-only relative to V26c. OFF completes its requested
20 seconds with exact KDM6 pre/post and final recorded-state equality. The
per-cell PBL packet output is replaced by column summaries. This establishes
output equivalence for that window, not a controlled performance result.

V28b includes combined PBL/FogDES source admission and correct FogDES-before-
driver compile ordering. Both matched arms complete 20 seconds and pass the
next FogDES and RK1/RK2, then reject a source-stage pair at RK3. V29diag adds
only exact failure operands before that unchanged fatal. The first captured
cloud pair `(106,55,6)` has a quotient that rounds onto the lower bound while
the continuous number-volume product lies one binary64 ULP outside. The
corrected replay uses the actual compiler-input kernel, not the intermediate
`composition_kernel.f90` file; the superseded replay is preserved and labeled.

V28b strict O0 and pinned O2 OFF first20 agree bitwise at all six recorded
stages and all 12 state fields; exact KDM6 pre/post dumps also match. This is
not equality of every WRF field or a completed second step.

V30 replaces the optional FogDES quotient comparison with the selected linear
mass inequalities, retains the final density-weighted store gate, and records
future rejected source operands as REAL64 values before aborting. It preserves
the legacy no-sidecar FogDES path. Matched40 validation is recorded separately
in the integration receipt; these source notes alone do not establish success.


## Archived implementation notes through V28

These are preserved development notes; their present-tense candidate and validation statements apply to the named historical version only. The integration receipt and main report give current status.

## Corrections at the state producers

### Host cleanup and timestep circulation

Six paired cloud states became `QC=0, QNC>0` in generic host cleanup after the
first KDM6 call. The first saved coordinate is `(230,70,3)`:
`QC=8.4692146629095078e-9` was cleared while `QNC=2021875.875` remained.
The values persisted through step end, next step begin, and FogDES input.

The optional MP37 moisture-call policy preserves scheme-committed QC/QI/QR/QG;
KDM6's joint cleanup owns their QNC/QNI/QNR/QIB partners. Vapor, snow, scalar,
chemistry/tracer calls, and `microphysics_zero_outb` retain their prior rules.
No number is recreated at the FogDES entrance.

### Completed RK source, transport, and storage

The native update retains an admissible old source/air map. If that full map
fails for a whole cloud/ice pair at RK3, the opt-in fallback stages the actual
intensive REAL32 physical source, explicitly includes later non-air additions,
and applies common old-donor air fluxes. Source/carrier/timestep references are
validated before an atomic candidate commit. QR/QG non-air rates are preserved.
Air transport must apply at fraction one; shrinking the whole air step fails.

V15 completed step one and the next FogDES, then rejected 131 rain candidates
at RK1 of step two. The shared-face rates were calculated in REAL64 but each
was independently cast to REAL32 before the kernel consumed them. V16 passes
the original REAL64 rates directly for all pairs. REAL32 API/diagnostic arrays
remain range-checked; face donors, velocities, source rates, and strict PSD
predicates are unchanged. The independent ledger audit found strict-bound violations in 63/81
source-only and 78/81 air-only positive-number rate pairs; all were within
the historical 8-ULP band. The causal decomposition is recorded separately;
this precision correction is not a wider physical tolerance.

The bounded joint quantizer accepts only a valid continuous pair. For normal
strict-volume states it derives the representable Q interval from the ordinary
stored N and both exact and REAL32 volume products, then selects a valid Q
without changing the bounds or regenerating N. Other storage paths retain
their existing adjacent-value policy. Explicit subnormal joint absence is limited to the declared Q
quantum policy. Signed Q/N representation deltas and counts are mandatory.
These are numerical changes, not phase transitions or conservation repairs.
The native pressure-carrier ledger is not relabeled kg or total energy.

### RK1 rain diffusion precision

A diagnostic-only V17 replay kept V16 physics and reproduced its second-step
failure. At `(i,j,k)=(110,5,18)`, rain Q/N tendencies were both zero before the
actual `horizontal_diffusion` call. Its REAL32 output exactly matched the
source rates in the failed joint candidate. Replaying the recorded R32
stencil operands reproduced the source output bits.

The same default `m` stencil evaluated in REAL64 gives a mean particle mass
`2.930932076770217e-10`, above the selected rain lower bound
`2.9309320335276967e-10`. The original candidate was below it at
`2.9309320040144683e-10`. This is a one-cell producer diagnosis, not proof that
all failures share one cause.

The precision candidate brackets only that diffusion call:
`delta = R64(tendency_before) + diffusion64 - R64(tendency_after)`.
The original host tendencies remain unchanged. An explicit per-timestep
array carries the separate Q/N corrections to the native rain source rate,
where each is added once without another carrier factor. The rate is reused
with the existing RK weights. Signed candidate amounts are reported separately
for Q and N; they cannot be summed across RK stages as a physical-time budget.
The exact host stencil footprint and all completed endpoint gates remain.

The helper uses the same stored coefficients, metrics, hybrid carrier, and
shared-face stencil. Its pinned Intel O0/O2 regression covers nonuniform
geometry, closed area-weighted face cancellation, and paired mixing. The
matched V18 native experiment is being checked separately. The final generator
also restricts capture explicitly to MP37; frozen V18 predates that additional
inactive-scheme guard.

See [the source replay and bindings](evidence/pr87_two_step_v17diag_20261016/)
and [the candidate source/build archive](evidence/pr87_two_step_v18_20261016/).

### Rain sedimentation and the public number basis

Rain retains its distinct mass- and number-weighted velocities. One admitted
face fraction applies both moment proposals using the existing extensive
column kernel. Surface loss and signed storage differences are recorded.
This changes the former independent rain numerical update.

The completed native/public rain stores use the selected default-REAL source
coefficients: `pidnr=12566.37109375`, `dmr=3`, lambda `961..35000`.
The live module values are asserted. The PIDNR value is also reconstructed
from a captured PSD-boundary row. The exact volume-number predicate is checked
on continuous values, the stored REAL64 product, and the actual REAL32 density
multiply consumed on re-entry. Invalid continuous states are rejected; no
number floor or wider nongraupel PSD gate is used.

The wrapper receives dry density from the executed host path and preserves it
through the call; it does not divide DEN again by `(1+rv)`. Gas density is a
separate derived quantity. The public-store ledger records Q/N representation
changes and actual number re-entry error with local density/layer geometry.

### Warm intermediate states and zero steps

V13's strict warm experiment exposed a caller error: status
`NO_FEASIBLE_STEP`, alpha zero, and a valid base were followed by no trial and
an incorrect endpoint-search fatal. The scoped correction evaluates retry-zero
status-one through the existing trial body and validator, including pending
rain-number-to-CCN transfer. Genuine search failure and exhausted positive
endpoint retries remain fatal.

V14 then showed that a new full rain PSD requirement at warm admission rejected
an intermediate paired state with `QR=3.3340966e-10 < qcrmin=1e-9`.
V15 restores the original warm `consumer_pair_only` domain. Completed air,
rain sedimentation, and public stores remain strict. A transient warm state is
not counted as a valid completed public state. Only status-one warm rows are
emitted; that sparse ledger is not a full warm activity census.

## Parallel cold-process findings

The frozen v17 NG/AUT/G ledger separates group alpha from composite gamma.
Most AUT/G suppression is individual admission, with much less from shared
backtracking. Full-proposal reason probes classify AUT as rain PSD and most G
activity as bulk-density incompatibility. These are first failed full-proposal
checks, not proofs of the unique bound determining the accepted alpha.

See [the weighted distributions and scope](PR87_COLD_CAUSE_DISTRIBUTION_20261016.md).
Their half-L1 group activity is not primitive gross reaction throughput,
precipitation loss, or latent heat. The G volume/receiver definition is the
next selected physical investigation; the 417 kg freezing path remains a
separate smaller case. These baseline statistics do not describe all later
candidate physics.

## Validation and remaining gates

Fortran validation uses the pinned Intel profile and fresh scratch builds.
The native executable is a selected-object partial-host overlay, not a clean
rebuild of WRF and all libraries. Exact component replay, manufactured kernel
regressions, actual matched runtime, and scientific validation are separate.

Full stage audits retain negative QV predictor states; a paired-moment pass
cannot hide them. Completed RK3 and KDM6 boundaries must be assessed separately
from the earlier RK predictor stages. Host hybrid-carrier closure, total
energy, observation retention, force/continuity balance, and initial-shock
reduction remain OPEN.

The snapshot schedule is shared by preparation, parsing, and completion:
`{20,60,300,600} <= requested_end`, plus the requested final time. Missing or
duplicate steps, fatal logs, truncated data, and input/executable changes still
fail. The 40-second request therefore requires 20- and 40-second snapshots.

After two-step validity, continue the same frozen model/input policy through
60 seconds and 600 seconds. Compare physical signals and dynamics with OFF;
normal exit or a quieter cloud field alone does not establish scientific
improvement.

## Evidence navigation

- [Checklist](PR87_FAST_COMPLETION_CHECKLIST_KO.md)
- [Independent team review](PR87_TEAM_REVIEW_20261016.md)
- [Historical candidate failures and source identities](PR87_TWO_STEP_INVESTIGATION_HISTORY_20261016.md)
- [Timestep state circulation](PR87_STATE_CYCLE.md)
- [Completed source/air map and numerical ledger](PR87_SOURCE_FIRST_GROUPED_TRANSPORT.md)
- [V13 zero-step causal component payload](evidence/pr87_two_step_v13_20261016/warm_endpoint_component_receipt.json)

## V19 closed two-step attempt

Both arms preserve the staged/original input identities and complete step one.
The second FogDES, RK3, and PRE_KDM6 pass their recorded pair/conversion checks.
Four negative vapor predictors occur at second PRE_RK/RK1 and five at RK2;
they are retained in the all-field audit. Completed RK3 and PRE_KDM6 have no
reported field, pair, or conversion violation under that auditor's declared
policy, which includes its historical 8-ULP diagnostic cone classification;
the consuming rain storage/sedimentation predicates remain strict.

Both runs abort with `PR87 rain sedimentation packet rejected`. The sparse
rain ledger's final call is model step 2, wrapper j=5, dt=20 s; columns 2..108
returned successfully at substep 1. The next eligible column lacks its row.
A missing success row does not identify the helper's rejection predicate.
The original receipts had no `earliest_fatal` because their collector did not
recognize the bare PR87 message. Their `INCOMPLETE`/exit-128 classification is
unchanged; original receipts are preserved and a separately hashed fatal
collection addendum records the message. The collector now recognizes bare
research-kernel rejection messages and its 13 focused tests pass.

Runtime receipts, sparse rain ledger, and independent stage audits are archived
under `evidence/pr87_two_step_v19_20261016/runtime/`. This remains a selected
partial-host research build, not a clean full-model validation.

## V20 failure-only causal replay and updated-density candidate

V20quiet OFF reproduces V19's same first-call pre/post bytes, completes only
20 seconds, and rejects at rain helper `(step,i,wrapper_j,substep)=(2,109,5,1)`
with `mstep=2`. Its 39-layer diagnostic gives the same level-19 Q/N/density
as the independently read PRE_KDM6 state. The exact-column Intel O0/O2 replay
rejects its initial strict rain cone only at k=19, before changing the column.

At that level, public Q is `5.0788977190574514e-11` and specific N is
`0.1732860952615738`; dry density is `0.5744202733039856`.
The REAL64 volume product `0.0995390461999337` is below the strict maximum
`0.09953904705024956`, while ordinary REAL32 storage produces
`0.09953904896974564`, above it. Neither a negative input nor FTZ explains
this case. Offline scans find 50 such stored-volume crossings, and zero
continuous rain-cone violations, in each arm's second PRE_KDM6 state.

The grouped update runs before `calc_p_rho_phi`. That routine updates AL
before RK-end observation, so a conversion-valid store against the earlier
density need not remain conversion-valid against the final density. In this
actual nonhydrostatic path AL does not depend on rain Q/N. The focused next
candidate therefore reuses the existing joint store after the RK density,
filters and boundary operations, before exposing RK_STAGE_END. It holds public
N fixed and stages only representable Q changes under unchanged continuous
and stored source limits; it does not move the host density or physical rates.
Q changes are signed numerical representation terms, with prospective volume
rounding reported separately. They are not physical sources, energy closure,
or an area/time-weighted inventory. Host validation remains pending.

The earlier V20diag build omitted the established suppression of repetitive
argument-temporary warnings. It was stopped by the operator (exit 137) and
preserved separately; no diagnostic completion is claimed. V20quiet restored
the matched configuration and supplied the actual failing-column evidence.

## V21 frozen integration and prelaunch review

V21 source composition and selected-object build pass with executable SHA256
`163194856a21802610b1e4ed1664123c12e82660a97077dde6068d61544a6342`.
The complete RK stage calls the atomic rain representation transaction after
all density/filter/boundary changes and before `RK_STAGE_END`, over the same
2,533,440-cell consumer support. The helper derives dry density with the
existing REAL32 `1/(AL+ALB)` procedure. No AL, public NR, physical tendency,
or source PSD coefficient is changed.

The new wrapper stages Q for the whole tile and closes its ledger before any
host commit. Invalid continuous input, no representable strict endpoint, or
ledger failure leaves host Q unchanged. Its actual signed Q changes are
recorded separately from prospective ordinary volume-number rounding; the
latter is not an RK number-state increment or a physical-time sum.

The initial draft's generated bound order differed from the wrapper ABI.
Root caught this before a native build; the corrected interface and exact
ordered argument list now share `(i,j,k)` active bounds. Source-order tests,
invalid-flag preflight, and pinned Intel O0/O2 tile tests cover the corrected
call/transaction and later-cell rollback. A separate review composition
reproduces the frozen source hashes. The final 26 affected tests pass; build,
source and test receipts are under `evidence/pr87_two_step_v21_20261016/`.
Actual matched 40-second receipts remain pending.

## V21 closed result: rain conversion closes, cold ice proposal does not

OFF and COUPLED each close `INCOMPLETE`, exit 128, with one completed
20-second step. The second RK3/PRE_KDM6 now have zero continuous or stored
strict rain-volume crossings (previously 50 per arm); the second rain packet
sweep passes. First-call pre/post dumps remain byte identical to V19 in both
arms. These scoped corrections do not establish a completed second step.

The next failure is `KDM6 invalid base before nongraupel admission`, at
`(step,wrapper_j,i,k,loop)=(2,6,89,18,1)`. The exact source diagnostic has
QI bits `0000003E` (`8.688050478813866e-44`) and NI=0. It fails ice-pair
validity before the tiny-ice PSD exemption. Rain N is already volumetric in
this diagnostic; compare `0.007147877011448145` directly with bounds
`2.9672511882360046e-5 .. 1.4334689243460015`. Rain is valid here.

Both host traces have QI/NI=0/0 through second PRE_KDM6 at that point; the
orphan appears inside the KDM6 call. Source review identifies an NI reset in
raw ice-sublimation rate construction before later caps and approved mass
updates. This branch is the identified source candidate; its execution at
the failing point is not independently captured yet. The next overlay defers
that reset to actual stored extinction in the approved joint transaction,
with a narrowly scoped pending state inside the search. No count is to be
removed from a positive accepted QI state, and final storage remains strict.

The bit pattern also illustrates the rate/amount distinction: 62 minimum
REAL32 quanta divided by 20 seconds round to 3 rate quanta; multiplying that
stored rate by 20 removes 60, leaving 2. A raw rate equality alone does not
prove that the stored ice mass is exhausted.

## V22b: defer ice count extinction to the approved stored endpoint

The closed V21 runs pass the second rain sedimentation and reject the NG base
at `(i,wrapper_j,k)=(89,6,18)`: QI bits `0x0000003E`, NI zero. Rain at that
point is already in internal volume-number units and is within its selected
bounds. The full-field step-two PRE_KDM6 has QI/NI zero at this coordinate;
those snapshots do not identify the internal producer of the tiny QI.

The selected cold source resets NI while proposing a full-sublimation rate,
before saturation caps and process admission. Equality of that rate with
`-QI/dt` does not establish stored extinction: with QI `0x3E` and dt 20,
the source-order REAL32 rate removes 60 minimum quanta and leaves QI `0x02`.
This is a source-order mechanism; the V21 failure record alone does not prove
that the equality branch executed at that cell.

V22b retains NI during rate proposal and uses a pending marker only in the
cold NG/AUT/G search. It permits an exact-zero-QI intermediate search endpoint
with pending NI. Each assembled local REAL32 composite clears NI only if QI
is exactly zero, then runs the strict endpoint check and atomic state commit.
A positive QI endpoint retains its computed NI. There is no proportional NI
loss, floor, new physical tolerance, or exception in the final stored checker.

The sparse ledger labels internal NI in m^-3, records raw/capped rates,
preproposal and final moments, the candidate NI immediately before clearing,
and the signed extinction amount separately. Search alpha and composite gamma
are recorded separately. Its leftover `n_sed` index is not a cold-substep ID.

The frozen complete selected-module build passes. Extracted source helpers and
source contracts pass pinned Intel O0/O2, including the 62-to-2-quanta case,
strict orphan rejection, exact full extinction, and vapor-limited partial
approval. The focused batch passes 26 tests. Both matched 40-second runs closed INCOMPLETE after 20 seconds. The actual
step-two equality event at `(89,6,18)` now retains NI unchanged while stored
QI goes from `0x3E` to `0x02`, with all process ratios one and zero count
extinction. The later rejection is cloud PSD at `(89,14,18)`. Bindings are in
[the V22b archive](evidence/pr87_two_step_v22b_20261016/).


## V23c: source-cone correction experiment

The V22b target cloud pair is zero/zero through second RK2, first appears at
completed RK3, and is unchanged at KDM6 entry. Its Q/N ratio is
`4.188790433087336e-15`. The actual RK fragment accepts PI64-derived cloud
minimum `4.188790204786391e-15`, whereas KDM6's initialized REAL32 `pidnc`
requires `4.18879052734375e-15`. Both the continuous specific-number product
and stored volume-number product are outside the consumer's strict cone.
This is a producer mismatch; adjusting an already invalid KDM6 input would
not establish a valid continuous update. The preserved first-call public
returns also contain cloud unit-rounding crossings under the source cone.

V23c derives cloud mass and volume bounds from source REAL32
`pidnc=523.59881591796875`, d=3, lambda 12000..500000. The kernel accepts
independent per-pair volume bounds for cloud and rain, with its original
single-pair API retained. Each selected pair must pass the continuous
source-order predicate before its directed joint storage is considered.
The full common-air fraction remains one.

The existing scalar public-store algorithm is reused for cloud and rain;
the original internal volume number is now checked directly before dividing
by dry density. The updated-density wrapper stages both Q fields, leaves
NC/NR unchanged, and commits only after all cells and the ledger succeed.
Signed representation deltas remain numerical terms, with prospective
volume-number rounding separate from actual committed changes.

Pinned Intel O0/O2 regressions include the actual invalid cloud pair beside
a valid rain pair, public-unit rounding from a valid internal cloud state,
and all-or-nothing cloud/rain density storage. The current focused suite
passes 34 tests. A fresh selected-module build and independent review passed.
Both 40-second attempts then completed 20 seconds and rejected 223 cloud
continuous candidates at second RK1; no two-step completion is inferred.
Earlier hash-pinned transforms are composed using the retained V22b kernel
body, then only that body is replaced by the current kernel before compilation;
both identities are recorded. Compiler module hashes are captured after
compilation separately from staged parent interfaces. The unexecuted V23b
build and its provenance findings remain preserved.


## V24c: cloud/rain diffusion precision and strict graupel storage experiment

V23c's full-failure records identify cloud source tendencies outside the exact
source cone. They do not isolate diffusion. V24c therefore adds one sparse
cloud stencil PRE/POST capture while extending the already reviewed REAL64
scalar diffusion evaluation to QC/QNC as well as QR/QNR. The original host
REAL32 call, coefficients, footprint, and tendency arrays stay intact. Four
explicit per-timestep channels carry signed rate corrections to the matching
RK consumers. A cloud source-first reset reuses its correction once after the
later-source assignment; the ledger reports each channel once per evaluation,
not a physical-time sum of RK stages.

The G strict-mass option applies only to QG/QIB. It checks the exact continuous
100–900 ratio before any representation choice, holds stored B fixed while
selecting representable Q, and rechecks the stored ratio. No number-density
multiply is imposed on B. This addresses a concrete risk from 53 active
second-RK3 G pairs in V22b that exceeded 900 inside the old 8-ULP band.
Inactive paired ice is not assigned an active PSD contract.

The fresh V24c selected-object build and static team review pass. The full
transport kernel passes pinned Intel O0/O2, including rejection of a NaN
density before an ordered comparison. The earlier V24 trace syntax failure
and unexecuted V24b build are preserved as separate records. V24c matched
40-second runtime is in progress; no new runtime PASS is claimed here.

## V35diag closed: captured G interval replay

V35diag closed with the same step-two cold-rain `SEARCH_FAILURE` as V34. The
failure-only record identifies `(step, call_lat, i, k)=(2,63,204,17)`;
`call_lat` is a wrapper-local index, not a mapped global latitude. Its first
20 seconds match V34 OFF bit-for-bit across the six recorded states and twelve
fields. The captured base passes the state validator, while the full G proposal
fails the strict rain endpoint check (reason 6); vapor passes.

The isolated O0/O2 replay of the captured call confirms that the search
exhausted its declared 32-ULP walk. Across the continuous G-active alpha
interval, the rounded endpoint rain pair is the same at both ends, and a
monotone bound proves every stored rain pair in that interval violates the
strict upper rain bound. This establishes a no-storable-endpoint result for
that specific interval and call; it does not establish global physical
infeasibility. Reproduction inputs, compiler records, hashes, and replay
receipts are preserved in
[the stored interval evidence](evidence/pr87_stored_interval_gap_20261016/)
and [the V35diag runtime archive](evidence/pr87_two_step_v35diag_20261016/).

## V36: proven-impossible G interval pruning; matched runs pending

V36 changes only the G search-domain handling for this proven case. The
existing full-PSD search skips a continuous alpha interval only when
inward-rounded bounds and REAL32 endpoint enclosures prove that its stored
rain pairs all violate the strict rain PSD check. Nonfinite or uncertain
bounds do not prune; pair-only searches and zero-mass/absence cleanup remain
unchanged. The exact V35 witness now resolves to `NO_FEASIBLE_STEP` with a
valid base, allowing the existing caller to use its validated zero-G proposal
and withhold linked G terms together. No endpoint is newly accepted, and no
tolerance, floor, or source proposal is changed.

The V36 selected build and focused tests completed successfully: 171 tests
passed. At the latest recorded status, matched OFF/COUPLED 40-second V36 runs
were still running, so there is no V36 runtime completion or budget result to
report. The source/build and focused validation are archived in
[the V36 evidence bundle](evidence/pr87_two_step_v36_20261016/); runtime
receipts belong here only after the runs close.

The cold cause ranking remains the saved-v17 result. For AUT, all emitted
proposal activity first fails the rain endpoint check. For G, the largest
first-failure category is bulk density (84.44–84.45% of emitted proposal
activity), followed mainly by rain, orphan, donor-negative, and ice checks.
These are first failed checks on full-proposal endpoints, not unique
certificates for the active alpha bound. The activity denominator is the
half-L1 Q/QV proposal-vector measure; it is not primitive gross reaction
throughput, a physical budget, or latent heat. V36 adds no new cold AUT/G/NG
distribution, and the next cold-physics target remains the G bulk-density /
volume representation question, with AUT rain compatibility tracked
separately. See [the saved-v17 cause distribution](PR87_COLD_CAUSE_DISTRIBUTION_20261016.md)
for denominators and per-arm values.

## V36 closed: ProgB round-trip failure

Both matched V36 40-second runs closed INCOMPLETE with return code 128 after
the first completed timestep. The second-step RK3 and PRE_KDM6 strict audits
pass; timestep 2 POST_KDM6 is absent. Both arms fail at `ProgB unsupported PSD
state rejected`, so the V36 search-domain correction did not complete the
40-second target. The earlier V36 paragraph records the status while the runs
were active; this closure supersedes its pending-runtime note.

The archived strict audit confirms completed endpoint gates through timestep
2 RK3/PRE_KDM6, with negative early scalar-Q predictors kept separate from
completed states. The build, run receipts, stdout, and independent review are
in [the V36 runtime archive](evidence/pr87_two_step_v36_20261016/runtime/).
The 40-second completion criterion remains unmet.

## V37diag: actual ProgB one-ULP rewrite identified

V37diag is observational relative to V36: all six timestep-1 state records and
twelve REAL32 fields match V36 bit-for-bit. It closes INCOMPLETE before
timestep-2 POST_KDM6. The failure-only context locates the sequence at
ProgB context 6, `(call_lat,i,k)=(116,33,20)`: the BG rewrite changes the REAL32
value by one ULP, from bits `0x35F68E57` to `0x35F68E56`. The resulting Q/B
ratio is `900.00002624039394`, above the strict 900 bound; context 7 then
rejects that unsupported state. This establishes the immediate measured
failure sequence, not a wider physical cause. The independent review and
diagnostic records are archived in
[the V37diag runtime evidence](evidence/pr87_two_step_v37diag_20261016/runtime/).

## V38: removing the rewrite exposes first-step melt failure

V38 removes only the post-ProgB `BG=QG/rhox` rewrite. Both arms still close
INCOMPLETE, this time during the first KDM6 call with `KDM6 invalid nonfinite
or negative species state`. Their timestep-1 PRE_KDM6 inputs match V36
bit-for-bit, but there is no POST_KDM6. The traced failing SLOPE04 state has
QG zero and a tiny negative BG: OFF at `(i,lat,k)=(137,16,1)` with
`BG=-2.77555756e-17`, and COUPLED at `(136,17,3)` with
`BG=-2.84217094e-14`. The melt path subtracts through rounded `rhox` arithmetic.

The current follow-up is a linked-melt proposal using the existing process
fraction, so QG and BG remain coupled at the approved endpoint. That change
has not yet been validated; these V38 runs do not pass the 40-second target,
and no physical success or budget claim follows from them. The source change,
both run receipts, trace artifacts, and independent review are retained in
[the V38 runtime archive](evidence/pr87_two_step_v38_20261016/runtime/).

## V39: 40-second execution complete; strict ice audit fails

Both matched V39 40-second runs completed with two unique POST_KDM6 records,
return code 0, unchanged inputs, and a common-air map of theta=1 for every
timestep/RK row. The independent completed-state audit nevertheless fails in
both arms: timestep-2 POST_KDM6 has 13 ice pairs outside the declared
8-REAL32-ULP ratio allowance. The pairs have positive QI and NI, but all lie
below the consumer validator's inactive-ice mass threshold, where its own
ratio check is skipped. This is a strict-audit/policy-scope mismatch to
resolve; no checker was weakened. Other audited cloud, rain, graupel, and
conversion gates pass. Thus runtime execution completed, but strict validation
and full scientific approval did not.

The V39 independent review records the exact 13 cells and ratios in
`ice_gate_context`; build and matched-run evidence are retained in
[the V39 40-second archive](evidence/pr87_two_step_v39_20261016/runtime/).

## V39 60-second extension: timestep-3 RK1 candidate infeasible

The matched 60-second extension returns code 1 in both arms. Timesteps 1 and 2
reach POST_KDM6; timestep 3 reaches PRE_RK and fails during RK1 because the
full joint moment candidate is infeasible. There is no timestep-3 POST_KDM6,
so the 60-second target is incomplete. The failure sweep reports 256 full
candidate failures per arm: 255 ice-pair rows and one graupel-pair row.
Separate source-only diagnostics are not committed failures. Ten of the 13
timestep-2 ice outlier coordinates overlap timestep-3 ice full-candidate
failures, but this overlap does not prove that those earlier outliers alone
caused the later failure. Receipts and the independent failure review are in
[the V39 60-second archive](evidence/pr87_two_step_v39_20261016/runtime60/)
when present in the evidence bundle; the review source is
`/var/tmp/pr87_v39_60s_review_20261016.json`.

Neither run establishes strict full-PSD approval: the 40-second audit fails
on ice, and the 60-second extension fails before its third POST_KDM6 state.

## V40diag: ice sedimentation crosses two of the 13 target cells

The closed OFF V40 diagnostic completed timestep 2 and reproduced the V39
first-call pre/post arrays and joint-stage records bit-for-bit. Its
cell-matched sedimentation trace finds lower-cone crossings in two of the 13
ice outlier cells: `(110,208,19)` and `(126,241,19)`. Both were on the lower
bound immediately before the ice sedimentation helper and moved only slightly
below it afterward. The other 11 targets were in-cone at each observed
post-sedimentation endpoint. The final POST_KDM6 ratios in the two event cells
are about half the lower bound, so this small sedimentation crossing does not
explain the final magnitude or the other 11 cells. This was an OFF diagnostic,
not a matched production validation or a physics fix. Details and hash
bindings are in the [V40 causality record](evidence/pr87_two_step_v40diag_20261016/ice_sedimentation_causality.json)
and [V40 runtime archive](evidence/pr87_two_step_v40diag_20261016/runtime/OFF/).

## V41diag: cold composite exhausts QI in all 13 targets

The closed OFF V41diag run completed two steps, then failed during timestep 3
RK1; it is incomplete. Its T2 cold KDM6 ledger contains one row for each of
the 13 V39 targets, with no corresponding warm T2 row or pending-sublimation
event. In every row the full nongraupel ice-mass request is `-QI_before`, the
inferred initial nongraupel alpha is `0.9999999403953552`, and the composite
retry ends at gamma `0.5` (retry index 1). Replaying the complete logged rate
vector in native REAL32 source order at gamma 1 produces `QI=0` while internal
ice number volume remains positive and unchanged. At gamma 0.5 the replay
matches the actual positive QI endpoint.

The endpoint path differs across three cells. In 10, the Pidep component
matches the full-removal cap after the nongraupel alpha. In `(131,196,18)`,
`(132,223,19)`, and `(126,241,19)`, positive `psaci` also contributes to ice
Q loss, so the total request still exhausts QI although Pidep alone does not
match the full-removal cap. The pending flag is set only when raw Pidep equals
`-QI/dt` before capping; that eligibility test misses the logged combined
endpoint. With the flag false, the validator rejects the gamma-1 orphan pair.
The gamma-0.5 candidate keeps QI positive but below its transient ice-mass
threshold, where the validator skips the PSD ratio check; this explains how
the half-QI endpoint is accepted by that path while remaining below the
strict lower cone.

The result identifies a cold-process endpoint/pending mismatch; it does not
validate a fix, establish full-run completion, or grant strict PSD approval.
The selected source, receipt, generator, and row-level replay are
hash-bound in the [V41 replay](evidence/pr87_two_step_v41diag_20261016/ice_lineage.json)
and [V41 lineage inventory](evidence/pr87_two_step_v41diag_20261016/lineage_archive_manifest.json).
The [provenance incident record](evidence/pr87_two_step_v41diag_20261016/provenance_incident.json)
documents that the prior frozen manifest could not be recovered. At the time
this V41diag result was recorded, V42 follow-up was pending.


## V42: matched 40-second run passes strict completed-state review

Both matched V42 arms completed 40 seconds with return code 0, two distinct
POST_KDM6 states, unchanged original and staged inputs, and all six JOINT_RK
rows at theta=1. The independent review reports PASS for the completed-state
audits: the exact selected cloud, rain, and graupel contracts pass, and the
existing ice 8-ULP completed-state gate is unchanged and passes. Exact
source-coefficient ice diagnostics are reported separately and do not replace
or widen that gate. The review also records negative QV predictor counts of
4 at T2 PRE_RK, 4 at RK1 end, and 5 at RK2 end; these are intermediate
predictor diagnostics, separate from completed-state results.

The review file is SHA-256
`b6530931a16aa4587729109f51bb638f15dc1d399e43887e9b7f020899efc98a`.
Receipts, preflights, launch records, runtime artifacts, and the independent
completed-state audits are retained in the [V42 40-second archive](evidence/pr87_two_step_v42_20261016/runtime/).
This is a selected-object pinned Intel partial-host validation, not a full
clean WRF build or a general physical approval.

The same-executable matched 60-second runs are INCOMPLETE in both arms, with
return code 128 after completing timesteps 1 and 2. The earliest fatal is
`ProgB transient PSD state rejected`; neither arm produces a timestep-3
completed state. The 60-second receipts and runtime artifacts are retained in
[the V42 60-second archive](evidence/pr87_two_step_v42_20261016/runtime60/).
No producer attribution is claimed here. A 600-second run was not run while
the timestep-3 failure remained.
