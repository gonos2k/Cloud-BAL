# PR62 KDM6 moment-gap scale audit — 2026-10-06

This read-only audit measures the retained combined PR61 KDM6 return gap and
negative cloud mass at call entry. Graphify was used first for navigation;
exact KDM6 source and retained artifacts remain authoritative. The maintained
Cloud-BAL graph is not runtime or mass-closure evidence.

## Raw call findings

The raw timestep-1 active tile contains 2,533,440 cells. At KDM6 return,
49,067 cells have `QC>0` and `NC=0`. Of these, 49,021 had positive NC at call
entry and 46 already had zero NC at entry. The count therefore includes a
large number of cloud-number state changes during the call, but it does not
identify which process produced each gap.

Most residual cloud mixing ratios are small: 35,193 gap cells are in
`(1e-15, 1e-12] kg kg-1`, 13,873 in `(1e-12, 1e-9]`, and one is above
`1e-7` (maximum `3.0768e-7 kg kg-1`). The median is `2.2737e-13 kg kg-1`.
This supports cancellation dust as a possible contributor, but the largest
residual and the absence of process tags prohibit treating all 49,067 as
roundoff residue.

At call entry there are 23,494 negative QC cells. Their range is
`-4.5860e-7` to `-4.5926e-20 kg kg-1`, median `-2.4279e-12 kg kg-1`, and
signed mixing-ratio sum `-1.8607e-4`. The weighted signed quantity below is a
diagnostic proxy for an invalid negative component; it is not physical
negative water and does not authorize clipping.

## Dry-mass scale reference

The raw trace has QC mixing ratios but no same-call pressure geometry or
horizontal mass metric. For a dimensional scale reference, I paired its KDM6
return QC with the second (t+20 s) record of the matched WRF output and used
the C-grid HYBRID_OPT=2 dry-pressure relation documented in
[`NATIVE_MASS_FRAME_CONTRACT.md`](NATIVE_MASS_FRAME_CONTRACT.md):

```text
dp_dry = -(C1H * (MU + MUB) + C2H) * DNW
A_native_metric = DX * DY / (MAPFAC_MX * MAPFAC_MY)
m_dry = A_native_metric * dp_dry / 9.81
species mass = sum(QC * m_dry)
```

For this output, hybrid layer-to-interface closure is `0.00250 Pa`, column
closure is `0.000110 Pa`, and `sum(DNW)=-1`. The active horizontal native
metric ranges from `25.296` to `26.798 million m2` per cell. Source documentation
binds this dynamics integration metric separately from physics `AREA2D=DX*DY`;
the serialized `AREA2D` field is not substituted for the map-factor metric.

With those t+20 weights, the 49,067 gap cells represent about **1,746 kg** of
positive QC, compared with **1.420e12 kg** of positive QC over the active
tile, a weighted share of **1.23e-9**. This shows the count can be large while
the gap's aggregate QC mass is small. It does not make the full moment gate
pass, nor does it establish a water budget or global Q/N conservation.

The KDM6-return QC and t+20 WRF `QCLOUD` use the same interior crop and agree
exactly in 2,484,370 of 2,533,440 cells; the maximum difference is
`2.50e-9 kg kg-1`. Later host updates therefore changed some values after the
KDM6 return. The 1,746 kg result is a **cross-stage diagnostic reference**,
not an exact first-call dry-mass integral: same-call `MU/MUB`, hybrid
coefficients, map factors, and gravity were not captured with the raw trace.
The accessible source algebra and output geometry also do not establish the
executed host binary's complete mass-closure contract.

Using the same t+20 weights, negative entry QC has a signed proxy of about
`-2.12e6 kg`. Because QC is negative in those cells and the state is invalid,
this is not a physical water amount.

## Source-order review notes

In the selected KDM6 source copy, cloud `pcond` is formed after separate warm
and cold mass and number process updates. The current full-evaporation path
moves NC to NCCN when `pcond == -QC/dtcld` before the subsequent floating-point
QC update is stored. Vapor and temperature are then updated using the same
`pcond`. Deferring only the NC transfer until after finalized QC and the
existing `QC <= qmin` cleanup is a testable hypothesis; where final QC remains
above the cleanup threshold, its NC should remain with that QC. A surviving QC
residue must not be zeroed without corresponding vapor and latent-heat changes.

The follow-up instrumented native trace (same first-call pre/post raw hashes as
the retained PR61 capture) provides process attribution for this run. Across
280 KDM62D returns, the final gap counts sum to 49,067; 49,066 are tagged as
residuals in the exact full-cloud-evaporation branch. There were 2,299,811
`pcond == -QC/dtcld` equality branches in total, and 49,066 left positive QC
after the branch's stored update. First-stage counts among final gaps are 44
present at entry, 13 first appearing after warm/cold updates, none first
appearing before condensation, and 49,010 first appearing after condensation.
The one gap not tagged as an exact-evaporation residual was already present at
call entry; its generating pre-call process was not localized by this trace.
These captures strongly support floating-point cancellation in the full
evaporation branch as the cause of nearly all gaps in this run; they do not
establish that it explains other configurations or runs.
The untagged gap had NC zero at call entry, did not take the exact-evaporation
branch, and has the largest returned QC (`3.0768e-7 kg kg-1`). The source of
that entry state is not localized here. This is why the branch-specific
correction cannot be described as repairing every gap.

For example, at `(i,j,k)=(167,280,6)`, `QC=3.0924054e-6 kg kg-1`,
`NC=2,891,842`, `pcond=-1.5462027e-7 kg kg-1 s-1`, and `dtcld=20 s` before
the branch. The double-precision arithmetic remainder is `1.14e-13`, while
the stored single-precision QC is `2.27e-13`; NC is moved to NCCN and becomes
zero, while QV increases by the pre-branch QC amount. This illustrates the
roundoff mechanism for one cell.

A reviewed targeted candidate uses one positive phase extent `E=QC_before`
inside the existing exact full-evaporation predicate: move NC to NCCN, set
`QC=0`, add `E` to QV, and subtract `E*xl/cpm` from temperature. This keeps
the water and latent heat updates tied to the same incoming amount while
removing the residual. For the equality predicate's zero-QC/zero-rate edge, it
retains the existing NC transfer and executes the old Q/QC/T arithmetic; all
other cells also retain the old arithmetic sequence. The candidate should
remove the measured positive-QC full-evaporation inconsistency, but does not
repair or certify the complete PSD/moment gate; report full post-call QC/NC
gate counts after any patch. Other KDM6 paths update mass and number with
separate sedimentation/accretion tendencies and donor bounds, so their
effects remain a separate audit question. No number floor, QC deletion, or
production prior is proposed here.

## Matched positive-extent candidate result

The candidate build identity is recorded in
`/var/tmp/kdm6_pr62_extent_patch_20261006/build_final_manifest.json`: the
production source hash is `43be4388…`, the diagnostic instrumented source is
`10879c5c…`, preprocessed Fortran is `a847491d…`, the selected object and its
archive member are `668047a5…`, and the executable/run copy is `15cbd378…`.
The executable matches the recorded launch image. Compilation used the pinned
Intel profile and exact WRF CPP macros including `RWORDSIZE=4`; host closure
remains partial because the other host objects and libraries were retained.
The selected KDM6 object is hash-bound to its archive member, and the linked
executable is hash-bound to the launch copy. The recorded link-command note
references the retained PR61 library list rather than expanding every linker
argument, so describe the link-input manifest and resulting executable as the
identity evidence.

The first candidate directory was created with hardlinks and its mutable raw
capture names initially shared inodes with retained PR61 controls. That
incident is recorded in the native run receipt. The PR61 raw files were
restored from an independent byte-identical PR62 control; their current hashes
are again `d2331e90…` and `526285de…`. I checked that the candidate raw files
now have distinct inodes and the candidate post hash remains `c1601094…`.

The diagnostic-only candidate run used the same first-call input trace as the
retained PR61 case: candidate pre.raw SHA-256 is
`d2331e90aee601dd9a1aa2549230fa7f388231ce224e53fdf60cb4b4b9b7e2bb`. The
candidate post.raw SHA-256 is
`c1601094ff2d5b0fb97212a3fc8a1ea9fb7291f2e4a70a971a220e034a8dbf51`. The
post-call QC-positive/NC-zero count fell from 49,067 to **one**. Its first
stage is call entry, with NC zero, QC `3.0767936e-7 kg kg-1`, and no exact
full-evaporation tag. The source step that created this entry state is not
localized here. The representative positive full-evaporation cell now has
QC=0 and NC=0 after that process update.

The source-bound mean-mass checks still fail: QC/NC has ten violations (the
one positive-mass/zero-number gap plus nine positive-pair lower-bound edge
excursions); QI/NI has three lower-bound excursions; QR/NR has 260 excursions
(259 below and one above); and QG/BG has 33,674 strict volume/density flags.
The QC, QI, and QR positive-pair mean-mass excursions are at most
`1.50e-7` relative to their nearest bound. For QG/BG, 31,209 positive pairs
fall just outside the declared density range `[100,900] kg m-3`; their
relative deviations are at most `5.93e-8`. The remaining 2,465 flags have
QG=0 and positive BG, each below `9.985e-12 m3 kg-1`. These remain reported as
strict gate failures; this audit does not relax bounds or call the complete
PSD gate a pass. The 3,533 post-call internal NI values above the initializer's
`1e6 m-3` candidate cap are a separate prior-cap diagnostic, not counted as
source-bound post-run PSD violations absent evidence that this cap is a
runtime invariant.

The matched candidate output has finite `REFL_10CM` at all 2,573,532 cells,
with range `[-35,68.5091] dBZ`. Entry QC negatives remain 23,494; at return,
none are negative, 23,464 of those cells have QC=0 and 30 have positive QC.
With candidate t+20 hybrid weights, the single remaining gap is about
**477.47 kg** of QC on a dry layer weighing about `1.55184e9 kg`. Its weights
use candidate t+20 geometry and the source-derived HYBRID_OPT=2 C-grid
formula. This is only a cross-stage diagnostic reference, not a first-call
mass integral or proof of whole-model conservation. The signed weighted proxy
for negative call-entry QC is `-2.12445e6 kg`; negative QC is invalid state,
not physical negative water.

At the representative full-evaporation cell, `E=3.0924054e-6 kg kg-1` and
the branch uses that one amount for `QV+=E`, `QC=0`, and latent cooling. In
FP32 storage, the logged QV values (`0.014248719` to `0.014251811`) imply a
stored QV increase of `3.09199095e-6`; the shortfall from `E` is
`4.15e-10 kg kg-1`, within half a QV ULP (`4.66e-10`). Thus the real-valued
phase algebra is paired. In binary64 arithmetic on the stored QV/QC operands,
the before/after pair differs by `-4.15e-10 kg kg-1`; evaluating the QV+QC
sum in FP32 rounds both sums to the same value. Stored temperature is
`293.59780884 K` before and `293.59036255 K` after, consistent with cooling.
The process trace does not capture `xl/cpm` or full-precision mid-process
inputs, so it does not establish a precise per-cell stored enthalpy residual.
No domain-wide conservation conclusion follows.

The frozen PR61 cloud mean-particle-mass envelope is
`[4.1888e-15, 3.0301e-10] kg`. As a deliberately limited counterfactual,
post-gap QC divided by positive call-entry NC is below the lower bound in
48,992 of 49,021 cells. Entry NC is not the final tendency-updated number, so
this is not a predicted deferred-transfer state. It shows why moving NC alone
cannot be described as restoring PSD realizability or passing the full moment
gate; any proposed ordering change needs its own paired post-call Q/N check.

## Reproduction and limits

The external read-only reducer is
`/var/tmp/pr62_moment_scale_audit_20261006.py` (SHA-256
`a16154c60184fda1e75f0f69e8b4a06042fdb5dad286b05f998824f97723ce58`). It reads the raw captures and matched WRF output without modifying
them and writes [`evidence/pr62_moment_scale_audit.json`](evidence/pr62_moment_scale_audit.json).
The reducer emits the base receipt for raw pre/post and WRF output hashes,
hybrid closure checks, area distinction, crop comparison, counts, and weighted
values. The `native_process_trace` section was added separately from the
instrumented run log and build manifest; it is not emitted by the reducer. The
combined JSON therefore carries both the reducer output and the separately
audited process and build evidence.

This is a scale audit of one one-rank, one-tile, 20-second diagnostic run. It
does not establish the source of all QC/NC gaps, authorize the native moments,
prove conservation, or provide forecast/science acceptance.
