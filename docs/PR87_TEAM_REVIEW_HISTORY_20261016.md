# Historical PR87 team reviews

These candidate-specific notes are preserved; current status is in PR87_TEAM_REVIEW_20261016.md.

# PR87 independent team review

## Scope and status

This review covers candidate build provenance, the narrow opt-in joint
REAL32 storage path, the cold-reason append probe and first-call summary
reader, host cleanup, stage audits, and the V10 physical-source capture path.
It does not approve the model scientifically. Current review status is
**V24c static/build review passed; matched 40-second validation is running.
The latest closed V23c attempts completed only 20 seconds. No two-step
completion or scientific approval has been established.**
Earlier v3–V18 passages
below are historical candidate records, including incomplete runtime attempts.
They do not establish two-step success.

The candidate is a selected-object partial overlay, not a clean WRF build. The
PR85 parent executable, archive, and frozen runtime inputs remain separately
identified. v2 receipts remain preserved as incomplete historical attempts.

## Findings and resolutions

| Review finding | Current resolution |
| --- | --- |
| Cold-reason file opened with replacement semantics per KDM6 call, overwriting earlier records | The candidate opens `pr87_admission_reason.raw` with `STATUS='UNKNOWN'`, `POSITION='APPEND'`, and write-only access. |
| First-call summary could not bind the run-root receipt/preflight or analyze a failed later step | The reader now checks candidate `preflight.json` and `receipt.json`, binds the frozen source receipt, candidate build receipt and executed executable, and permits incomplete runs only under explicit first-call-only scope with at least one completed step. Artifact paths and compressed hashes are checked under `run/`. |
| Joint underflow storage needed a subnormal guard; v4 adds a distinct normal-Q constrained-rounding policy | Joint Q/N absence is limited to positive subnormal Q that rounds to zero. The separately opt-in v4 one-neighbor Q adjustment applies only when an already valid continuous pair fails the stored predicate after ordinary rounding; default strict behavior remains the default. |
| Signed storage-ledger arrays were not initialized before invalid calls returned | The kernel initializes optional output arrays at entry, requires all three ledgers when opt-in is enabled, checks their sizes, and keeps candidate deltas local until successful commit. Failed candidates leave model arrays unchanged and the ledger outputs zero. |
| Directed upper-bound repair and joint-underflow number-delta accounting lacked targeted tests | The Fortran tests now cover one-ULP Q movement down at the upper endpoint and assert signed Q and N deltas for paired underflow. |

No unresolved concrete source-level correctness, provenance, or gate blocker was
found in the reviewed components. This statement is limited to code review and
the build identity checks below; it does not imply runtime success.

## Historical v3-v4 build and test evidence

The v3 build receipt at
`/var/tmp/pr87_joint_cycle_build_20261016_v3/pr87_native_overlay_build.json`
reports `PASS_OVERLAY_BUILD`. Independent SHA checks pass for the candidate
executable (`0a53474445b5a1a021572ae05d99fc677993bd4355d7dac97383589bbdf72ea5`),
all six requested/staged override source pairs, all six replaced archive
members, the unchanged parent executable and archive, and the bound parent
receipt. The source manifest binds the current kernel
(`d49236feec85aeb2bd5bd9613ada539e72c104588971f510d9e64b436ad39a52`), patch,
generated native fragment, and their exact parent embedded components.

The build uses pinned `ifx 2026.0.0` and the profile hash recorded in the
receipt. The archive order places `module_em.o` before `solve_em.o`; both the
retained PR85 stage observer and the PR87 cloud-cycle observer are linked.
Build identity and targeted-kernel O0/O2 evidence are recorded in
[the review evidence JSON](evidence/pr87_team_review_20261016.json) and
[the kernel test receipt](evidence/pr87_native_cycle_20261016/joint_storage_ifx_o0_o2.json).

The source-first v4 candidate is separately bound to
`/var/tmp/pr87_joint_cycle_build_20261016_v4/pr87_native_overlay_build.json`
(receipt SHA-256
`20d00cb0a2fab917ba1be1759a2cdc2a2f527b1ac4dc0d063d84a4aab62bb103`). It
reports `PASS_OVERLAY_BUILD`, uses pinned `ifx 2026.0.0`, and records candidate
executable SHA-256
`e0f364bbf71d4a34dbf39bd53bf7e29ffe2cd4c81e150088fccbf4316a75f870`.
The compiled `module_em.F` source SHA is
`158a3f9c78e897086047208fc86fc177189de4ef53d1ec16a9f3fdef38f8e543`; its
embedded `cloud_bal_joint_transport` prefix exactly matches current kernel SHA
`dc6f682aa64c27651044a35ae31e07cf16ee5b1848daedd185db524218209b9e`.
The preprocessed `module_em.f90` SHA is
`0ef8bc39cdaec5437c1b2af2576b3397f2ccc35c72491219327f08a06966f7bc`, and the
source-first patch SHA is
`5cd8d34ca99583eb78a67e7e1e6234ac699286a53d7a94b825119c349c6e35e0`.
All six requested/staged override source hashes match. Parent executable,
archive, and receipt hashes remain bound by the v4 receipt; this is still a
source-mapped partial overlay, not a clean build. The same pinned O0/O2 kernel
test receipt passes for kernel SHA above and test SHA
`c1a8258b11fe19c8283a4c96727001f25e0207cb6d7427617ce6e20b36b93bb2`.

## Storage policy boundary

The opt-in path first validates the continuous REAL64 pair. It handles joint
absence for positive subnormal Q when ordinary Q rounding is zero, and permits
one adjacent REAL32 Q value toward the PSD interval when ordinary independent
rounding alone fails the stored predicate. The latter policy also applies to
continuous-valid normal-Q pairs in v4; it is a deliberate extension beyond the
earlier subnormal-only policy and is separately identified by the candidate
source/build hashes. N is unchanged for the one-neighbor adjustment. No number
floor, invalid-continuous-pair repair, or wider PSD interval is used. The full
stored-pair checks remain in force and the native grouped path requires theta
equal to one.

The signed `carrier_new*(stored-continuous)` ledger is a numerical
representation term. It reports added storage loss or gain; it does not
compensate for it and does not establish mass or energy conservation. Physical
closure remains open.

## Historical v3 runtime follow-up

The OFF and COUPLED v3 40-second runs use the same candidate identity and the
original frozen geometry inputs. Their receipts bind the candidate executable
SHA above and confirm that the candidate did not change during execution. Both
reach `FOGDES_INPUT` on timestep 2 with the same target pair as the end of
timestep 1: `QC=8.4692146629095078e-9`, `QNC=2.021875875e6` at
`(230,70,3)`. The paired host-cleanup repair therefore survives that boundary.

Both then stop during the timestep-2 RK3 joint source/transport candidate with
`PR87 full joint moment candidate infeasible`. Their diagnostics report 445
source-only failures and 17 full-candidate failures. The opt-in storage ledger
shows 447 QC/QNC and 135 QI/QNI special storage adjustments in the successful
timestep-2 RK2 update; it does not make the later RK3 candidate feasible. The
two completed-state receipts each report one completed timestep, so the
40-second two-step runtime gate fails.

`PRE_RK` and `RK_STAGE_END` are intermediate snapshots. In frozen v17
`solve_em.F`, `PRE_RK` is emitted after the ordinary moisture/scalar advancement
and immediately before the deferred paired Q/N/B update. QC/QI/QR/QG/QS are
excluded from individual `rk_update_scalar` for MP37; QV is not. With effective
`MOIST_ADV_OPT=1`, the positive-definite moisture correction runs on the final
RK stage. Therefore a negative QV in an earlier predictor remains a strict
all-field audit failure and must not be reclassified as an accepted physical
input. Paired QNB validity and final-RK3/PRE_KDM6/POST_KDM6 status are separate
checks. Because the RK3 joint candidate did not commit, timestep 2 has no
completed `RK_STAGE_END(3)`, `PRE_KDM6`, or `POST_KDM6` state. The available
completed-state audit can only cover the completed first timestep and earlier
second-timestep predictors; it cannot establish final timestep-2 paired-state
validity.

The exact receipt and compressed diagnostic hashes are recorded in
[the review evidence JSON](evidence/pr87_team_review_20261016.json). No
two-step runtime success or scientific approval is claimed.

## Historical v3 interpretation of the 17 full-candidate ratio failures

The frozen source supports a source-order difference at final RK. In
`solve_em.F`, the positive-definite path calls `rk_update_scalar_pd` before
`rk_scalar_tend` when `rk_step == rk_order` (around lines 1841 and 2236).
`rk_update_scalar_pd` applies the physics tendency to `scalar_old` with old
carrier in both numerator and denominator, then zeros that tendency. The
subsequent `advect_scalar_pd` uses both the current field and this prepared
old field (in `module_advect_em.F` around line 6069). MP37 skips this stock
source-prep and scalar-update path for paired QC/QI/QR/QG/QS. The PR85 wrapper
then adds physical source and its custom air-flux tendency in one numerator,
using old-time Q/N as its upwind donors.

Preparing paired Q/N as
`(oldcarrier*Qbase + dt*Qsource)/oldcarrier` before forming grouped shared
face fluxes is therefore a focused way to restore the native source-first
ordering **inside the existing grouped low-order donor operator**. The
completed update must add the source only once, reject an invalid continuous
prepared pair, limit the change to RK3, and leave the donor boundary ring
unchanged unless source activity there is explicitly represented. This is a
testable correction hypothesis, not a runtime fix established by the 17 rows.

The v4 source-first candidate implements this hypothesis. Independent review
confirmed the RK3 preparation equation and footprint against frozen
`rk_update_scalar_pd`: for this call `mu_old=mu_new=mu_1`, so the prepared
donor is `(m_old*x + dt*S)/m_old`. The source is counted once in the committed
update, paired Q/N use the same prepared upwind donor map, and the outer
horizontal donor ring remains unchanged and is validated. Singleton snow/CCN
calls omit the optional pair index and retain the old donor path; RK1/RK2 are
unchanged by source preparation. A two-cell convex-cone example in
[the focused source-first note](PR87_SOURCE_FIRST_GROUPED_TRANSPORT.md)
demonstrates why additive old-donor transport can cross a pair bound while
transport of valid source-prepared donors preserves it under shared
nonnegative weights and carrier continuity.

This does not reproduce stock `advect_scalar_pd`: that routine uses a
high-order flux with a low-order positive-definite correction, while PR85
already deliberately uses shared first-order donor-cell fluxes for paired
moments. Accordingly, this restores source-first ordering within grouped
low-order transport, not exact native PD advection. The low-order CFL guard
alone does not prove carrier continuity or boundary-flux consistency. This
remains a configuration-bounded research change; mass/energy closure is open.
The one-neighbor normal-Q storage rule is now enabled in the v4 constrained-
storage identity, with signed ledger and full stored-state validation; invalid
continuous pairs remain rejected.

## Historical v4 runtime status

The v4 OFF and COUPLED 40-second runs closed **INCOMPLETE** under candidate
executable SHA `e0f364bbf71d4a34dbf39bd53bf7e29ffe2cd4c81e150088fccbf4316a75f870`.
Both returned code 1 before completing the first timestep. Their receipts bind
the same candidate executable and show unchanged inputs. The strict two-step
gate fails; v3 remains preserved as a separate historical candidate.

The grouped source-prepared continuous donors passed at the failing RK3
boundary: both arms report `SOURCE_FAILURE_COUNT 0`. The full candidate still
has 10 storage failures, all pair 2 (ice), at the same cells in OFF and
COUPLED. For example, at `(183,59,2)`, continuous
`Q=7.3521320088e-46`, `N=4.6910077510e-37`, and `Q/N=1.567282e-9`, inside the
ice interval `[2.605588e-16,2.098275e-9]`. REAL32 round-to-nearest stores Q as
one minimum subnormal (`1.40129846e-45`) while retaining N; the stored ratio
becomes `2.987201e-9`, above the upper bound. The adjacent Q toward the
interval is zero, which with N unchanged fails the stored pair predicate. The
same pattern holds for all ten rows: continuous Q is 0.5094–0.7453 of one
REAL32 subnormal quantum, continuous Q/N is within bounds, and source-only
failures are zero. There is no completed timestep-1 RK3/KDM6 state to audit.

A constrained-storage quantum-absence rule is under v5 review: after ordinary
rounding and one directed adjacent-Q adjustment fail, it may store `(Q,N)=(0,0)`
only when the already validated continuous pair has
`0<Q<minsubnormal(REAL32)`. This bounds Q loss to less than one REAL32 quantum.
It can discard the entire N value, which in these rows is continuous-valid and
independently representable (`N*rho` is about `0.97e-37` to `6.43e-37`). That
signed N loss must be recorded as a numerical representation term; it is not
physical zero, a number floor, or evidence of mass/energy conservation.

The kernel now exposes a separate `joint_quantum_absence` update flag, default
false. It rejects the option unless constrained storage is active; constrained
storage alone still rejects the retained row, while explicit opt-in stores
`(0,0)` only after the continuous check, ordinary rounding, and adjacent-Q
attempt fail. The three signed ledger outputs remain mandatory, are accumulated
locally, and are copied only after the complete candidate validates. Pinned
Intel O0/O2 kernel tests pass for this API and the retained row, including the
signed Q/N losses and rejection outside constrained mode. The source-first
patch explicitly enables the option for its v5 candidate; v4 and prior
strict/subnormal identities remain unchanged.

The O0/O2 evidence receipt initially labeled its retained fixture timestep as
2; that metadata is corrected to 1 to match its bound v4 raw record
`FULL 1 3 2 ...` (timestep 1, RK3, pair 2). The corrected receipt SHA-256 is
`93a1e84db6725fe2ede1859e544738f673e94770e57f1ac8487e1a60f4ecda92`. The
source and test hashes remain unchanged. The pending v5 integration status in
this historical note was later superseded by the incomplete v5b run; the active
v7 runtime status is recorded below.

## Historical v7 source/build and fallback test

The v7 source manifest and overlay build receipt bind the admissibility-selected
RK3 fallback to parent receipt SHA-256
`a2c09db99d3b934a6de677c30901434ce75012fb2fd9020f19c800ee19954353`. The
generated native fragment SHA-256 is
`6f1068a8878bec2ebb78c5852433fdfe98df7c22110784a86b8ba89c7bef192a`; it
matches both the `module_em.o` source component in the manifest and the
proposal bound by the focused Fortran receipt. The current transport kernel is
SHA-256 `4149f75aa94d5ca917dc3acfb17db36342f454122459251aa007ea78d30cc9bb`.
All six requested source hashes match their staged and compiled source hashes.
The archive receipt records six replaced members, `module_em.o` before
`solve_em.o`, and the stage/cycle observers in the link inputs. Parent
executable, archive, and receipt hashes match their recorded identities.

This is a selected-object overlay build, not a clean build. It used pinned
Intel `ifx 2026.0.0` from `tests/intel_toolchain.sh` (profile SHA-256
`5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`). The
candidate executable SHA-256 is
`c7fb1a30e6b47f79a414fc7f0a04f6c2da593adae279061641f924b57b1fb095`.
The receipt and these checks establish identity and compilation provenance;
they do not establish runtime success.

The extracted exact native fragment passed its focused two-cell fixture at
Intel O0 and O2. Receipt SHA-256 is
`fb7c5919dcfa169125f46dac7d561a5ea49c45755060c6cf30bf8894d842d9ff`; its
proposal hash matches the generated fragment and its kernel/profile hashes
match the v7 inputs. In both optimization modes, the admissible baseline kept
all four fallback flags false and passed; the fallback fixture selected only
cloud pair 1, completed with the expected paired mass total, and passed. This
tests baseline retention and whole-pair fallback wiring in the extracted
fragment. It is a focused synthetic test, not an integration or scientific
validation.

The matched OFF/COUPLED v7 40-second runs closed **INCOMPLETE** with one
completed timestep and return code 1 in both arms. They used executable SHA-256
`c7fb1a30e6b47f79a414fc7f0a04f6c2da593adae279061641f924b57b1fb095` and build
receipt SHA-256 `0bb6b05c295ff35713269caffc155208199fefb31550c240932be62bcab3a906`;
the OFF and COUPLED run receipt hashes are recorded in the evidence JSON. The
second-step RK3 fallback stopped at a source-prepared cloud donor in the
intermediate PSD check: `(146,103,4)`, `Q64=4.638877968449027e-6`,
`N64=1107451465.72224`, and `Q/N=4.1887866981364437e-15`. This is about 8.28
REAL32 ratio spacings below the lower bound, just outside the existing 8-spacing
tolerance. This was a virtual transport donor, before the combined source-plus-
air candidate was committed; it is not evidence that the final endpoint passed
or failed the unchanged full-pair predicate.

## v8 source/build binding

The v8 source manifest SHA-256 is
`c1cd6ff4fb73485f3053a417109faccc287b18f7daefa6e85f2a183cba65004f`; it binds
the same parent receipt and current transport kernel SHA-256
`4149f75aa94d5ca917dc3acfb17db36342f454122459251aa007ea78d30cc9bb`. Its
generated native fragment SHA-256 is
`035d3de7310191b340f486b116241757c4d4a87312278a37ae63a8b9f9f688b9`, matching
the composed `native_update.f90` and the embedded `module_em` component. The
source/build records bind all six requested, staged, and compiled override
hashes; the overlay archive hash and six replacement object hashes; the
unchanged parent executable, archive, and receipt; module order; and both
observers. The independent checks pass.

The pinned Intel overlay build receipt SHA-256 is
`acab8e20efa5d4f269eb647dbae55a54d9e11159b2e5bc7969f1fa53b3113fb8`; the
candidate executable SHA-256 is
`7d6f16bc98d3648f341ba062db3462ec7e307d2fedc63823d1124d85b18472d5`. It uses
`ifx 2026.0.0` and profile SHA-256
`5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`. This is
a source-mapped selected-object overlay, not a clean build. The donor-only
change removes the ratio interval test from the virtual source-prepared
transport donor guard while retaining finite, nonnegative, paired-zero,
REAL32-range, and number-volume checks. The unchanged boundary ring and full
committed candidate retain the existing PSD predicate and tolerance.

The v8 exact-fragment regression passed all five modes at pinned Intel O0 and
O2. Its immutable receipt is
`source_first_virtual_donor_guarded_ifx_o0_o2.json` (SHA-256
`71e3392bc3ce4d3f4d2984464de6ddb4b2ed0344c067f115cf153161930feb1f`). It binds
the current generated native fragment, kernel, density helper, pinned profile,
and test runner hashes. Both levels retain the admissible baseline with no
fallback, select only cloud pair 1 in the source-first and virtual-donor cases,
reject a negative virtual donor before commit, and reject an invalid final
endpoint before commit with the storage ledger absent. The virtual-donor case
exercises an intermediate outside the PSD cone whose committed endpoint passes
the existing full predicate. This is component-level evidence only. The matched
v8 runtime and completed-state audits remain pending; no dynamic or two-step
PASS is claimed.

## V9 source capture, build, and exact-fragment review

The V9 source manifest is `/var/tmp/pr87_joint_cycle_sources_20261016_v9/sources.json`
(SHA-256 `f3647a192eb20231966ac8f35efaebfff6d1135a186d4db8c990210a2ec49168`).
It binds the generated native update fragment (`28b0762b4192b66a0b8c55fe6101c01e84c4200fae400105cc82d6f0887f8609`),
the part2 source capture (`007fcce0cdc51cf18c2d8c33de42ec1367c3419e3c2c38770ecf7be8800b44c8`),
and capture generator `tools/pr87_physical_source_capture.py`
(`832f6677a6d09a388aa5ba1573bb8c5d7cbf6f3f77f18f4cfbfc4001d298c551`).
The capture explicitly carries intensive and coupled-reference Q/N rates,
source carrier, and step identity; it uses no saved cache. The cloned
`update_phy_ten` receives shadow tendency outputs while its source arrays are
read-only. A consumer-side comparison verifies captured coupled rates and
carrier against the live stage and rejects stale or mismatched payloads.

The V9 overlay build receipt
`/var/tmp/pr87_joint_cycle_build_20261016_v9/pr87_native_overlay_build.json`
has SHA-256 `8ed28717bffe95083c41619a6c3398679fc401280f405308d93ca208ab5966fd`;
it reports `PASS_OVERLAY_BUILD`, uses pinned `ifx 2026.0.0` and profile
`tests/intel_toolchain.sh` (SHA-256
`5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`), and
binds candidate executable SHA-256
`88de62b1e8e795e2c8e1c3a4957df0db2edbd0fadd848ffc84f3868634555df1`.
The seven requested/staged/compiled source hashes agree, archive member and
parent receipt identities are recorded, and the archive retains `module_em`
before `solve_em`. This is a selected-object partial overlay, not a clean
build.

The nine-mode exact-fragment fixture passed at Intel O0 and O2. Its immutable
receipt is
`docs/evidence/pr87_state_cycle_20261016/source_intensive_stage_ifx_o0_o2.json`
(SHA-256 `c51c1f57ace65f90b66437947e87fc2ab2ad4a0a67eb3fe0d83e489e01dcbeff`),
binding proposal SHA above, kernel
`4149f75aa94d5ca917dc3acfb17db36342f454122459251aa007ea78d30cc9bb`, pinned
profile, source-matched density helper, and runner
`tools/pr87_source_first_fallback_regression.py`
(`023c2a93eda27fdd32844bc52330fe81ac439bbd0e8bcf08358afd60b477d346`).
Both optimization levels preserve the admissible baseline without fallback;
the selected cloud fallback succeeds, and negative donor, invalid final
endpoint, stale carrier, stale source reference, and stale step are rejected
before commit. This is component-level evidence, not full-model validation.

The V9 OFF and COUPLED 40-second runs are active. Their runtime receipts,
strict completed-stage audits, and two-step acceptance remain pending. The
signed source-representation ledger includes producer coupling and REAL32
staging differences; it is not a physical transfer or conservation claim.
Scientific approval remains open.

## V10 source cadence, build, and exact-fragment review

The V10 source manifest `/var/tmp/pr87_joint_cycle_sources_20261016_v10/sources.json`
(SHA-256 `b2078d4017db6118c73121bb74ad2d4940305de5c68dcf612444082fd258ec61`)
binds generated native update fragment
`b0a467b8f96728cb0b98cae014edb78df68edc995d5bab40138e8ef405651bf4`, kernel
`4149f75aa94d5ca917dc3acfb17db36342f454122459251aa007ea78d30cc9bb`, physical
source-capture helper `tools/pr87_physical_source_capture.py`
(`2f5bb09165326a41811e2d8c55a8182ce2f8bd2d97869da252014a7efab788e5`), and
the source-mapped host changes. The generated fragment hash matches the
reviewed proposal. The solve source hash is
`c2d0b35e8543f08ee1d474b14ef7863542676269dc0ebeb87bac9ed415cea5f8`.

Cadence review confirms the grouped update copies paired q1/n1 from q2 only at
RK1 and commits subsequent stage predictors to q2/n2. Thus the old-state base
remains unchanged through RK1/2/3, while q2 remains an intermediate for the next
stage. The later non-air tendency D is computed once after RK1 scalar and
boundary tendency updates, as widened live tendency minus the original coupled
capture; the source reference is updated once and the timestep/equality guards
remain. The fallback stages the physical source in the local R32 base and adds
D through the R64 source-rate argument. Its donor and completed endpoint use
`(W*stage + dt*D + dt*A)/Wnew`, so the physical stage and later source each
enter once. It does not mutate host q1 or add the separate PD advection tendency.
The source ledger records pressure-carrier amounts and numerical representation
deltas only.

The V10 overlay receipt
`/var/tmp/pr87_joint_cycle_build_20261016_v10/pr87_native_overlay_build.json`
has SHA-256 `2a3bf857db09a16d6f375ea60861e4b8f93b8b9be54a612fd0871b0c98b21004`.
It reports `PASS_OVERLAY_BUILD`, binds the seven requested/staged source hashes,
uses the pinned Intel profile (`5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`)
and ifx 2026.0.0, and produces executable SHA-256
`08958980d8225417c1551922a5b2cb8c1841d7411b6836d770a111900d963b0b`. This is
a selected-object overlay, not a clean build; the build receipt claims no model
run.

The 12-mode exact-fragment fixture passed at pinned Intel O0 and O2. Its
immutable receipt is
`docs/evidence/pr87_state_cycle_20261016/source_later_stage_ifx_o0_o2_v10.json`
(SHA-256 `74995a45f264580e4622511c7be63eee452deecdac70fb67ab4f383bdf6ebcb9`).
It binds the V10 fragment, kernel, density helper, profile, and runner. The
cadence mode checks bit-equal old q1/n1 after each RK stage, fallback only at
RK3, use of the same D at each stage's distinct `dt_rk`, and final state equal
to one full source application rather than cumulative application. Invalid
endpoint, negative/nonfinite donor or source, stale carrier/reference/step
cases reject before commit. These are component tests, not model validation.

The source-representation parser and its tests check finite values, row
identities, signed-delta arithmetic, L1/max summaries, and group aggregation.
They parse and report the separately supplied `SOURCE_LATER_TOTAL` amount and
identity residual, but do not independently recompute or threshold that
residual. They impose no physical-acceptance threshold, do not aggregate the
later-source amount into a physical conservation claim, and mark
`physical_mass_or_energy_claim` false. The parser tests pass (10/10), including a trailing metadata record without
its required totals. The closed V10 OFF/COUPLED runs are INCOMPLETE after one
step: second RK3 and PRE_KDM6 pass, then internal rain-freezing base validation
rejects. The new V11b runtime is evaluated separately; scientific approval
remains open.

### V10 second-call rain-freezing source review correction

The PRE_KDM6 host `NR` is number per kg dry air, while the rain-freezing ledger
records converted internal number per m3. These values cannot be compared
without respecting their unit bases. At `(i=114,j=2,k=18)` before second-call
KDM6, `QR/NRdry = 2.9309917692e-10 kg/particle`, just above the bound
`2.9309320335e-10`; the PRE_KDM6 pair is valid. The freezing packet later sees
`QR=7.9431267119289828e-10` and `NRvol=1.7165578603744507`, which with its dry
carrier gives `rho*QR/NRvol = 2.8910133e-10 kg/particle`, below the lower bound.

The cutoff trace does not report this second KDM6 call: `pr67_trace_this_call`
is disabled after the first call (`module_mp_kdm6.F` sets the saved
`pr67_trace_complete` after its first trace dump). The first-call cutoff row
therefore cannot establish the second-call starting state. Source review
narrows the change interval to KDM6 entry through rain sedimentation and the
freezing call. The wrapper converts host number-per-kg to internal number per
m3 before entry; the rain sedimentation sweep updates Q and N with separate
mass and number fluxes (`module_mp_kdm6.F:2537-2561`). At the recorded
temperature, the melt branches are inactive, and the sub-qcrmin rain pair does
not enter the PSD boundary-number correction. The freezing packet then applies
the full rain-cone predicate. No per-process second-call snapshot captures the
state between entry and sedimentation, so the precise incremental source of
the cone crossing is not established. This corrects any earlier review wording
that treated the second-call PRE_KDM6 pair as invalid or used the first-call
cutoff row as proof of an empty second-call receiver. It does not support
loosening the rain-freezing predicate or changing N to force acceptance.
The structured source-only correction record is
`docs/evidence/pr87_state_cycle_20261016/v10_second_call_rain_freezing_source_review.json`
(SHA-256 `d711dd1b386768ba5c1c48d3da6452e07e470e90817b781f5def675cf217cd05`).

## V11b rain sedimentation integration review

The new required rain pair bounds match across the explicit interface,
embedded helper and all three calls. Rain uses internal volume number and
extensive mass/number packets with distinct source velocities and one face
admission factor. Both old rain mutation sites now only accumulate approved
flux diagnostics; they do not update the pair twice. G/ICE mode behavior and
zero inert bounds are retained. Rain ledger open/trace/close runs on every
call with timestep/loop/lat context. The helper body equals the pinned tested
body. This is a changed numerical operator, not native-flux bitwise identity.

V11 and V11a were unlaunched build failures: the original external signature
and then the copied parent compiler-generated interface retained the old
arity. V11b binds the explicit current interface and excludes only the stale
parent helper genmod from module staging. Unrelated module copies and duplicate
conflict checks remain tested. No code-level launch blocker was found in the
reviewed V11b source; actual first-post changes, packet withholding, storage
residuals and two-step completion remain runtime questions.

The rain helper intentionally requires its input pair to satisfy the full
rain cone. Earlier native paired-state checks and slope caps alone do not
imply that condition, and the later native count reconstruction is gated by
mass/number cutoffs. Thus this research path can reject a paired state before
a later native reconstruction; it does not accept every old native source
state. Actual entry and per-call success must be evaluated rather than
inferred from paired positivity. No count reconstruction is added to hide
such an entry failure.


## V13 strict rain producer closure review

The V13 generated KDM6 wrapper retains the supplied dry carrier `DEN` directly and uses that same R32 carrier for host-specific to internal-volume number conversion and the public return conversion. The strict rain bounds use the selected source's default-REAL coefficients (`PIDNR=12566.37109375`, `DMR=3`, `LAMDARMIN=961`, `LAMDARMAX=35000`); the wrapper asserts these values before running. The warm process option defaults off and adds strict rain PSD checks only to the opted-in warm rain pair path. Existing pair-only cloud/ice behavior and default kernel storage behavior remain unchanged.

The strict storage mode checks the continuous number-volume cone, then checks both the R64 density product and the actual R32 public-to-internal product. Only the selected rain pair receives this additional contract; an admissible one-quantum Q adjustment leaves N unchanged and is recorded, while invalid continuous inputs reject. No entry reseed, N floor, or cone tolerance increase was found. The public-return helper and native grouped update are bound in the V13 source manifest and partial-overlay build. No static source or API blocker was found in this review.

Static evidence: generated KDM6 source SHA-256 `f9652dc7208bb81edd57a23de53c58d3b23a531967ea46c0ec7aa510e0599a98`, native update fragment `4a1175d2f4a007672ab5d47d95316237889661665f323d046a7ff71bfa333b01`, kernel `ffdce6170547fd0416d6073d4542a6a7e6dc4c316d4d04f4dc76a117a58efe19`, public store `7116a6979e14cb4d8cc64752f70e62d768aab1598fc4004f4615b63caa4b02fa`, source manifest `059e5d30f489a65d34ce716f31baee90f3039fb24324506a539af274d57dbcf4`, and build receipt `d68d83cfe70bb5ed3f037f40bfdabcc479fa5e3dbf632c76a312a89c09370690`. The pinned Intel partial overlay build passed and produced executable `dd7b52b21506014ad45009bab377862d3a3c653bc597e3d5e32fcc85c1b4dbcd`. The focused source/test shard passed 99 tests; the exact native fragment O0/O2 receipt passed 12 modes (`beac27781a1e74867a44d197185546655d7b673b7b6910ca7431478dc78d1ce1`), and the standalone public-store fixture passed with pinned Intel O0. Runtime OFF/COUPLED 40-second closure, strict stage audits, and scientific acceptance remain pending; the partial overlay build is not a full clean build.


## Historical V14 warm zero-step review; strict warm domain superseded

V14's zero-alpha control change remains a valid narrow control: it evaluates the source-ordered endpoint at `alpha=0` on retry 0 only when the fraction helper returns status 1 (`NO_FEASIBLE_STEP`). Status-0 positive retries and status-2 failures remain separate. However, V14 also opted the warm consumer into the full strict rain cone. That domain choice was overscoped: the isolated V14 component rejected a warm base with reason 6 at `QR=3.3341e-10 < qcrmin=1e-9`. This is a sub-cutoff warm transient, for which the existing `consumer_pair_only` contract requires paired nonnegative Q/N, while the later rain sedimentation and public storage boundaries retain their strict cone checks. V15 removes only the warm strict-rain opt-in and retains the status-1 zero-step control and sparse status-1 trace.

The source-order endpoint must be tested because the fraction predictor forms R32 process increments from summed rates times `dt`, then scales those increments by alpha, while the native endpoint scales individual rates, sums them in source order, and applies `dt`; near the exact rain cone this can change the last R32 Q/N bits. A validated zero step is a withheld-process control response, not an accepted warm source update. V13 and V14 failures remain historical evidence; V15 was superseded by the V16 direct-REAL64-rate candidate.

V14's generated-source and zero-step fixture hashes are preserved in the historical evidence record. Its focused pinned Intel control-flow fixture passed O0/O2; the V14 runtime candidate is superseded after the sub-cutoff strict-base failure.

## V15 pair-only warm domain and source/build review

The generated V15 warm fraction call and its base/trial validators use `consumer_pair_only=.true.` without `require_rain_psd`; other process validity checks remain. The status-1 alpha-zero path validates the unchanged pair-only base and then the same source-ordered zero endpoint. Strict rain-cone gates remain in paired rain sedimentation and completed public storage. The V14 rejection was reason 6 on a sub-`qcrmin` warm pair, so V15 restores the established transient consumer domain without weakening a completed-state gate. No `nrmax` reset change was made; the prior V11b examples did not establish that cap as the cause.

The pinned Intel 2026.0 overlay build passed. Manifest `a8f1130489b8a5e7a32a0a266bd91fad8a706d6b69bc8aab9785babf3e19abc6` binds generated KDM6 source `cacefe3d99d744c26203068791e83a991fa6db2d6e33a5a4ba950fa4f24fe738` and native update `4a1175d2f4a007672ab5d47d95316237889661665f323d046a7ff71bfa333b01`. Build receipt `588a4dea2cd92d36f612aa8552c659310058c8ddab1d488dd8687452f6a45853` reports `PASS_OVERLAY_BUILD`, not a full clean build; executable SHA-256 is `20e2c3b537a08e1259eaff783ac7d4caffa3633535270cc4b8fd34420775184e`. All seven requested/staged override source hashes match. The focused shard passed 103 tests (`306d91c784d4cd66603561536f8eebdd849189d039f29f3c2a5d55b1b12b0987`).

An isolated replay completed the first full KDM6 component using the V15plain source (same physical source as V15; final V15 adds only failure-only nongraupel diagnostics). The receipt binds replay input `93dff951d5d3a497b51a0b9281d2e1ebe9830fd4e8ed8c70318b25809a13b847`, replay executable `660327f68e30f16a9e9ef50015aa4188ba1cf60736f19f84e97e22e70f12bcc4`, and completion marker `REPLAY COMPLETED FULL FIRST KDM6 CALL`. This replay is component evidence only. Its outputs were contained under a private run cwd; earlier attempts that ran with the maintained KLAPS50 cwd were quarantined and are explicitly excluded from evidence. The V15 OFF/COUPLED 40-second runs closed incomplete after timestep 1 and rejected 131 rain candidates at step 2 RK1; see the V15 runtime evidence archive. V16 is the current candidate; its 40-second runtime receipts and strict completed-stage audits remain pending, and scientific approval remains open.

## Current V16 direct REAL64 shared-face candidate

The V16 source manifest (`f0a7e3384ea6e5d543df8515a228ee0e626961acceb4e3fd03672514f57d890c`)
binds the selected-object build and the targeted source changes. In the
grouped transport kernel, `air_tendency` computes paired Q/N shared-face
fluxes in REAL64; V15 rounded each moment rate to REAL32 and promoted it back
before forming the endpoint. V16 keeps the REAL64 rates in the candidate
calculation for all four pairs. REAL32 diagnostic arrays remain separate.
The RK3 source-first retry remains limited to whole PBL cloud/ice pairs; rain
and graupel still do not trigger that retry. No PSD tolerance or rain source
policy was changed for this precision correction. The V15 cold audit found
63 of 81 positive-N source ratios and 78 of 81 air-rate ratios strictly outside
the rain cone, all within the existing 8-ULP band. Those source-only failures
show that the air-rate correction may be incomplete; V16 runtime must test the
combined endpoint without widening the cone.

The pinned Intel overlay build passed with executable SHA-256
`0886693c1355e195620cbc845c3381cd30d09ec64f28e48f21af031e690beb29` and
build receipt SHA-256
`76683e7edd31a057503246fc0ed619fcfba3ce943d0251fc9c792df58dbbfe60`. This is
a selected-object partial overlay, not a clean model build. The focused V16
shard reports 103 passed. Both 40-second preflights bind the candidate build,
the same frozen baseline executable, and their original OFF/COUPLED inputs;
runtime receipts have not yet closed. V16 must be audited for source-only and
full rain endpoints as well as for completed states.

Pending acceptance gates are matched OFF/COUPLED receipt closure at the
requested 20- and 40-second times, unchanged source/executable/input identity,
strict completed-stage and all-field audits, and the remaining scientific
checks for carrier/face closure, water and energy accounting, observations,
and physical response. No runtime completion or scientific validation is
claimed here.

## V19 directed-Q strict rain storage and source/build review

The opt-in strict rain store derives an admissible Q interval from the fixed
rounded N, dry density, source mass limits, and both volume products used by
the next native call: REAL64(N×ρ) and the actual REAL32(N×ρ). It selects a
representable Q in that intersection, reruns the stored-pair predicates, and
leaves N unchanged. Invalid continuous pairs are rejected before adjustment;
an empty or nonrepresentable Q interval fails atomically. Signed Q/N storage
deltas are emitted only after the grouped candidate commits. The kernel does
not add an N floor, expand the existing mass tolerance, or repair an invalid
continuous state. No concrete kernel or API blocker was found.

The frozen kernel is
`src/common/cloud_bal_joint_transport.f90` (SHA-256
`19d0259c423a3035a418174292c14d8671d778ebfe48a604cc80923c2f854541`); its
focused test is `tests/test_joint_qnb_transport.f90` (SHA-256
`79dfb1b41029379a61c231ccff52c7e69fc1f444ad85eb4b84943a0f718fbd53`). The
pinned Intel O0/O2 runs in `/var/tmp/pr87_directed_q_store_pass2_O0` and
`/var/tmp/pr87_directed_q_store_pass2_O2` both end with
`PASS test_joint_qnb_transport`; their copied source hashes match the frozen
files. The shared compile log SHA-256 is
`181bb7f947e8f096d37f3cc1f648e5dc588e0ade51f5d1a2d2f476db82817943`.

The first report of a pass was incorrect. An explicit execution returned 128;
the test failed because the grouped API reports one adjusted cell while its
assertion expected scalar adjustment class 2, and the shell command path had
hidden the nonzero status. The test now checks the grouped count, the N storage
delta, and an explicit terminal pass marker. The failed execution log is
`/var/tmp/pr87_failed_q_store_explicit_returncode_20261016.log` (SHA-256
`6f12640f69f348a4de81dd5667f71492d042326321b832ed36c17bdd11f9e292`). This
was a test assertion and status-reporting error, not a compiler failure.

The V19 generated source manifest SHA-256 is
`b58f89f00446e58a65e46b079c9a6717197fdc36b1268dcf884b2850e4146649`. The
native fragment is `e2abb1809b6fa49ab56ebc82ecc205f9fca6f9dba28192ce49ed1136d32b648e`;
the generated `module_em_pr85.F` embeds the reviewed kernel byte-for-byte.
The pinned Intel selected-object overlay build passed with executable SHA-256
`461260ae28de31295406e6d64e7bfcc498aeeba5c84289dac1dd71c1ce7ab9cf` and
build receipt SHA-256
`7d32ba0a9d4d9466a81ecbfe7c5be5424f5e23e383620b4e17f12b9b41d0ea3e`. This
remains a partial overlay, not a clean build. The V19 exact native-fragment
fixture passed 19 modes at both O0 and O2; its receipt is
`/var/tmp/pr87_source_first_fallback_ifx_o0_o2_v19_directed_q.json` (SHA-256
`9524298618090573b79b1b863d0f3f4a6f9a0756b099615d326dcdbdbf849f1e`).

The first directed-Q pass2 test receipt remains preserved, but its overflow
fixture did not isolate an overflow caused by R32 rounding. Pass3 replaces that
case: with `rho=REAL32(1.7)`, the test verifies the continuous R64 validator
passes and `N64*rho` is at or below `HUGE(REAL32)`, while `REAL(REAL(N64,REAL32),REAL64)*rho`
exceeds `HUGE(REAL32)`. The store rejects before casting the overflowing
number-volume product. Pass3 O0/O2 both exit zero, show an explicit test pass
marker and contain no failure text. Receipt:
`docs/evidence/pr87_two_step_v19_20261016/directed_kernel_ifx_o0_o2_pass3.json`
(SHA-256 `995b16e0b50d4e79f0582e12505f29025b7efcfb0ab524bccdf82940cabe563e`);
final test SHA-256 `7e6a471bc2362d4690d86ee1ed42c8394b268fc38fa71bf2af1ee390481697c9`.

## V19 runtime closure and fatal-classifier review

Both matched OFF/COUPLED V19 40-second runs closed `INCOMPLETE` with return
code 128. Each has one completed 20-second `POST_KDM6`; the step-2 trace reaches
RK3 and PRE_KDM6, then the unchanged rain sedimentation gate rejects with
`PR87 rain sedimentation packet rejected` before step-2 POST_KDM6. There is no
two-step completion. Both candidate executable hashes match the V19 build, and
the archived receipts report no changed staged or original inputs. The
original receipts were preserved with their earlier `earliest_fatal: null`;
separate fatal-collection addenda bind those receipts and record the rejection.

The runner’s shared fatal scanner now recognizes bare KDM6/PR87 rejection
messages in plain or gzipped `rsl.error.0000`, while deferred-admission text is
excluded. The 13-test runner suite passes, including the actual invalid-base
class, bare rain-packet rejection, and finalizer status checks. I applied the
scanner directly to both archived compressed RSL error logs; each returns the
rain rejection and no processing errors. The original receipts remain
unchanged. Runner SHA-256 is
`22dc932bcf7fd145df096886096db46915813da15e1020caac5641df7a74d21f`; test SHA-256
is `243df8df29f4d115096baa9a2dd3f86e4f7e86694fae55a6719577cc4064fbe1`.

Runtime manifest:
`docs/evidence/pr87_two_step_v19_20261016/runtime/runtime_manifest.json`
(SHA-256 `0e8746f53b08b96cd61de61ee68d65285cf4aec194913e3f30a17fdf43939702`).
The per-arm fatal addenda are kept with that archive. Completed-state coverage
ends at step 1; there is no step-2 POST_KDM6 state to approve. The cause of the
rain packet rejection remains a diagnostic question, not a resolved physical
claim. Scientific approval remains open.


## V20 causal evidence and V21 static review

The V20quiet source-only diagnostic reproduces V19 OFF first-call pre/post
bytes, then captures the second-call rain rejection at `(i,wrapper_j,k) =
(109,5,19)`. Exact Intel O0/O2 helper replay rejects the original column and
accepts the existing store's one-ULP Q adjustment with captured rates fixed.
The exact specific-N input is used; an earlier test with volume N supplied as
specific N is retained but excluded for invalid units. This is no native or
physics acceptance claim.

Independent V21 review confirms the corrected i,j,k ABI, post-density/filter/
boundary placement before RK observation, continuous and stored strict gates,
public N preservation, and tile-wide atomic Q commit. Root caught the draft
argument-order mismatch before the build; maintained source-order and pinned
Intel O0/O2 tests now cover the corrected interface. A suspected source-pin
composition mismatch was checked against actual V19 provenance and withdrawn:
`bbc03...` is already the post-diffusion solve preimage, and fresh complete
composition matches V21. The V21 source/build identities and these corrections
are recorded in the team JSON. Static review has no unresolved concrete code
blocker; matched runtime and all scientific gates remain pending.
