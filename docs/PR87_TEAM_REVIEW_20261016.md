# PR87 independent team review

## Final source review

The final V42 source/build is a selected nine-object pinned Intel O2 overlay
against the preserved PR85 partial host. The original initial inputs remain
unchanged; this is not a full clean WRF build or scientific approval.

Independent reviewers checked the current common transport/store kernel,
actual source-payload cadence, source-first RK3 path, producer transforms,
ProgB volume preservation and linked melt, and the final cold extinction
transaction. No remaining concrete source/commit-order blocker was found.
The final focused suite passes **194 tests**, including pinned Intel O0/O2
source-extracted regressions in fresh scratch directories.

- Candidates remain local until all coupled states pass; constrained common
  air transport must apply theta=1. It rejects rather than shrinking the whole
  air step or applying an individual cell/moment patch.
- Source-first retry is restricted to failed cloud/ice pairs at RK3. The ring
  stays at its declared old state; the source and later corrections enter once.
- G mass/volume keeps exact selected bounds. ProgB preserves prognostic BG;
  the melt proposal couples donor volume, receiver moments and temperature.
- Full ice extinction eligibility uses post-cap or aggregate donor exhaustion.
  Actual finite/nonnegative source-order stored QI=0 alone permits the number
  sink. Positive QI retains NI, and strict validation runs before commit.
- The same diffusion operator uses scalar REAL128 intermediates, R32 inputs
  and R64 output. Captured boundary replay passes, but output rounding remains
  and isolated stencil cost is about136 times the R64 variant.

## Findings addressed

Review and validation caught a stale unassigned source-rate gate, invalid melt
test modes wired to the wrong executable, an overly broad diagnostic loop,
and the final prepare hook's incorrect imported function name. Each was
corrected before the current candidate build/run; historical failed records
are kept with their actual scope.

The final extinction reviewer initially reported invalid-NI acceptance, then
withdrew that claim after tracing the pre-clear validity flag: invalid candidates
were already blocked from commit. The narrower NaN-comparison/invalid-local
mutation risk was removed by guarding the clear with candidate validity and
finite nonnegative NI. Negative/nonfinite endpoint regressions remain.

Aggregate extinction rows with `extinctions=0` are accepted pending candidate
records, not physical extinction events. The completion report documents the
meaning. The nonzero `dN` is a category-number sink, not a water/storage term.

## Actual runtime review

V42 matched OFF/COUPLED40 is COMPLETE and the independent closed-run audit
is PASS. Each arm has two distinct POST_KDM6 IDs/timestamps, unchanged inputs,
and all six air theta values one. Completed RK3/PRE/POST pass exact selected
cloud/rain/G checks and the unchanged global ice8-ULP criterion. Exact ice
source counts remain nongating diagnostics. Step2 QV predictor negatives
(4 PRE_RK, 4 RK1, 5 RK2 per arm) are recorded separately; completed endpoints pass.

The same executable's matched60 extension is INCOMPLETE after two steps,
with a third-step ProgB transient rejection. Independent review confirms the
complete17-record40 prefix is byte-identical; T3 RK3/PRE gates pass but no
T3 POST exists. Failure-cell operands are unavailable; no producer is asserted. Historical V39 completed
execution40 but failed global ice PSD in13 cells per arm; its unchanged60
extension failed at T3 RK1. Those outcomes remain preserved.

## Limits and evidence

Numerical storage changes remain signed pressure-coordinate representation
terms; they are not a kg or total-energy conservation proof. Water/energy,
host hybrid carrier, mass–wind balance, observation retention and initial shock
remain OPEN. The existing v17 cold budgets are not current-candidate budgets.

- [Final independent static review](evidence/pr87_final_static_review_20261016/review.md)
- [V42 source/build/tests](evidence/pr87_two_step_v42_20261016/)
- [Cold cause distribution](PR87_COLD_CAUSE_DISTRIBUTION_20261016.md)
- [Integration receipt](evidence/pr87_integration_20261016.json)
- [Historical reviews](PR87_TEAM_REVIEW_HISTORY_20261016.md)
- [V41 inventory provenance limitation](evidence/pr87_two_step_v41diag_20261016/provenance_incident.json)
