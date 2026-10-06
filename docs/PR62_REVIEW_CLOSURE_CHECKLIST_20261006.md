# PR61 review follow-up — 2026-10-06

Baseline: `6f403258a8b67675e0882f0edb0cbbe3a6ee5459` (PR61 merge).
This checklist separates implementation evidence, moment admissibility, joint
candidate feasibility, and native time-response approval. No scoped PASS
promotes a candidate to full physical approval.

## Work and exit conditions

- [x] Reject nonfinite derived volume bounds in the common validator. Reproduce
  the tiny-density overflow input and preserve declared 100–900 kg/m3 controls.
- [x] Locate the QC/NC incompatibility in the matched native input and
  KDM6 update chain. Use identical incoming state, record stage and actual
  source/object/executable identities; do not assign the rain mechanism by analogy.
  Full-evaporation tags identify 49,066 gaps; one was already present at entry.
  The step creating that entry gap is still unlocalized.
- [x] Quantify the 49,067 post-call QC/NC gaps on the same mask: distributions,
  total cloud-water fraction, and a dry-mass-weighted integral only when a valid
  cell-volume/carrier measure is available. A sum of ratios is not kg.
- [x] Separate the 23,494 negative entry-QC values by magnitude and bracket them
  between startup input and the public call. The generating host step remains
  unlocalized; do not hide them with clipping or count them all as roundoff.
- [x] Apply the proven full-cloud-evaporation correction using one phase extent
  for water transfer and the native latent-temperature update. This is not a
  native total-energy closure proof. Activation and collision may change number; water
  conservation does not imply conservation of total particle count.
- [x] Recheck the same 20-second run for finite reflectivity, Q/N/BG bounds,
  CCN, negative masses, process deltas, and same-input controls. Preserve failed
  trials separately and do not relabel inherited host objects as a clean build.
- [x] Retain a caller-declared component contract through writer reevaluation,
  serialize declaration/identity/coverage/tolerances, and independently replay
  the stored background/candidate against that declaration. Keep contracts
  independent of computed endpoint differences; refuse forged or partial data.
- [x] Complete team cross-review and scoped pinned Intel/Python validation.
- [ ] Freeze source; incrementally refresh maintained KLAPS50 and Cloud-BAL
  structural graphs with separate timestamps/deltas and derived wiki audit.
- [ ] Push the reviewed change and open a PR against main.

## Remaining scientific gates

- [ ] Feasible joint trial search with internal phase-transfer freedom and
  independently authorized source/boundary terms; distinguish feasibility,
  stationarity, and step norm.
- [ ] Joint Q/N/BG admissibility through common-air transport. Different
  sedimentation velocities retain their species/moment physical equations.
- [ ] Native mapped conservation, parallel rank/tile and complete host build
  closure beyond the one-rank/one-tile research run.
- [ ] Identical-setting BASE/HYDRO/COUPLED 10/30/60-minute responses and forecast
  verification, preserving observed cloud/rain/updraft signals. Fix criteria
  before results; do not reduce cloud mass or strengthen damping for a PASS.

## Current result and remaining FAIL reasons

The matched copied-source 20-second trial changes the returned `QC>qmin, NC=0`
count from 49,067 to **1**. The one cell is `(172,76,1)` and was already invalid
at call entry; its actual runtime input has QC=NC=0. The intervening generating
step is not captured. Negative entry QC remains **23,494** cells.

Strict post-call mean-particle-mass/volume checks still fail: cloud 10, ice 3,
rain 260, and graupel volume 33,674 violations. The cloud count includes the
one zero-number gap. Small float32 boundary deviations and zero-mass/nonzero
volume are reported separately in the native audit. Thresholds and prior were
not adjusted after seeing the results. Reflectivity is finite at 20 seconds;
this does not pass the full moment gate.

The actual writer fixture is a schema-5 zero-change candidate. Eleven corruptions
are rejected; two additional changed-state cases are synthetic reader controls.
The supplied contract is retained and replayed, but independent source authority,
feasible joint trial search, and optimality are not established.

### Ordered resolution plan

1. Capture Q/N/BG and carrier geometry at startup, initialization, each RK
   transport boundary, and first physics entry; locate the earliest failure
   at the remaining gap and negative-QC cells. Use fresh output files.
2. Keep moment admissibility through common-air transport and finalized process
   transfers. Apply donor limits to coupled water/number/volume/heat updates;
   account for any deletion rather than applying unrecorded floors.
3. Generate feasible trials with independent source/boundary declarations and
   internal phase freedom; use separate feasibility, stationarity, and step tests.
4. Repeat the native gate with same-call mapped budgets and parallel/host-build
   closure. Then compare fixed-setting BASE/HYDRO/COUPLED at 10/30/60 minutes
   and against independent observations before physical or operational approval.

Historical PR61 receipts and the frozen PSD prior remain unchanged. The
new native patch is applied only to an external research source copy.
