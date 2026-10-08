# PR71 independent source and evidence review (2026-10-08)

## Scope and navigation

This review uses the maintained Cloud-BAL graph as a navigation aid; the
isolated inherited graph has 1,499 nodes and predates PR71, so it is stale for
this patch. Source code, source transforms, and bound execution receipts are
authoritative. No graph freshness or graph delta is used as runtime or
scientific evidence.

## Conservative fraction reproduction

The frozen PR70 process patch (`5f1b75925ec803838f5b3cfa81012336f4d21727073c5d8c0703fb70ddc37670`)
was applied at fuzz zero to the captured source
(`97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa`). The
extracted helper matched the already recorded PR70 helper SHA
`47e969dde50410e3c708c1a49e49e76bc2592d6c2fcfae31b0164c51dddf1683`.
The test uses the exact reported rain mass and process increment and evaluates
both the helper return and its immediate next float32 value with
`kdm6_rain_process_state_valid`.

Pinned Intel ifx 2026.0.0 O0 and O2 both returned `0.98616278171539307`; the
next float32 value is `0.98616284132003784`. Both candidates pass the direct
predicate and both store `QR=1.000000082740371e-9`, above `qcrmin=1e-9`. This
is a local counterexample to a largest-rounded-valid-fraction guarantee. It
does not search all float32 fractions or establish a global maximum. PR71's
appropriate description is a conservative valid fraction within computed
continuous admissible intervals. No PR70 receipt was rewritten; the new
source, test, compiler, flags, executable, and log hashes are in
[`pr71_conservative_fraction_validation_20261008.json`](evidence/pr71_conservative_fraction_validation_20261008.json).

## Freezing domain source audit

I reviewed the source and evidence in
[`PR71_FREEZING_DOMAIN_AUDIT_20261008.md`](PR71_FREEZING_DOMAIN_AUDIT_20261008.md)
and its JSON receipt. The selected generated source and matched observer
support the freezing-created tiny QG/BG pair, the 1000 kg m-3 source ratio,
the inactive property gate, the subsequent `pgdep` call, and the controlled
fatal. The report correctly distinguishes that observed value from a
supported PSD state and does not claim an accepted native result, closure, or
a rule for positive deposition.

The maintained research-host source was compared directly at the property
gate, freezing assignments, and terminal cutoff. It shares the relevant
undefined output/gate mismatch; its legacy extinction zeros QG only, while
the selected generated candidate additionally clears BG. The observer receipt
belongs to the selected generated source only. This supports a bounded source
comparison, not native acceptance. No false scientific or runtime PASS was
found in the freezing-domain audit.

## Particle output contract

The first output-contract patch/source (`72a429…` / `af26db0…`) are retained
as historical evidence. After review found that a PR67 stage-0 observer
record serialized unassigned `work1(:,:,4)`, the generator now emits a
replacement with the assigned `mass_velocity_rate(:,:,4)` trace. The revised
patch (`94ea6189c85cd0856a28aac2663ad70091c3259fc448d48bd021adf42ff9ae45`)
and transformed source (`5de1884ab59e3de30a3e4ef1d8317405f1ba0591cf7ed9aa6fbca574d5233f41`)
preserve the particle-output logic and change only that observer field.
Its regenerated source test passed under the pinned Intel profile. The revised
receipt is `pr71_particle_output_contract_20261008_observer_fix.json`.

I reviewed the revised transformed source
against the seven `ProgB_param` / `slope_kdm6` pairs and the output-use
inventory. The original risk was real: `ProgB_param` has 18 `INTENT(OUT)`
arrays, so values from an inactive call cannot be read by the immediately
following slope call. The patch now initializes every output on every call,
passes status along all seven paired paths, rejects transient or unsupported
status at slope entry, and gates direct rate and density consumers. I found
no remaining unguarded graupel property consumer in the transformed source.

ABSENT requires exactly `qg == 0` and `bg == 0`; it clears graupel slopes and
status-derived `n0go`. The extracted test executes the exact absent slope
assignments and the status-gated `n0go` branch with `rslopemu=0` under
`-fpe0`, confirming zero outputs without division. This exercises those
branches, not the full slope routine or whole-module path. Terminal extinction
also sets ABSENT, zeros `n0go`, and clears all 18 properties. Other status
classes are explicit, including paired-positive TRANSIENT below both setup
thresholds and PSD_ACTIVE only when either threshold is exceeded, the raw
ratio is admitted, and derived values are finite.

The strict raw `QG/BG` admission interval [100,900] rejects states that legacy
code clamped and rewrote. The output-contract report accurately identifies
this as a deliberate research property-domain restriction and a model-behavior
change, not a semantics-preserving initialization fix. I found no code or
test assertion that treats the restriction as a universal physical law.

The extracted `ProgB_param` harness passed under pinned Intel ifx 2026.0.0.
It covers exact absence, transient, orphan, negative, NaN, out-of-range, and
exact endpoint cases; output and status assertions pass. Its local `rgmma`
stub calls the intrinsic gamma function, so this is routine-level contract
evidence rather than full-module scientific validation. The frozen receipt
binds source, patch, generator, tests, executable, compiler profile, and logs.

## Checked integer substep counts

The v2 count patch (`7bc37047bf616b50ebb506f130a2f1f0535e0a5afc26bb26183a27ee188ebb24`)
applies to the output-contract source above and produces checked source
`6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716`. I
reviewed both guarded count sites and the extracted helper. Its signed NINT
bounds account for the `+0.5` input and tie rounding: scaled input must be
strictly below `INTMAX+0.5` and strictly above `INTMIN-0.5`. Binary64
rate-times-timestep overflow is checked before multiplication when timestep
exceeds one; non-finite rates or timestep and non-positive timestep reject
before NINT. Finite negative rates within the representable range keep the
original minimum-one result. No rate cap, floor, or physical velocity policy
was added.

The pinned Intel O0/O2 harness passes both signed-boundary tests and first
asserts that default integer is 32-bit. Guarded-composer tests also pass (2/2),
binding the source, PR70 process patch, PR71 output patch, and count patch to
the checked source hash. These checks validate integer safety and source
composition only; they do not explain the large observed ice rates or show a
complete native step.

## Same-source integration and native execution

The final whole-module integration receipt
[`pr71_unit_process_guarded_integration_20261008.json`](evidence/pr71_unit_process_guarded_integration_20261008.json)
binds checked source
`6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716` and
process, output-contract, and count patches. Its bounded unit and EOS
candidate/direct-volume comparisons pass at O0/O2. The narrowed EOS
graupel-absent fixture has positive cloud and ice, with rain, graupel, and
background graupel absent; it is blocked by the inherited `n0i` divide before
fixture outputs. An earlier all-hydrometeor-absent attempt is historical and
also does not pass. Neither establishes full-module absent-graupel behavior;
the branch-level absence test remains narrower and is explicitly scoped above.

Native v1 is recorded as `INCOMPLETE_TIMEOUT`: the fresh partial-host run
received controlled SIGTERM at the 15-minute limit, with 100 inputs unchanged,
15 expected outputs present and `pr69_water.raw` missing. It emitted no PR71
status or fatal contract diagnostic. Only first-call observer stages 0 and 1
were written; the original stage-0 `work1(:,:,4)` value was unassigned and is
not interpretable. The corrected v2 observer replaces that field with
`mass_velocity_rate(:,:,4)` and adds substep diagnostics. Its full execution
receipt is [`pr71_native_v2_incomplete_observation_20261008.json`](evidence/pr71_native_v2_incomplete_observation_20261008.json).
V2 also ended by controlled SIGTERM (`INCOMPLETE_OBSERVATION`) with unchanged
inputs and no property-gate acceptance or rejection. It reports an ice
number-velocity rate of `7.736184251e9 s^-1` at `(i=78,k=2)` with
`dtcld=20 s`; the source's `NINT(max(rate)*dtcld + .5)` input is at least
`1.54723685021e11`, outside default int32 range. This establishes an unsafe
NINT input at that cell, but the separately observed maximum `mstep_i` at
`i=149` has no captured pre-NINT driver, so no causal relation between the two
values is claimed. Both observations predate the checked-count patch, so they
do not validate guarded native rejection. The later guarded run is recorded
in [`pr71_guarded_native_integration_20261008.json`](evidence/pr71_guarded_native_integration_20261008.json).
I independently applied its observer patch at fuzz zero to the exact checked
source and reproduced the compiled source byte-for-byte (`e6f9dbf8…`); the
fresh KDM6 object (`26f6af0c…`) and partial-host executable (`6d2bbd1d…`)
hashes match that build receipt. The receipt also binds the pinned ifx and
`mpiifx` path, hash, and version output. All 100 staged inputs still match
their before/after hashes. The run reported
an ICE step-count rejection at `(i=107,k=5)`, rate `829940373.290303 s^-1`,
and `dt=20 s`; the helper rejects its scaled value before `NINT`, then the
caller stops before the ice substep loop. The two later diagnostics
`pr67_kdm6_process.raw` and `pr69_water.raw` are absent because the run stopped
at the guard. This is `EXPECTED_STEP_COUNT_CONTRACT_REJECT`, not a property
rejection, accepted model, or rollback guarantee. The output-isolation receipt
therefore reports missing expected outputs; input integrity remains PASS.
The large ice velocity/rate cause, physical policy, full step completion, and
water/energy closure remain open.
