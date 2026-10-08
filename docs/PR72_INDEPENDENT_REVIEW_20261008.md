# PR72 independent review (2026-10-08)

## Scope and evidence boundary

This review independently inspected the PR71 guarded source and receipts, the
frozen PR72 source and focused evidence, with Graphify used only to navigate
the maintained Cloud-BAL relationships. The isolated Graphify snapshot
predates PR71 and contains no KDM6-specific source relationship; it is not
evidence for runtime behavior. Source and Intel build artifacts remain
authoritative. This review does not sign off a successful native time response
or scientific closure.

## Initialization and active ice coefficient invariants

In the PR71 selected source, `kdm6init` assigns the ice coefficients from
source constants on each initialization call:

- `avti = 2710`, `bvti = 1`, `dmi = 3`, and `mui = 0`;
- `pvti = avti*Gamma(1+dmi+bvti+mui)/Gamma(1+dmi+mui)`;
- `pvtin = avti*Gamma(1+bvti+mui)/Gamma(1+mui)`;
- `pidni = cmi*Gamma(1+dmi+mui)/Gamma(1+mui)`.

The Gamma recurrence gives `pvti = 4*avti`, `pvtin = avti`, and therefore
`pvti = 4*pvtin`. `pvti` feeds ice mass velocity while `pvtin` feeds ice
number velocity. An inactive-state guard should preserve these active
definitions and gate the resulting properties at their use sites.

## PR71 zero-number forward-property defect

In `slope_kdm6`, the PR71 source assigns zero to `vtn(i,k,2)` when
`nci(i,k) <= 0` at lines 4510-4511, then unconditionally assigns
`pvtin*rslopeb(i,k,4)*denfac(i,k)` at line 4513. The zero sentinel is therefore
overwritten. For positive ice mass with zero number, the same routine also
evaluates `lamdai(qci,den,nci)` whenever `qci > qmin`, although its expression
uses `log(pidni*nci/(den*qci))`. The tiny positive QI values observed in the
retained native trace (about `1.95e-34` and `1.87e-36`, with zero number) are
below the PR61 initializer activation threshold; depending on `qmin`, they can
still reach this branch. These values alone do not identify the velocity
cause.

The PR71 full-module EOS graupel-absent fixture was recorded as blocked at an
`n0i` division in `kdm62d` near line 2106, before its output assertions. The
PR71 report called this inherited; exact source comparison shows the likely
cause was introduced by the PR71 output-contract patch. PR70's composed source
(`487afbf064b6a3598ecb12248224fc3b91c77e1b0ed921d0e0e8130cacb9b583`) closes
the graupel slope branch before entering the ice slope block. PR71's guarded
source (`6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716`)
adds an outer `PROGB_ABSENT`/`else` around graupel slopes but leaves the ice
slope block inside the `else`. When graupel is absent, ice slopes are skipped
and later `n0i` can divide by an unset/zero slope value. The PR72 ice-slope
transform adds the missing branch close before the ice block, restoring its
unconditional per-cell initialization. It also computes number velocity
before applying the zero-number gate, fixing the PR71 overwrite. The same EOS
graupel-absent fixture was replayed with exact PR70, PR71, and PR72 sources
under pinned Intel ifx O0. PR70 stopped earlier with
`INFEASIBLE_MOMENT_STATE`; PR71 stopped with FPE73 at the `n0i` divide on line
2106; PR72 no longer hit that divide but stopped earlier at the same guarded
process admissibility failure as PR70. The divide is a PR71-specific
regression, and PR72 removes it, while this fixture remains blocked and is not
a passing full absence test. The [causal replay receipt](evidence/pr72_causal_eos_graupel_absence_20261008.json)
binds source, object, executable, and log hashes; the historical PR71 receipt
is unchanged.

The frozen species-state transform guards the `n0i` rebuild, all three
`lamdi_tmp` consumers, and each of the seven slope call sites. Its source-bound
O0/O2 matrix verifies supported active output preservation and rejects
unsupported positive-mass/zero-number and number-only pairs before PSD work.
The transform applies an explicit paired-moment policy; it is not a general
PSD or scientific acceptance test.

## PR71 count-guard lineage

The PR71 integrated report records composed source SHA-256
`6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716`, particle
contract patch SHA-256
`94ea6189c85cd0856a28aac2663ad70091c3259fc448d48bd021adf42ff9ae45`, and
step-count patch SHA-256
`7bc37047bf616b50ebb506f130a2f1f0535e0a5afc26bb26183a27ee188ebb24`. The
guarded partialhost execution stopped at the checked ice count with
`EXPECTED_STEP_COUNT_CONTRACT_REJECT` at `i=107,k=5`; all 100 staged inputs
retained their hashes. This is a controlled numeric-domain rejection, not an
accepted model run. The later one-point diagnostic probe was generated
byte-for-byte from the retained PR71 observer source, and its partial-host
build receipt binds source, object, and executable. The probe added
conditional writes at the existing rejection point without changing numerical
assignments. This is not an exact replay of the historical count failure at
`(i=107,k=5)`; it observed a different first rejection, `(lat=2,i=83,k=7)`.
The separate EOS fixture comparison remains as described above.

I independently reproduced the observed point's number-velocity expression
from its captured binary32 operands: `DBLE(pvtin)` (2710) multiplied by ice
`rslopeb` (9659124) and `denfac` (1.1013844013214111) yields the exact
binary64 velocity `28830087045.919334` (`0x1.ad9a0de17ad66p+34`). Dividing by
binary32 `delz=209.64324951171875` yields exact binary64 rate
`137519748.96910655` (`0x1.064c509f02ebcp+27`). The source declares `vt` and
`vtn` as double precision, assigns `DBLE(pvtin)*rslopeb*denfac`, stores
`number_rate` as double precision from `vtn/delz`, and keeps `step_rate` as
double precision; the checked helper accepts a double rate and real timestep.
Both calculated values exactly match the logged fields at `(lat=2,i=83,k=7)`.
This confirms the expression at that new diagnostic point only; it does not
attribute the old `(107,5)` rejection. The durable
[expression replay receipt](evidence/pr72_live_ice_expression_replay_20261008.json)
binds the calculation to the pre-fix diagnostic receipt.

The source-bound `checked_substep_count` helper rejects nonfinite rates or
timesteps, nonpositive timesteps, binary64 multiplication overflow, and a
rounded argument outside the default-integer range before `NINT`. It does not
reject a finite negative rate as a physical-sign check; valid inputs retain
the PR71 expression and minimum-one rule. I independently extracted and
compared the delimited helper from the PR71 composed source and the PR72 ice
transform output: both are byte-identical (block SHA-256
`fc63f48f8e8d8f93b9ba12911400242ba9e223cbb2432fb61b0918ed4339392d`). The
final combined source retains the same helper byte block; both guarded call
sites are present in the frozen combined source.

## Candidate review and independent replay

The native owner's direct-call slope test runs with pinned Intel O0 and O2 and
covers active ice under absent graupel, the `vm=4*vn` output relation, lambda
clamping below/inside/above the supported interval, and poisoned
active-to-absent slope outputs. I independently inspected the updated bounds:
the full `(1:3,1:3)` actual section maps to dummy bounds `12:14,7:9`, with the
active actual center `(2,2)` mapped to dummy `(13,8)`. It checks all eight
inactive interior neighbors plus the external halo sentinels. Both observed
builds pass. The review replay used scratch
`/var/tmp/pr72_ice_velocity_invariants.I03Hbr`; transformed source SHA-256 is
`f396c9270791addcd4aed9fdc59f5a6d3f9287f1af8f759d3a0cbc36b1e78f85`, O0
module object/executable are `aca8548887e45511a78e03218f152675dbf1b85670ed0e29b2c3b6eb56a9b18d`
and `4bb5c8a2c28e6bd92c0ea95336540ad6eaca840c529a3b4f92c0c22ef3a92d4f`, and
O2 module object/executable are
`68ab4aa8924d9ef2a5a4e4e2b75fee1d070e8facdbd64f553fe58e43bc37a172` and
`0905c1671f1bf36da435d502cc43ba855e8418bac44b81055a1805c043308034`. The
test source hash at replay was
`c827756825259db73b1524953ef795520efbdb67b31100c95d4dc38f4b68755b` and the
runner hash was
`327708a72d4e5e75df8c293d2eb27e6d1dc5b241b9b6e675e784a49686a0b446`.
The active case checks the output ratio, but does not independently assert the
absolute initialized `pvti`/`pvtin` factors or nonunit `denfac`; this test
preserves the relation rather than independently validating those values.
The durable [direct-call test receipt](evidence/pr72_ice_velocity_invariants_20261008.json)
(SHA-256 `00104a45edea7fa3b9f02a0136bd330e569140b704aeb82368b08a365454be2f`)
binds its O0/O2 runs and source hashes.

The final species/property source is hash-bound to native-fixed input
`f396c9270791addcd4aed9fdc59f5a6d3f9287f1af8f759d3a0cbc36b1e78f85` and has
SHA-256 `1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819`.
The refreshed [species matrix receipt](evidence/pr72_species_property_state_20261008.json)
(SHA-256 `8610eb1f298698d46a1e01c58b606fb1c8f483e0ceaea572bef0c7d7efca1521`)
records 20 pinned-Intel O0/O2 executions under compiler profile SHA-256
`5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`: active outputs match baseline,
exact-zero whole-module and individual cloud/ice/rain states pass, and
mass-only, number-only, negative, and nonfinite ice mass are rejected before
PSD work. Its transform, driver, and runner hashes match the current files.
The local validator now takes current-cell scalar moments, avoiding both
per-cell full-grid rescans and assumed-shape lower-bound remapping. The three
ice-lambda consumers now have preflight coverage: two local checks before the
intercept rebuild blocks and one before the late lambda reconstruction. In the
final combined source, the checked substep helper block remains byte-identical
to PR71 (SHA-256 `fc63f48f8e8d8f93b9ba12911400242ba9e223cbb2432fb61b0918ed4339392d`)
and both guarded call sites are present.

The final combined native receipt binds source
`1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819`, pinned
partialhost object
`b02ec1c57377d26346fc401e5bf27ff5e61c7e9173a54d028a881116ef99f502`, and
executable
`d4820b855109c74260bdf70b2c647af712322a09518f71531c6dfc22294c24b6`. Its
[receipt](evidence/pr72_combined_native_first_reject_20261008/receipt.json)
records all 100 input hashes passing and a first-call pretrace matching the
PR71 baseline. The run is **REJECTED** at generic KDM6 error line 1360,
“unsupported positive mass without number/volume state.” The captured fatal
does not name a species or coordinate. Independent input-order analysis of
the preserved trace and frozen validator source identifies the first
unsupported pair as ice at actual `(i=133,k=1,j=2)`, with
`QI=3.5308575789291633e-35` and `NI=0`. This is an inference, not text emitted
by the fatal. The paired-state policy rejects any exact positive-mass/zero-
number pair, including this tiny value; this does not establish its physical
importance or certified PSD validity. The [derivation receipt](evidence/pr72_independent_input_order_20261008.json)
binds the raw trace hash, parser hash, coordinate mapping, and source order.
The public NI input remains zero after conversion to volume number under
positive density. Process and water raw outputs are absent, so output
integrity is FAIL and the native result is not a successful substep or
scientific pass. The direct-call and species-matrix results establish focused
source behavior only; native time-response and scientific closure remain
OPEN.

The earlier PR71 guarded native receipt at
`evidence/pr71_guarded_native_integration_20261008.json` (SHA-256
`2644c12fd8e56fd204caa2ca2ab530f80b22d39af2f669c8ebc900fe7af497af`, build
receipt SHA-256 `12cbcb3ef45a815806415b45c781f3389e0a46776c88938c671be83c011b3331`,
retained input-profile receipt SHA-256
`bf747509ee3eed5d4763315d701ebaff8f82c3ec8c2d825ad5703cf53e065cbb`) and its
historical first rejection `(i=107,k=5)` remain preserved and unchanged. The new pre-fix probe's
`(lat=2,i=83,k=7)` diagnostic is a separate observation, not an exact replay
of that historical point. See the [pre-fix diagnostic receipt](evidence/pr72_pre_fix_ice_rejection_20261008/receipt.json)
and the exact [expression replay](evidence/pr72_live_ice_expression_replay_20261008.json).
The expression replay verifies the number-velocity arithmetic only at the
new 83 point; no historical operand equality or causal attribution is
claimed. No implementation blocker was found in the frozen source, focused
tests, or reviewed receipts; the native rejection and remaining scientific
gates are unresolved outcomes, not implementation signoff.

## Joint-candidate preflight review

The joint-candidate preflight evaluates declaration fields only. Its current
case correctly reports `BLOCKED`, and its result explicitly says cited
evidence is not authenticated and the result is not scientific approval. My
initial audit found malformed nested values that raised exceptions or accepted
a truthy non-string `evidence_id`; the owner added structural and primitive
type validation. Malformed declarations now return `INVALID_DECLARATION` with
exit status 2, and the six focused tests cover invalid authorities, wind mode,
and evidence ID values. The tool still does not authenticate cited evidence,
as its docstring and result interpretation state. No `research-policy.yaml` is
present in this Cloud-BAL tree, and the preflight does not change any model
input or process equation; it only reports whether declared authority fields
satisfy its gates. The fixed-background wind path can be ready for thermodynamic
candidate evaluation when other gates pass, while it continues to report the
wind component as incomplete.
