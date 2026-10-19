# Final-RK source-first ordering in grouped low-order transport

## Scope and source connection

The frozen `solve_em` final-RK path calls `rk_update_scalar_pd` before
`rk_scalar_tend` / `advect_scalar_pd`. Its physical-source preparation uses
`mu_1` for both old and prepared carrier. The grouped MP37 condensates are
excluded from that stock path. PR85's grouped replacement instead adds a
physical source and an old-donor upwind tendency together.

The final candidate first tries the old-donor shared-face update, preserving
its REAL64 air rates directly. If the whole candidate is admissible under the explicit constrained
store policy, it retains those source and flux rates. At RK3 only, a failed
QC/QNC or QI/QNI PBL pair can select a source-prepared donor map for its entire
active support, followed by one atomic retry. A failed rain/graupel pair
forbids this fallback. Selection uses the exact full endpoint/store predicate;
it does not depend on a coordinate or timestep number. QR/QNR and QG/QIB
retain their established REAL32 non-air source calculation. This reproduces
the source-before-air ordering within that low-order operator; it does **not**
reproduce WRF's high-order positive-definite flux correction. RK1/RK2, rain,
graupel, snow,
CCN, flux geometry, carrier fields, and the physical source producer rates retain their
existing treatment; the selected fallback changes their representation as
described below. The original v17 and failed v2/v3 candidates remain
separate, preserved identities.

Implementation: [source-first overlay](../patches/pr87_source_first_update.patch),
composed after [storage overlay](../patches/pr87_joint_storage_update.patch)
by [the source composer](../tools/pr87_prepare_native_cycle.py).

## State equation and source counted once

For pair vector `x=(Q,N)`, old/new pressure carriers `m`, raw intensive
source `s`, and captured coupled source `S`, V9 first formed the explicit
REAL32 virtual stage on the source-active interior:

\[
z_i=\operatorname{R32}\!\left(x_i+
       \operatorname{R32}(\Delta t\,s_i)\right).
\]

The raw source is captured before `calculate_phy_tend` applies its REAL32
carrier coupling. A cloned `update_phy_ten` adds the same physical inputs to
shadow outputs, including the total pre-existing scalar tendency. The live
weighted update remains unchanged. Explicit timestep, carrier, and coupled
reference checks bind the capture to this consumer.

The outer donor ring remains the old boundary state and retains its full
PSD predicate. Prepared interior donors are virtual linear-flux operands:
they must remain finite, nonnegative, paired, within REAL32 range, and safe
for the declared number-density conversion. They are not committed or
consumed by a PSD routine, so this virtual intermediate is not asserted to
be a physically realizable PSD. An orphan/zero-quantum representation may
use only the existing bounded joint store, which first requires the ideal
continuous source pair to satisfy the full cone.

V10 also captures weighted REAL64 non-air source amount `D` added by RK1
after physics coupling. For a selected failed whole pair, the same face mass
flux and upwind donor are used for both components across the entire support.
The virtual donor used by the feasibility check is formed in the kernel's
REAL64 carrier order, `d=(m_old*z + dt*D)/m_old`; the local kernel base remains
`z` and its separate source is `D`. Its full endpoint is

\[
x_i^{new}=\frac{m_i^{old}z_i+\Delta t(D_i+A_i(z))}{m_i^{new}}.
\]

Physics and the later source each enter once. The complete continuous and stored
endpoint retains all existing PSD/conversion predicates and atomic commit.
All paired shared-face air tendencies remain REAL64 through the candidate
calculation. V16 removes the former independent REAL32 casts of the two air
rates, which could move a boundary donor's contribution outside the strict
rain cone. REAL32 diagnostic arrays are finite/range checked before casting.
Earlier stages and rain/graupel retain their established non-air source path;
the source-first fallback still applies only to cloud/ice at RK3.

The difference between `m_old*(z-x) + dt*D` and the original `dt*S` is explicitly
ledgered as a numerical source-representation term, including producer
coupling, staged arithmetic, and the later source. The two expressions need not be equal;
this is a declared numerical policy, not a neutral algebraic rewrite or a
physical conservation claim. V7/V8 instead formed a continuous donor from
already coupled `S`; their failed identities and receipts remain historical.

## Why additive old-donor transport can violate a pair bound

Take two periodic cells, carrier and timestep one, Courant number 1/4, and
bounds `N <= Q <= 4N`. Old pairs are `(1,1)` and `(1.5,1)`; sources are `(0,0)`
and `(-0.5,0)`. Both source-prepared donors are `(1,1)` and satisfy the bounds.

Transporting the old donors and then adding the local source gives cell two
`(0.875,1)`, outside the cone. Transporting the prepared donors gives `(1,1)`
in both cells. The summed source and the summed endpoint change agree, while
internal shared-face fluxes cancel. All these toy coefficients are dyadic;
the counterexample needs no rounding or tolerance change.

When prepared donors satisfy the cone, nonnegative shared donor weights
preserve `N>=0, m_min*N<=Q<=m_max*N`. Carrier continuity additionally makes
the weights sum to one. For a virtual donor outside the cone, this proof does
not apply; acceptance instead requires the unchanged complete-endpoint test. The existing donor CFL check is retained. The boundary-face and
carrier assumptions remain part of the selected native configuration, not a
claim for all WRF domains, nesting, or MPI layouts.

## Why the scope is limited to PBL cloud/ice

V5b applied source-first / REAL64 rates to all four pairs. Its incoming KDM6
state had one source-defined graupel transient at `(41,237,13)` with
`QG=2.5102110060709615e-13`, `BG=6.275527875166406e-16`. The first two RK
predictors had none; RK3 produced it, and v17 had QG=BG=0 at that site.
The partial window completed no model timestep. This is not an internal
ProgB creation or justification to relax its property contract.

V6 limits the source-order/rate change to paired PBL cloud/ice channels and
restores incoming G arrays bit for bit to v17, but the changed cloud/ice inputs
still expose an unsupported ProgB state within its first KDM6 call. It completes
no timestep. V7 therefore retains an admissible old update and retries only a
failed whole PBL pair, with one shared face map. This changes the numerical
operator when necessary to satisfy its declared state domain; it is not a claim
of exact native PD behavior. An admissible baseline can still have a storage
adjustment, so first-call bit identity additionally requires zero adjustments
and actual dump comparison.

## Storage is a separate numerical term

An already valid continuous pair can have independent REAL32 round-to-nearest
values outside its pair interval. The explicit constrained-storage candidate
may then move Q by **one adjacent REAL32 value**, with N unchanged, and only
accept it if the existing stored predicate passes. The constrained candidate can also select joint absence when
`0<Q64<min_positive_REAL32` and both ordinary storage and the directed Q
neighbor fail. V4 exposed ten such ice pairs: Q rounded to one quantum and
made the stored mean mass too large; the adjacent Q=0 left N alone. V5's
explicit quantum-absence flag permits storing `(0,0)` in that bounded-Q
case. Its Q removal is below one Q quantum; its N removal is the **complete
valid number moment**, not one N quantum. Both signed changes are ledgered.
The legacy strict and subnormal-only policies retain their prior behavior.
A truly invalid continuous pair is never repaired. No bound tolerance changes.

Signed storage deltas and counts are required outputs. These are numerical
representation changes, not physical phase transfers or demonstrated water /
energy conservation. The native aggregate uses pressure-coordinate carrier
units and must not be labelled kilograms without the remaining geometry.

## Validation and acceptance

The two-cell case and constrained-store boundaries are covered in the pinned
Intel O0/O2 transport test. An additional [exact native-fragment test](../tools/pr87_source_first_fallback_regression.py)
extracts the exact composed V9 procedure and invokes its explicit source payload
interface: `pr87_raw_qsrc`, `pr87_raw_nsrc`, `pr87_coupled_qsrc`,
`pr87_coupled_nsrc`, `pr87_source_carrier`, and `pr87_source_step`. The four
REAL32 source arrays carry raw intensive Q/N rates and the captured coupled
Q/N tendencies; the REAL32 carrier array and integer step tag bind them to the
old state and current call. At both pinned Intel O0/O2 levels,
nine modes cover the unchanged baseline, ordinary source-first retry, safe
virtual donor, no-air rounding case, negative donor, invalid final endpoint,
and stale step/carrier/coupled-source rejection. Rejections preserve Q2/N2
before commit. The [V9 receipt](evidence/pr87_state_cycle_20261016/source_intensive_stage_ifx_o0_o2.json)
binds the proposal, extracted procedure, kernel, compiler, flags, and per-mode
logs. The earlier [V8 guarded fixture receipt](evidence/pr87_state_cycle_20261016/source_first_virtual_donor_guarded_ifx_o0_o2.json)
and its compressed runner remain historical and unchanged.

The manufactured no-air fixture uses `W=REAL32(92363.85)`,
`Q=REAL32(3.7537916e-8)`, `N=8961516`, and `dt=20`, with raw rates formed
from the recorded weighted tendencies divided by `W` in REAL32. Its initial
weighted REAL64 endpoint lands 8.1604 REAL32 ULP below the minimum bound, so
the existing 8-ULP store tolerance rejects it. Forward REAL32 intensive
staging lands 7.2634 ULP below that bound and is accepted by the same unchanged
tolerance; with no air transport, the committed Q/N pair is bit-equal to that
staged endpoint. This is a manufactured numerical regression, not a native
cell replay or a proposal to widen the tolerance.

The paired source representation row is in pressure-carrier units. It compares
the original `dt * coupled source` against `W * (staged state - old state)`;
these signed deltas are numerical representation changes and carry no kg or
energy interpretation.

| Moment | Original proposal | Represented stage | Signed delta | L1 delta | Maximum cell delta |
|---|---:|---:|---:|---:|---:|
| Q | -1.223607455358433e-5 | -1.223577078612870e-5 | 3.037674556338743e-10 | 3.037674556338743e-10 | 1.518837278169372e-10 |
| N | -2,919,544,000 | -2,919,621,347.89062 | -77,347.890625 | 77,347.890625 | 38,673.9453125 |

## V10 later-source payload and cadence fixture

V10 appends two REAL64 arrays, `pr87_later_qsrc` and `pr87_later_nsrc`, to the
six V9 capture arguments. They carry the weighted RK1 non-air source rates
after physics coupling. The source-first virtual donor and complete endpoint
use the same REAL64 order as the transport kernel; the REAL32 physics stage
remains unchanged. The source ledger represents the stage plus later source
as `W*(stage-old) + dt*D` and writes an optional `SOURCE_LATER_TOTAL` row with
the summed `dt*D` amounts and maximum REAL64 identity residuals. This separate
row does not make an aggregation claim across the Q/N source ledger and does
not imply kg or energy units.

The exact-fragment regression now extracts proposal SHA256
`b0a467b8f96728cb0b98cae014edb78df68edc995d5bab40138e8ef405651bf4` and runs
12 modes at pinned Intel O0/O2: baseline, ordinary source-first, virtual donor,
V9 no-air stage, V10 no-air later source, RK cadence, negative donor, invalid
endpoint, stale step, stale carrier, stale coupled-source reference, and
nonfinite later source. The stale and invalid cases reject before commit. The
nonzero later-source fixture verifies its REAL64 Q/N increments enter once
after the REAL32 stage and that its `SOURCE_LATER_TOTAL` amounts match the
captured input.

The cadence fixture calls RK1/RK2/RK3 with `dt=20/3, 10, 20`, reuses the same
captured later-source arrays, verifies the active `q1/n1` state remains bitwise
equal to its initial state after each call, and verifies the final state is
bitwise equal to one full 20-second source application. This is an isolated
native-procedure fixture; it does not establish completion of the actual
40-second model window. The [V10 receipt](evidence/pr87_state_cycle_20261016/source_later_stage_ifx_o0_o2_v10.json)
binds the exact proposal, extracted procedure, kernel, pinned profile, and
per-mode outputs. The [V9 runner snapshot](evidence/pr87_state_cycle_20261016/v9_fixture_runner.py.gz)
is preserved separately with its original V9 receipt.

Reproduce against a newly composed proposal and use a fresh receipt path:

```bash
python3 tools/pr87_source_first_fallback_regression.py \
  --proposal /var/tmp/pr87_sources_new/native_update.f90 \
  --receipt /var/tmp/pr87_source_intensive_stage_ifx_o0_o2_new.json
```

Actual two-step acceptance is recorded separately
in the integration receipt. A changed first-call state under source-first
ordering must be reported as a new model identity, rather than byte identity
with v17. Structural evidence does not establish time-response, observation
retention, or scientific approval.
