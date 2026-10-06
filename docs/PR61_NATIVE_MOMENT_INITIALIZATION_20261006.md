# PR61 native KDM6 PSD prior experiment

Date: 2026-10-06. Scope: a source-bounded, explicitly assumed research prior
for one copied PR60 2026-08-16 12 UTC input and a maximum 20-second native
diagnostic. Policy was written before the experiment in
[`PR61_NATIVE_MOMENT_POLICY_20261006.json`](PR61_NATIVE_MOMENT_POLICY_20261006.json).
The experiment is not an operational startup authorization, science acceptance,
or a coupled forecast.

## Prior policy and source

The selected patched private KDM6 source is
`Cloud-BAL/scratch/ccn_native_start.j2U4Rf/phys/module_mp_kdm6.F`, SHA-256
`9f34e893e814872138f8d8402095be0cc76fbf0700c6095f69d7f530c05bcdae`. The
20-second trace executable used its instrumented copy with SHA-256
`9986e3ecfc116bb1a723d68dc423418541971f421d5a6dfafa47e59273bf6a80`. We
checked the PSD bounds, gamma parameters, mass-size coefficients, and ice
number cap against upstream KDM6 source SHA-256
`02c9dc1f6711c9785d3c5841cbf2c14ebc454fa4628466407ae7f8879e965c5a`; these
constants and formulas match. The public dry-air basis and wrapper behavior
come from the selected patched source only. Host constants source SHA-256
`5b80377fecdc18a5f0ad38d3b6c15cfc86ad5d76701adbbbb08a08698d0f7062`
declares `rhowater=1000 kg m⁻³` and `epsilon=1e-15`; the driver source
`bcac98180bfb5e260271a5836d71c5936d47ab167e2164c37b328f37ec2c03f4` passes
those values as DENR and QMIN. The selected wrapper converts public number per
kg dry air to internal number per m³ by multiplying by DEN (lines 320–327).

The prior uses source KDM6 gamma PSD mass-size inversions for cloud, ice, and
rain. It selects the geometric midpoint of each source lambda interval,
intersected per cell with the existing internal number cap. The number is
computed as `N_public = Q * lambda^d / pidn`; the DEN conversion cancels from
the PSD mass/number ratio. The geometric midpoint is a declared research
assumption, not a fitted result. For ice, 3,086 active cells in the retained
baseline trace have no feasible lambda because even source `lambda_min`
exceeds the `1e6 m⁻³` internal ice-number cap. Their input NI values remain
zero and are reported as unresolved.

For graupel, source code carries `rho_mid=400 kg m⁻³` and density support
`[100, 900] kg m⁻³`, but `rho_mid` is unused by the active initialization and
default path. The prior center 400 is an independent declared research choice
informed by that unused parameter, not an operational source default. The
source's zero-BG recovery path instead uses `rho_max=900`; that numerical
fallback is not the chosen prior. The candidate volume is `BG = QGRAUP / 400`
on the public dry-air basis. The source interval is an admissibility envelope,
not a statistical uncertainty estimate. Gamma PSD support is unbounded in
individual diameter; derived particle-mass bounds refer to the PSD mean
particle mass, not hard minimum and maximum sizes for every particle.

Two field labels in the frozen policy are historical errata and were not
changed after the experiment. The QICE value `1e-15` labeled
`source_active_mass_threshold_kg_kg-1` is the strict research fill cutoff;
the selected source's relevant PSD branch uses a separate `QI >= 1e-14`
comparison. Likewise, the frozen graupel field labels 400 as a source default,
although that parameter is unused in the active path. These errata do not
change the frozen policy's numeric values or its hash.

## Preflight and source copy

The initializer rejects a source file unless its exact PR60 SHA-256 matches,
its `MP_PHYSICS` is 37, its sole time is 2026-08-16 12:00:00, its serialized
units and `[Time,z,y,x]=[1,39,282,234]` shape match, and all mass/moment
arrays are finite with nonnegative masses.
It binds the retained timestep-1 pre-call trace by SHA-256 and full native
bounds. The trace DEN is used only as a baseline first-call cap proxy; it is
not claimed to equal the initial `wrfinput` density. The new 20-second run
must recheck candidate number moments against its own actual first-call DEN.

Only exactly zero moments with mass strictly above the declared research fill
cutoff are initialized in the active domain. The strict fill choice differs
from source process comparisons and does not cover every positive mass.
Existing nonzero moments and the outer ring are retained.
All hydrometeor mass, QVAPOR, T, QNCCN, and every nonmoment variable are
fieldwise hash-checked as unchanged. The receipt records units, dry-air basis,
source identities, thresholds, changed values and counts, mass-field hashes,
source-bound validation, the unresolved NI cells, and complete before/after
variable hashes. The candidate and its receipt use a two-file publication
transaction with rollback for handled failures; this does not make the pair
crash-atomic.

## Retained baseline and diagnostic failure

The baseline `wrfinput_d01` and `wrfbdy_d01` hashes are
`397daf0387d522243167f5e48831f7415bea07f00c22e5674ef89f73db1a2c0c` and
`64ab86c004af0f81b221c89c5bfb6ff57aef7410c7f5542ce93c00c7f732009d`. Its
one-rank, one-tile, 20-second WRF executable hash is
`ab8cc24579adb6112684029636e3bdd2ab06e6fa600721b7ee6c322b21a7ba62`. That
diagnostic build reused host objects and libraries; compiler/source closure
and operational equivalence remain unestablished. Baseline pre/post raw
KDM6 trace hashes are
`aa01a611b81cf041961748a945e91b4d52aa6704c9fea4398ec7cbe9138139b2` and
`ffdfabb7fadb3d986400003ecc0283af1511c4f6931c842130c3309852fd7c1c`.

At first-call entry, NC, NI, NR, and BG were zero over 2,533,440 active cells.
Positive mass/zero moment counts were QC/NC 1,510,952; QI/NI 835,790;
QR/NR 361,253; and QG/BG 7,377. After baseline KDM6, QC/NC gaps remained at
238,835 and QR/NR at 33,617; QI/NI and QG/BG gaps became zero through model
evolution. The latter is not startup evidence.

The retained cadence-repeat t+20 `REFL_10CM` record had 33,617 nonfinite cells
out of 2,573,532. All 33,617 overlap post-call QR>0 and NR=0; no nonfinite
reflectivity lies outside that mask. KDM6 reflectivity computes `lamr` from NR
when QR exceeds `1e-9` and immediately evaluates `1/lamr`, matching the exact
failure mask. This is the diagnostic gate the bounded prior experiment is
intended to investigate; removing this failure would not establish that the
assumed prior is physically correct.

QNCCN remains separate from cloud number. In the retained PR60 baseline, the
first-call capture had 98 negative and 88 zero active cells; their origin was
unresolved at that stage. PR61 later bracketed the negatives to RK advection
and tested a scoped PD limiter reserve; see
[`PR61_CCN_ORIGIN_20261006.md`](PR61_CCN_ORIGIN_20261006.md). In the matched
PR61 PD source-copy run below, call-entry NN had no negative or zero cells.
The initializer itself leaves QNCCN untouched.

## PR61 prior and initial diagnostic result

The policy bytes were frozen at SHA-256
`20fd53ec626cbb4e192583f99777b5f7f56d580959171c240b804c38873517b3` before
initialization and execution. The copied input initialized 940,173 NC,
255,428 NI, 206,095 NR, and 1,468 BG values. Its input-state source-cap check
left 3,094 ice cells unchanged as infeasible. Eight positive cells at or below
the strict QRAIN fill cutoff also retained NR=0. These differ from the 3,086
ice-infeasible cells estimated from the retained first-call state.

The original initializer receipt predates code-hash recording, so it does not
identify the code bytes that produced it. A later independent replay using
initializer source SHA-256
`5975542b273bc406b52b03912e03b908429394a42ddee245ca4f858752d69d6e` produced
the same candidate input bytes (`aecc4885…66739`) and a distinct receipt
`f8efcfbf…006f2`. That replay is separate evidence and does not retroactively
bind the original receipt to the later code hash.

The isolated one-rank run used the same executable, boundary, namelist, static
tables, timestep, damping, and 20-second duration. An initial Intel MPI launch
stopped with SIGSEGV before the WRF tile strategy and produced no KDM6 trace.
The copied case then completed with the executable's MPI singleton launch and
unlimited stack. No prior values or physical constants changed between
attempts. The successful run's executable, boundary, and namelist hashes match
the retained PR60 case.

The actual first-call trace has 88 NI cap exceedances on cells initialized by
this prior. Candidate NI multiplied by actual first-call DEN has no cap
exceedances; the 88 occur after input initialization but before KDM6's captured
entry, so the intermediate mutation origin remains unresolved. At entry,
NC/NI/NR/BG contain respectively 4,832/2,231/1,889/115 negative values.
These are intermediate model values, not values written by this initializer.
No clipping or retuning was applied.

The first PR61 prior run had one nonfinite t+20 `REFL_10CM` cell. It overlapped
the post-call QR-positive/NR-zero cell at global `(i,j,k)=(35,117,15)`; QR was
`1.745910083e-9` and NR was zero. At first-call entry the cell had QR
`1.385846282e-8`, NR `0.2151257843`, and DEN `0.7838002443`; initial QRAIN and
NR were both zero while QCLOUD was positive. The retained first run showed
the symptom but did not capture process-rate variables.

## Source-copy process-order experiment

Targeted runtime instrumentation of the selected KDM6 source copy confirmed
that `prevp == -QRAIN/dtcld` triggers an early full-evaporation NR-to-NCCN
transfer before the later finalized warm/cold updates. At the target cell,
the warm mass-limiter factor was exactly 1.0, finalized QRAIN remained
`1.7459101e-9`, and the regular rain number update would retain internal NR
`192.2938`. This is the exact process order behind the initial proposal; no
post-hoc prior adjustment was made.

A source-copy-only candidate deferred that transfer until after finalized
warm/cold Q and N updates, and transferred the remaining NR to NCCN only if
final QRAIN was at or below `qcrmin`. When final QRAIN remained above
`qcrmin`, regular NR was preserved. Its selected source file hash is
`61bac0c2868a5d31dcfaa9f4a4e076622cdfaa260ca69524eeb8ce3f5a840244`; an
aligned instrumentation build added later chain logging and has source hash
`b39afa8e02689367b81f8006a104a686995b33f82202ddd7a1bb138f1812f00d`. Both
are private forensic copies, not changes to the maintained WRF/KDM6 source.

The follow-on path was also captured. With finalized QR and NR, source
`slope_kdm6` computed a mean-volume diameter of `23.8646 µm`, below its
`82 µm` cutoff, and the existing small-drop path transferred QR to QC and NR
to NC. In the subsequent cloud step, `pcond == -QC/dtcld` triggered the source
NC-to-NCCN transfer. The target finished the KDM6 call with zero QR, NR, QC,
and NC and a positive NCCN state. This source-supported reclassification and
cloud evaporation removed the QR-positive/NR-zero reflectivity failure; it
did not provide a general moment closure.

The aligned 20-second source-copy run used the identical candidate input,
wrfbdy, namelist, static tables, executable ABI inputs, timestep, damping, and
one-rank/one-tile cadence. Its executable hash is
`6aeb5b3ead1be9a9c76f559c6b8078c6bbcb049ee5a55589365b8788a6d8468e`. The
post-call trace has 48,980 QC-positive/NC-zero cells. Source-bound checks on
the complete post-call active arrays fail for cloud (48,989), ice (1), rain
(259), and graupel bulk density (33,636) cells. At call entry, NN/QNCCN still
has 98 negative and 88 zero values; the KDM6 return has finite positive NN,
but that internal clamp does not establish valid call-entry provenance.
Therefore the all-moment and CCN gate remains FAIL even though the paired
rain gap is zero.

The t+20 `REFL_10CM` field is finite at all 2,573,532 cells (range `[-35,
68.5091] dBZ`). Between baseline and source-copy output, only one QVAPOR cell
changed, by `+1.8626451e-9 kg kg-1`; all condensate, temperature, pressure,
and dynamics output fields compared were unchanged. At the target first-call
capture, QVAPOR gained `1.8626451e-9` while QRAIN lost `1.7459101e-9`; the
sum residual `1.1673507e-10` is below half the actual FP32 ULP
(`2.3283064e-10`) of the rounded `QVAPOR + QRAIN` sum. The observed FP32 sum
equals that addition exactly; TH and derived temperature were unchanged.
This is a storage-rounding result for the target transfer, not a domain-wide
conservation or science-acceptance claim.

## Matched strict-profile PD and finalized-order run

The combined confirmation used the pure PD source-copy patch
[`native_pd_roundoff.patch`](native_pd_roundoff.patch) and the KDM6 patch
[`native_kdm6_finalized_evaporation.patch`](native_kdm6_finalized_evaporation.patch)
for finalized evaporation, both with the original WRF routine interfaces. The
PD patch removes the earlier trace-only dummy argument, automatic capture
arrays, and debug writes while retaining the same 69-operation roundoff
reserve. Its compiled source hash is
`a1dc18bce40f84ad709d38fbe7b0658590e587d42528b1124f9c8b7e9c1830fa`; its
normalized limiter block is byte-identical to the independently reviewed PD
candidate after removing only those debug captures. The KDM6 patch defers
terminal NR-to-NCCN bookkeeping until after the finalized warm/cold number and
mass updates. The combined run compiled an instrumented extension of that
patch: production-patch source hash
`61bac0c2868a5d31dcfaa9f4a4e076622cdfaa260ca69524eeb8ce3f5a840244`, compiled
instrumented source hash
`b39afa8e02689367b81f8006a104a686995b33f82202ddd7a1bb138f1812f00d`. The
extension adds target-cell process-chain logging used for the retained process
trace. The PD patch and KDM6 production patch are reviewable artifacts; neither
was applied to the maintained WRF source tree.

Both native runs used the same copied prior input, boundary, namelist, static
tables, 20-second duration, timestep, damping, and strict freshly compiled PD
and KDM6 objects. The PD-only control used the same PD patch and KDM6 source
without the ordering change. The combined run used executable SHA-256
`47bb9cc921374cb0c2190f83de941c0aa1d55eb7981b93732a4f10a851a0e14d`; its
KDM6 and PD object hashes are `9572c18ec0937a320d555d8ea0432c0cd98c9833f861b514aa6e7be849603116`
and `0b9be5ea72d428ef66d5876a3820681a82471e319bdcbe7fabf8f67d1c30316c`.
Only these two objects were freshly compiled with the pinned Intel reproducible
profile appended after the retained host ABI flags; reused host objects and
libraries still prevent a whole-model compiler-closure claim. The child launch
record reports an unlimited stack and verifies the executable SHA immediately
before execution. The matched PD-only and combined runs have identical
first-call pretrace hashes, confirming they entered KDM6 with the same state.

The combined run completed at t+20 with finite `REFL_10CM` at all 2,573,532
cells. Its KDM6 return had no negative, zero, or nonfinite NN values; the
matched PD-only run had one QR-positive/NR-zero cell, while the combined run
had none. At the traced cell `(i,j,k)=(35,117,15)`, finalized QR and NR fed
the existing 23.8646 µm small-drop path (under the source 82 µm threshold),
which transferred QR to QC and NR to NC; the subsequent full cloud evaporation
transferred NC to NCCN. No number floor or reflectivity replacement was used.
At combined KDM6 entry, QC had 23,494 negative values, separate from the
post-call 49,067 positive-mass/zero-NC cells.

Compared with the matched PD-only run, the KDM6 ordering change affected one
first-call return Q value by `+1.8626451e-9 kg kg-1` and one QR value by
`-1.7459243e-9 kg kg-1`. Their residual is `+1.1672e-10`, below half the
actual FP32 ULP (`2.3283064e-10`) of the rounded Q+QR sum; the FP32 addition
reproduces the candidate Q exactly. TH and derived temperature were identical.
At t+20, only one QVAPOR cell differed from the matched PD-only control, by
`+1.8626451e-9 kg kg-1`; all condensate, TH/derived temperature, pressure, and
dynamics fields matched. This comparison isolates the KDM6 source-order patch
within this one 20-second run; it is not a general conservation proof.

The 69-operation reserve used by the PD limiter is a conditional roundoff
bound for finite normal-range binary32 operands/results, positive timestep,
and normal positive mesh metrics. It does not cover overflow, underflow,
subnormal/FTZ behavior, upstream face-flux construction, external negative
tendencies, or a negative low-order seed. The strict/no-FTZ flags applied to
the selected PD object; retained host objects and libraries remain outside
that compiler-closure claim.

The combined post-call state still has 49,067 QC-positive/NC-zero cells, all
above the source `qmin=1e-15`; the complete moment-realizability gate remains
FAIL. Strict binary64 source-bound checks also flag 9 cloud, 3 ice, 260 rain,
and 33,674 graupel cells. Apart from the 49,067 actual cloud zero-number
gaps, these flags are tiny FP32 edge excursions (maximum relative excursion
below `1.5e-7`) and are kept separate from robust physical failures. The
rain-only ordering run and the earlier one-NaN prior run remain separately
identified in the evidence record. An earlier combined debug build with a
changed optional PD diagnostic interface crashed at `advect_scalar_pd` because
the retained caller objects used the original interface; it is preserved as a
failed ABI-mismatched attempt and is not counted as a model result.

## Evidence files and limits

The source-bound policy is accompanied by a hash-bound initializer receipt and
the experiment evidence at
[`evidence/pr61_native_moments_20261006.json`](evidence/pr61_native_moments_20261006.json).
The experiment is research-only, limited to 20 seconds, and remains a failed
all-moment/CCN gate if unresolved cells or negative QNCCN persist. No longer
forecast, science assessment, or operational claim follows from graph or
source freshness.
