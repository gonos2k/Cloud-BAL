# PR67 agent-team review (2026-10-07)

Base: `3405d25aa62f0ebecd7e1b94a3915e7c1bb2aa6e`.
Overall physical approval: **FAIL/OPEN**. Research candidate safety: **REJECTED**.

## Independent assignments and review

Four agents worked in parallel: same-call PBL carrier, completed negative-QC
updates, KDM6 process/bottom budget, and joint-input admission/reader integration.
The joint-input agent independently reviewed the other three code/evidence paths;
the PBL agent reviewed negative-QC replay. Root reviewed all integration changes.
Agent reviews concern the stated implementation and evidence scope; they do not
approve whole-model physics or operational enablement.

## Findings addressed before publication

- The transpose tridiagonal solve now shifts opposite diagonals correctly;
  a nonuniform dense-reference test prevents the earlier draft indexing error.
- Negative-QC replay uses the correct 21-column observer mapping, asserts the
  initial mask, binds the executable and contains receipt paths. Invalid channel
  fields and their nonclosing decomposition are excluded from attribution.
- Budget parsing uses the existing canonical big-endian KDM6 and geometry
  readers. Stage bounds, time argument, density and optional accumulator flags
  must agree across rows; finite reductions are required.
- Output moment pairs use QGRAUP/QIB; CCN is not a graupel descriptor.
  Reflectivity failure is retained, and candidate execution exit 0 is separated
  from physical/output acceptance.
- Large NetCDF integer-mask reads use allocated single-level buffers; actual
  pinned-Intel O0/O2 reader tests succeed under an 8 MiB stack. The original
  unsupported mask is rejected; support is never widened.
- Scratch model-target preparation rejects symlink/alias/existing destinations.
  Actual reader evidence predates that guard-only edit and cosmetic diagnostic
  wording; run hashes remain attached to the tested bytes.
- Compilation recipes, captured commands, static coefficients, retained host
  archives and source-bound selected objects have separate provenance. No full
  clean-host reconstruction is claimed.

## Scientific results and unresolved gates

The measured ice-sedimentation unit defect is reproduced in a fresh selected
source build. A research normalization changes the same-call hybrid-weighted
water-plus-bottom-fall residual from approximately -1.291e12 to +6.53e6 kg.
This does not close all carriers, cleanup, boundaries or energy. Ice-only and
combined experiments produce 26 and 25 reflectivity NaNs at 20 seconds and are
rejected. The combined 25 overlap positive rain mass with zero rain number.

The PBL DEL and linked hybrid-dry measures differ, and completed incoming QC
still contains 23,494 negative cells. The 13 UTC model-target reader result is
API compatibility evidence; it is not authority for the 12 UTC observed joint
candidate. Full observed joint search and native initial-response comparisons
remain unperformed.

## Validation and publication

The [final focused validation receipt](evidence/pr67_focused_validation_20261007/receipt.json)
records **79 passing tests** in 11 selected Python modules: 19 new regressions
and 60 directly affected dependency tests. Shell syntax checks pass. Hash-bound native patch context is preserved by four
exact-path `.gitattributes` whitespace exceptions; maintained code remains checked. All tested
source hashes were stable during each batch. This is not the full suite.
Actual pinned-Intel reader/native evidence lives in the linked per-task manifests;
Python replays do not replace those builds. Full unit suite, full host rebuild,
multi-rank/tile runs and forecast/scientific approval are not claimed.
Graphify/KG metadata will identify the frozen commit and separate corpus snapshots;
graph freshness is navigation evidence only.

See [closure checklist](PR67_PHYSICAL_CLOSURE_CHECKLIST_20261007.md),
[PBL audit](PR67_PBL_SAMECALL_CARRIER_20261007.md),
[KDM6 budget](PR67_KDM6_SAMECALL_BUDGET_20261007.md), and
[joint admission](PR67_JOINT_INPUT_ADMISSION_20261007.md).
