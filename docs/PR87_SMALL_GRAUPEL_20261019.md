# PR87 follow-up: small graupel and repeated native consumption

## Latest validated window

**V50 OFF and COUPLED complete 60 seconds and three KDM6 calls.** The
[independent closed-run review](evidence/pr87_followup_20261019/review/v50_runtime_review.json)
checks all completed states, all nine accepted RK calls at air fraction one,
unchanged input hashes, and 17 bit-identical records through the preserved
40-second prefix. Ice retains its separately declared 8-ULP policy;
cloud/rain and graupel keep their strict bounds. The selected-object Intel
build is a research partial host, not a clean whole-model build.

The [manifest](evidence/pr87_followup_20261019/manifest.json) is the entry point
for source/build identity, the 28 focused tests, matched closed receipts and
scientific gates. The same binary is now attempting OFF600; COUPLED600 waits
for its disk allocation. Neither window has a longer-duration PASS yet.

## Preserved baseline and actual failure

PR87 review base is `d22a3887b168f3ba7c3f4f538b28dd27b583f6f5`.
PR87 subsequently merged at `45c8800fcac1f8ea2a8964519550accaba01f20a`
on 2026-10-19 01:47:58 UTC. This follow-up starts from that unchanged source
tree; the review base and historical receipts remain pinned separately.
V42 OFF and COUPLED40 remain the preserved two-step `PASS_SCOPED` baseline.
Their 60-second attempts stop at the third KDM6; no historical receipt is rewritten.

The source-pinned audit of the saved T3 PRE_KDM6 finds 18 low/low positive
QG/BG pairs in each arm. All 18 are finite, paired, and within the existing
100–900 kg/m3 density support. In the read-only V43 OFF diagnostic, the actual
failure is model timestep 3, first ProgB call, call latitude index 32, i117,k17:
QG bits `2B638C2A`, BG bits `268376D7`. Those bits match the saved input.
The first 17 records through 40 seconds match V42 OFF40 byte-for-byte.
The call latitude index is not a geographic latitude declaration.

## Common small-positive state contract

The candidate admits finite positive QG/BG in the existing density support at
all representable magnitudes, and exact 0/0 remains absence. ProgB, process
endpoint admission, and the paired graupel sedimentation helper share this
contract. Negative, orphan, nonfinite, and unsupported-density states remain
rejected. Existing small-Q slope and interaction-rate branches, process rates,
and the separately recorded terminal joint cutoff remain in force.

This changes the accepted intermediate physical domain. It neither introduces
a new N/B prior nor claims that tiny states have magnitude-independent kinetics.
The [source-domain review](PR87_SMALL_GRAUPEL_DOMAIN_REVIEW_20261019.md) describes
the formula and storage limits. Pinned Intel O0/O2 extracted-routine tests cover
actual failure bits, active/absent transitions, properties, process admission,
and paired sedimentation. Their Gamma/constant fixture adapter is not full host
initialization.

A separate full-KDM6 replay uses the saved actual T3 input row at call latitude
index32 and the recorded host constants. The original diagnostic source fails
at the same ProgB call and bits; V44 completes this row. This is a component
replay of model timestep3, not a complete native60 run. A subsequent replay
of the complete saved T3 OFF input also returns zero: all 2,533,440 active cells
pass strict cloud/rain/G and unchanged ice 8-ULP post-state checks. Its
[component receipt](evidence/pr87_followup_20261019/component/v44_full_t3/receipt.json)
is separate from native execution.

## Rain flux ownership correction

The first-call V42 water audit found a distinct caller defect: each rain column
was updated by the paired helper, but a later loop reused the last column’s
1D helper flux for every column’s precipitation output. The candidate caches
each helper result immediately into the existing per-column falk/falkn arrays.
Packet proposals, state mutation, substep gates and sweep order are unchanged.
The Intel O0/O2 regression compiles the actual caller blocks and distinguishes
the old and corrected behavior, including an inactive last column.

The [separate V42 and V44 budgets](PR87_V42_BUDGET_20261019.md) keep original
public precipitation distinct from helper ground export. V44’s helper/public
rain gap is 0.179kg OFF and 0.386kg COUPLED; this is not complete water closure.
After the currently included cleanup terms, signed first-call residuals remain
about −39,666kg and −39,490kg. Full energy, same-call host hybrid carrier and
post-step observations remain unavailable/open.

## V44 native result and next boundary

Both V44 arms complete 20 seconds with strict completed-state audits, then stop
at timestep2, RK2, graupel at i146,j216,k21. The source failure ledger has one
FULL failure; its 625 SOURCE rows are separate source-only diagnostics.
Both runtime receipts remain `INCOMPLETE`, not 60-second passes.

The saved T2 PRE_RK receiver is absent. Its only nonzero face donor is the
k−1 neighbor, whose stored QG/BG ratio is exactly900. The common-air operator
with zero local source therefore has a valid exact-real boundary mixture.
Printed REAL64 candidate values lie near that boundary, but the list-directed
record does not retain enough digits to establish the actual continuous-gate
versus storage split. The strict gate is retained. Source-certified arithmetic
and joint storage must be resolved before another longer forecast is useful.

## Selective common-air storage retry

V45 was an unsuccessful prototype: both arms still stopped at the same T2 RK2
boundary. Its relaxed-kernel retry also treated BG as a number moment. An
independent tiny-BG fixture demonstrates why that role is wrong: a valid
specific bulk volume need not survive multiplication by dry density as a
stored number concentration. The archived V45 source and receipts remain
unchanged. V46 was built but not run; final review split a finite-value check
from its subsequent comparison before freezing V47.

V47 keeps the strict primary joint update. On failure, a local transaction calls
the existing storage function directly for every pair, with the original
cloud/rain volume-number bounds, ice contract, and graupel mass/volume role.
Only a failed graupel store can use the seven-donor mixture fallback. It requires
zero local graupel source, original receiver bits, and a bit-identical replay of
the existing air-tendency calculation. It therefore cannot replace an arbitrary
inconsistent proposal. Finite nonnegative weights include the retained donor;
every contributing original QG/BG pair must lie in the unchanged density cone.

The weights use the same old-time donor map and host geometry as the existing
shared-face stencil. A selective REAL128 positive-mixture calculation and
directed REAL32 storage choose an endpoint within the strict cone. Face flux
proposals remain unchanged; numerical differences are recorded against the
canonical REAL64 update. The weights themselves are REAL64 values, not a claim
of exact real-arithmetic products or full carrier continuity. Ordinary nearest
storage keeps the old ledger convention; certified retries additionally record
their stored-minus-canonical change and one compact first-witness bit record.

All trial arrays and ledgers commit together after every check passes, with
the common air fraction fixed at one. Invalid
donors, nonzero incompatible sources, negative weights, and partial air fractions
remain rejected. Intel O0/O2 tests compile the archived common kernel and actual
transaction routines; they verify successful certified mixtures, the BG role,
ledger deltas, rollback after a later invalid pair, inconsistent proposal
rejection, and quiet-NaN rejection under `-fpe0`. This is a conservative
retry for its declared source domain, not a proof that every feasible coupled
source/transport problem will be found.

Both V47 arms complete two KDM6 calls and 40 seconds. The closed independent
audits bind the unchanged inputs, executed binary, all six accepted RK rows at
air fraction one, and strict completed endpoint states. The T2 RK2 repair has
an actual bit witness: its canonical Q/B exceeds 900 by
`140/2321676760735037`; the stored pair has ratio
`973003456/1081115`, below 900. These are V47 operands, not a retrospective
claim about V44's unavailable candidate bits.

V47 then rejects T3 RK1, graupel i160,j235,k20. Its source is nonzero, so the
air-only certificate correctly refuses reconstruction. This is before the
third KDM6, not a reproduced ProgB failure. Both 60-second windows remain
`INCOMPLETE`; the unchanged historical V42 40-second evidence is preserved.

The next extension admits a nonzero represented total source only when both
REAL64 rates are bit-identical to an independent replay of the existing
horizontal diffusion stencil on the same immutable donor pair. Four
nonnegative diffusion coefficients join the air weights; the combined retained
weight must remain nonnegative. This establishes an identity of the consumed
rate values, not a claim that physical source components came only from
diffusion. Zero total source retains the separate air-only certificate.
The original full diffusion helper and all proposed source/air rates remain
unchanged. Reassociating the certified map can change stored rounding, which
continues to enter the numerical ledger. Geometry mismatches, additional
unmatched source terms and invalid mixtures remain rejected.

V48 implements that source-value identity. Both arms complete 40 seconds and
the first two RK stages of timestep3. They then stop at RK3: cloud source-first
recovery is blocked because the baseline scan also marks a graupel pair that
the independent mixture certificate can already store. Neither V48 arm reaches
the third KDM6 call. The [closed V48 review](evidence/pr87_followup_20261019/review/v48_runtime_review.json)
keeps that failure separate from the original V42 ProgB failure.

V49 probes the failed graupel pair on local arrays and a local ledger before
the existing rain/graupel gate. It clears only the graupel failure flag when
that entire pair is certified. This permits the existing cloud/ice recovery
to run; the final all-pair transaction must still pass before anything is
committed. The probe changes neither shared fields nor feasibility, theta,
rejection totals or the committed numerical ledger. Invalid source identity,
rain failure and unsupported graupel still block recovery. The
[orchestration review](evidence/pr87_followup_20261019/review/orchestration/review.md)
and Intel O0/O2 tests cover simultaneous cloud failure and certifiable graupel,
both probe rollback outcomes, and rejection by the final all-pair check.

Both V49 arms still stop before the third KDM6, at T3 RK3. Their 17 complete
trace records through 40 seconds are byte-identical to V48. The new probe
rejects before cloud/ice source-first recovery: the consumed source was frozen
at RK1, while the diffusion replay received the live RK3 `muts`. Acoustic
mass updates change that field between stages. The
[source-stage review](evidence/pr87_followup_20261019/review/diffusion_certificate/source_stage_geometry.md)
identifies the producer and consumer epochs; it does not attribute the mismatch
to cloud/ice recovery. Preserving RK1's two-dimensional carrier geometry for
the later replay is separate from changing any proposed physical source.

V50 captures that full two-dimensional `muts` field immediately before RK1's
moist/scalar advance, after acoustic mass and boundary updates. The local
snapshot lasts for one `solve_em` invocation; its timestep and producer RK=1
identity must match before every joint consumer. The existing MP37 guard owns
the one consumer call. No new three-dimensional field, diffusion rate or
precision change is introduced. Other geometry references remain unchanged,
and the exact donor/source identity check still rejects mismatches. Intel
O0/O2 tests execute the inserted capture/guard, change live `muts`, and verify
both snapshot preservation and rejection of stale timestep/wrong producer RK.
The [V50 review](evidence/pr87_followup_20261019/review/diffusion_certificate/v50_geometry_snapshot_review.md)
is separate from the completed native60 audit linked above.

## Available 60-second state diagnostics

The [native-history result](evidence/pr87_followup_20261019/history/v50/native_history_summary.json)
binds actual T0/T60 files and recomputes hybrid dry mass at each endpoint.
For the interior excluding the boundary ring:

| Water endpoint change | OFF | COUPLED |
|---|---:|---:|
| Signed inventory change (kg) | +12,499,728,837.609 | +12,502,204,791.953 |
| Cellwise L1 change (kg) | 305,429,549,097.944 | 305,545,593,361.850 |

These are state changes, **not water-closure residuals**. Boundary fluxes,
process terms and numerical changes have not been combined on this host
measure. The preserved first-call KDM6 budget uses a different declared local
measure and is not copied into a 60-second closure claim. The history result
also exposes pressure, Phi, potential-temperature and wind descriptors;
force/continuity balance and independent observation agreement are not
evaluated. First-call rain/cutoff/ice subsets remain byte-identical to V44,
as bound by the V50 scoped comparison in the manifest.

## Scientific limits

One domain, rank, thread and tile; selected-object pinned Intel partial-host
build, not a clean rebuild of WRF and every dependency. Initial operating inputs
and original source remain unchanged. The successful T3 component replay and
V50 native60 window remain separate from preserved V42 native40 evidence. Model
changes, analysis-increment effects and numerical storage accounting remain
separate. Water/energy closure, observed signal retention, native mass–wind
balance and initial-shock reduction remain `OPEN`.
