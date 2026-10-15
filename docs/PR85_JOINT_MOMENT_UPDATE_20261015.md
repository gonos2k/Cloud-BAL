# PR85: completed native moment updates

PR85 retains the PR84 OFF and COUPLED Q/N/B inputs for 2026-08-16 13 UTC.
It addresses the completed air updates and native processes that consume
those inputs. The research policy is
[PR85_JOINT_UPDATE_POLICY_20261015.json](PR85_JOINT_UPDATE_POLICY_20261015.json);
closed execution results are bound separately in
[the integration receipt](evidence/pr85_integration_20261015.json). The compact
[execution evidence](evidence/pr85_execution_20261015.zip) and its
[package manifest](evidence/pr85_execution_manifest_20261015.json) retain the
independent audits, original receipts and validation logs.

The supported experiment uses one domain, MPI rank, thread and tile, RK3,
explicit vertical scalar advection, Shinhong every model step, and a 20-second
window. Unsupported transport, tile and PBL-cadence configurations fail
explicitly. Initialization, completed RK, first KDM6 pre/post and model exit
are separate gates. A successful initialization wrapper does not establish a
successful integration.

## Completed air updates

The PR74 common Shinhong QV/QC/QI/QNC/QNI path was already linked in the
retained executable. Its new REAL64 witness uses the actual REAL32 matrix and
RHS, including the sequence-associated lower diagonal `al(k-1)`. Only an
exactly empty Q/N base with a positive, in-cone unrounded common-solve import
is eligible for its representation gate. If legacy REAL32 tendencies give an
invalid stored pair at an RK3 fraction, both imports are withheld and recorded.
Existing particles and genuinely invalid ideal proposals remain visible to
admission checks. The DEL-pressure-weighted ledger is not a kilogram budget.

MP37 FogDES uses donor-approved Q/N faces with distinct Stokes-integrated
mass and number speeds, VQ/VN=5/3 for the declared generalized-gamma alpha=3
PSD. Ground VDFG deposition is a separate paired sink. This changes the
selected atmosphere transport; the legacy entry point remains available.
Local rho-dry times thickness accounting does not establish a native global
water budget.

KSAS cloud/ice mass births receive an explicit
[process-specific PSD number prior](PR85_KSAS_SOURCE_PSD_POLICY_20261015.json)
before carrier coupling. Negative source packets use the existing N/Q ratio.
Proposed births and actual REAL32 additive increments are recorded separately.
This conditional prior is not a number observation.

Selected scalar advection uses shared old-time upwind faces for QC/QNC,
QI/QNI, QR/QNR and QG/QIB. Snow mass and ambient CCN retain their separate
single-field meanings. The carrier is `c1h*(mu+mub)+c2h`, with native map
factors and signed eta flux. A complete grouped candidate must pass before
commit, and the admitted air-transport fraction must be one. This first-order
research replacement changes the selected high-order native transport.

## Native carrier and source contracts

The executed utility/solve/driver chain establishes KDM6 DEN as dry density:
`moist_physics_prep_em` assigns `rho=1/(AL+ALB)` before microphysics and the
driver passes it unchanged. The earlier `phy_prep` moist density is not the
entry value. Dividing DEN by `1+QV` again introduced an extra conversion, up
to approximately 2.216% in the retained v13 pretrace.

Public number conversion now uses the supplied dry DEN directly. Gas-property
calculations receive a separately checked `rho_gas=rho_dry*(1+QV)`; the dry
carrier is retained without a rounded roundtrip. New PR85QND2 stage records
observe active AL/ALB directly. Historical PR85QNB1 records and PR83/84 receipt
bytes remain unchanged and cannot certify this corrected density contract.

The [200-micrometre correction](PR85_ICE_TRANSITION_CORRECTION_20261013.md)
supersedes PR84's non-reachability claim: `6**(1/3)/9080` is approximately
200.1234 micrometres. Actual branch events require their own source trace;
the number of high-ice initialized cells is not an event count.

`kdm6init` also initializes the previously unassigned saved coefficient
`rslopecdmax=rslopecmax**dmc`. This corrects a physical rate input. The final
graupel radar intercept cache is refreshed from the current supported PSD;
absent graupel receives an absent cache.

## Coupled native process transactions

Ice settling retains the native distinct mass/count velocities and substep
feedback. REAL64 face proposals are admitted jointly against stored donor and
receiver states. A positive packet must change both stored channels at both
ends; an unrepresented loss cannot fund a receiver gain. The ledger retains
actual REAL32 inventory residuals. This is not exact stored-column or global
energy conservation.

Graupel settling reuses that paired core with its own carrier and domain.
QG and specific BG retain the same native mass-velocity rate and top-down
face order; stored BG is used directly. Their column inventories are
`rho_dry*dz*QG` and `rho_dry*dz*BG`, whereas internal ice number uses `dz*NI`.
The next slope calculation runs after every native sedimentation substep.
Its G pair must be absent or density-supported and active. The admission
search partitions the disconnected absent/transient/active domain and checks
actual stored endpoints. An unsupported small incoming tail is withheld in
both components and remains at the donor. This conditional limiter can stall
subthreshold packets and changes effective settling; no unresolved reservoir
or maximal-throughput result is claimed. Integrated ground packets and the
legacy rate accumulators retain their separate units.

Small snow melt at or below native qcrmin uses a mass-normalized particle from
the native snow PSD. Its liquid destination is cloud when that mean particle
mass fits the cloud interval, otherwise supported rain. The same approved
snow mass and latent cooling are retained. This conditional representation
rule changes species assignment and higher PSD moments; larger-donor melt
retains its original path. Unsupported positive melt is reported and rejected.

Contact and immersion freezing calculate number rates for every positive
cloud-number donor and admit cloud mass/count, ice mass/count and heat as a
single packet. A packet that cannot be stored at both ends is deferred in
full. The native stage-1 count closure is skipped for QI below REAL32(1e-14).
A positive paired ice base in that precise skipped-closure range may enter
the freezing transaction; accepted endpoints retain strict cloud/ice PSD and
storage checks. Equality at the threshold remains in the active category.

Rain freezing retains the native proposed volume `frozen_mass/denr`, where
`denr=1000 kg/m3`. An absent graupel receiver cannot accept that packet inside
the existing 100--900 kg/m3 density interval. The full mass/count/volume/heat
packet is then withheld; a supported existing mixture may admit a fraction.
This changes effective physical freezing and is a material research limit.

Cold reactions use three disjoint groups: non-graupel (NG), cloud-to-rain
autoconversion (AUT), then graupel/precipitation interactions (G). PAACW moves
two mass parts out of cloud, one each into snow and graupel, with matching
number loss, volume and fusion heating. Graupel volume uses the same delta2/
delta3 routing as mass. Independent AUT need not vanish with a deferred G
reaction. Dormant PGaut/PGacs remain guarded against unsupported activation.

Each trial rebuilds the actual native-order REAL32 transaction from pristine
primitive rates, recomputes volume terms and checks the stored result before
commit. Bounded interval searches distinguish a validated positive candidate,
no feasible step, and search failure. Nonzero rates may leave endpoints
unchanged; primitive-rate and stored-state no-ops require separate accounting.
Pending rain evaporation returns number to CCN only for exact stored QR=0.

An explicit cold-path option uses the same source stage-2 skipped-closure
range: positive paired QI below REAL32(1e-14). Its bounded search partitions
at the exact threshold and validates the actual stored candidate. At or above
that threshold, the strict ice cone applies. Cloud, rain and graupel retain
their strict conditions. The default helper mode and completed public-state
validator remain strict. This native stage category does not certify a PSD
inside the configured interval for the skipped-closure pair.

Warm rates use a common post-cap factor and atomic native-order stored-state
checks, including the following ProgB consumer's density and activity domain.
The search tests its helper fraction, up to 32 adjacent REAL32 fractions,
then up to 24 halvings; exhaustion remains fatal before commit. In the
captured boundary fixture, one adjacent step resolves QC undershoot while
retaining over 0.9999999 of the helper fraction. This is a bounded admission
policy, not proof of maximum throughput.

At the 18 existing rain/cloud/ice min/max-lambda count-reconstruction sites,
the native PSD closure now stores an inward REAL32 count from its source-bound
REAL64 interval. Original gates, masses and differential velocities remain.
The full native count reset and the additional storage correction are separate
ledger quantities, distinct from physical nucleation or entry number filling.

The existing final qmin/qcrmin cleanup remains unchanged. Its new cutoff
ledger records actual changed Q/N/B rows, thresholds and status transitions.
It also records unchanged vapor and temperature: discarded condensate is a
numerical term, not a physical phase transfer. Local unweighted sums do not
supply global carrier-weighted water or energy closure.

## Validation and acceptance limits

The integration receipt distinguishes the older full canonical snapshot,
subsequent focused tests, component replays and actual partial-host runs.
A nominal O2 test using `-check all` is checked-build evidence because Intel
warning 10182 disables optimization. Corrected harnesses use the pinned
reproduction profile for true O2; the original records remain preserved.

The final v17 same13 OFF and COUPLED executions both completed the first
20-second model step, including the first full KDM6 call, with return code 0.
The independent closed-run audit is `PASS_SCOPED`: original receipts bind the
unchanged inputs, source/build/executable identities and required traces.
The complete RK3, pre-KDM6 and post-KDM6 sequence passes strict density and
state checks across 2,533,440 active cells per arm. Native pre/post dumps
bit-match their corresponding stage records for all 12 checked fields.
Separate component runs at pinned O0 and true O2 produce byte-identical
post-state dumps.

The earlier v16 runs also completed, but their overall audit remains
`INCOMPLETE_OR_FAIL`: original receipts omitted `pr67_kdm6_process.raw`.
The collector now reserves and records that process trace, and v17 reran both
arms without changing physics or initial inputs. Original v16 receipts and
their failed inventory audit remain unchanged. Detailed process attribution
is separate from strict state admission and model exit.

Actual ice-to-snow events number 7,065 for OFF and 7,066 for COUPLED; these
are traced branch events, not an inference from initialized high-ice cells.
One event per arm removes QI without a representable positive QS increment.
The local stored-state residual is retained; exact stored or global mass
conservation is not claimed for that existing native operation.

These runs cover one 20-second step only. They do not establish global
carrier-weighted water, number or energy closure, an observation fit, native
force or mass-wind acceptance, or matched OFF/HYDRO/COUPLED responses at
10, 30 or 60 minutes. The cold, warm and graupel admissions may defer source
or face packets under their stated local representability and consumer
limits; their unweighted ledgers are diagnostic accounting, not global
budgets or evidence that withheld physics is negligible.

Earlier fast replays used assumed nonserialized constants that differed from
the host caller. Their findings retain that scope. Corrected replays import
the retained caller's constants; identical pretrace bytes alone do not prove
an identical full physical call. Failure-only diagnostic copies preserve
separate source/executable hashes and compare their raw trajectory with the
unmodified candidate.

Final host validation remains a selected eight-member replacement against a
preserved partial-host configuration, rather than a clean rebuild of all WRF
sources and transitive libraries. The exact source, archive and input bindings
are required for each result. Initial mass and T/q are unchanged, while the
transport and process-admission changes above affect subsequent evolution.

Physical dry-air, water and energy closure requires native cell weights,
carrier, time, boundary fluxes, physical transfers and numerical terms.
Independent observation fit, native force/mass-wind acceptance and matched
OFF/HYDRO/COUPLED 10/30/60-minute response remain open. Structural graph
freshness and a normal model exit do not establish those scientific results.
