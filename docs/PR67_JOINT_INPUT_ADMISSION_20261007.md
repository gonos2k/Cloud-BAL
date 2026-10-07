# PR67 retained-observation joint-input admission inventory (2026-10-07)

## Finding

The 2026-08-16 12 UTC retained input supports the full radar producer
(`70,051` usable echo cells), but it does not carry the independent declarations
needed for a full observation-conditioned physical candidate. The existing
preflight remains the correct executable result: it measures the retained
producer and reports the physical gate `BLOCKED`. No alternate wind prior found
in the workspace repairs the other admission gaps.

## Existing authority paths and their limits

- `derive_column_physics` produces a radar-conditioned candidate and an
  aggregate `pressure_analysis_budget`. The budget is analysis bookkeeping, not
  per-cell external-source authority. `physical_joint_candidate_contract`
  requires caller-declared per-cell `source_increment`, `boundary_increment`,
  physical tolerance, and optional separately constrained phase exchange.
  Its identity string is a label, not authentication. The radar producer does
  not return an independent per-cell error envelope or admission provenance
  that can be used to fill these declarations. A candidate endpoint difference
  cannot be copied into `source_increment`.
- The VRZ observation contract supplies quality-filtered reflectivity, and VRT
  supplies bright-band/mixed-target quality. Neither supplies a per-cell
  reflectivity measurement error for this source declaration. Optional radar
  velocity products require radar identity, beam geometry, uncertainty, and
  observation identity; those LOS samples are absent in the measured 12 UTC
  case.
- The observed omega route has no source-matched `omega_target`/`sigma` pairs
  in the actual input. The producer's 55,010 omega targets are diagnostics and
  have no sigma authority. FUA `omega` is a usable background value, but this
  retained input has no background-prior uncertainty declaration for adjusting
  it. Keeping background winds fixed needs no wind adjustment authority.
- A distinct supported route exists for paired model dynamics. The reader
  `read_model_omega_increment` requires an exact valid-time, NE57 pressure-grid,
  grid-relative paired increment with matching pressure/coordinates, explicit
  target and coverage masks, and `MODEL_DYNAMICS` plus
  `ZERO_INCREMENT_PRESERVE_BASELINE` metadata. It constructs absolute targets
  from the retained background omega and gives them paired-model source bits.
  `model_dynamic_target_is_resolved` accepts these model targets without an
  observational sigma. This is a separate model-origin authority path, not
  observational authority, and it does not declare uncertainty for radar
  analysis, phase exchange, or species budgets.
- The retained CP02 paired model response
  `Cloud-BAL/scratch/cp02_native_omega_remap_6v2c9m1a/LIQUID_MINUS_HYDRO.nc`
  (SHA-256 `37ec7c3bc53ef15668abc37ab6d4e071f12b62c634fc9fcefe261a66ae899bef`)
  is timestamped **2026-08-16 13:00 UTC**. The PR65 observation case is 12 UTC,
  so the original response cannot serve that exact-time request. A separate
  retained 13 UTC case exists. Its input loads successfully and the model-target
  reader validates the time, pressure grid, coordinates, target origin, and
  boundary mode, but the original support mask has one cell outside that
  reader's `above_ground` domain. Intersecting coverage with the exact 13 UTC
  reader domain removes one coverage cell; applying the existing
  `model_target_level_is_interior` predicate then removes its one unsupported
  target at Fortran `(174,241,7)`. This creates a derived scratch artifact with
  892,338 authorized target cells and 1,150,134 coverage cells. Every non-mask
  variable, including `delta_omega`, is byte-value identical to the source; no
  support is widened. The original artifact is preserved and hash-checked.
- With `read_model_int3` changed to read one vertical level per NetCDF call, the
  pinned-Intel O0 reader handles these large masks under the ordinary 8 MiB
  process stack. The original 13 UTC artifact now returns a clean unsupported
  status instead of crashing. The derived 13 UTC artifact returns `STATUS_OK`
  with 892,338 paired-model-authorized cells and zero observational sigma cells.
  Passing the derived artifact to the 12 UTC input is rejected without
  mutating retained state; the reader returns a generic unsupported-target
  status that does not identify time mismatch as the specific reason. This is
  a scoped model-target
  integration result, not scientific approval or a full radar/phase candidate.
  The paired response itself remains a numerical trajectory proposal, with no
  observational or manufactured authority, no statistical target fit, and no
  sigma or uncertainty. It is not a production external-omega proposal. CP02
  retains it as comparison evidence after the production-plan scope changed.
  The model-origin API permits a valid paired
  target without observational sigma; it does not supply radar-analysis,
  phase-exchange, or species-budget authority.
- Fixed pressure geometry can define a zero geometric increment for a scoped
  fixed-volume trial, but it does not provide water or enthalpy boundary
  fluxes. The balance operator's omega boundary contracts and the model
  target's zero-increment boundary mode govern the wind solve; neither supplies
  the eight-component physical boundary increment required by the joint ledger.
  The retrospective column-flux inventory reports incomplete real boundary
  transport, with its available time pair centered at 13 UTC.
- The retained NC donor replay measures a later native RK invocation and
  identifies its same-call local carrier/update behavior. It does not provide
  an admitted common-air QC/NC policy for this 12 UTC radar producer candidate,
  including the complete donor-face, boundary, limiter, and common RK terms
  across the candidate's physical interval.

## Admission decision

No full-observation nonzero physical candidate is justified by the current
inputs. Keep the producer/Phi preflight labeled research-only and `FAIL_OPEN`.
Reconsider a wind correction only with either source-matched observed target
and sigma data or an exact-time paired model target with validated masks,
coordinates, and model-origin provenance. Independently, admit the per-cell
radar analysis values, their error/provenance declaration, source and physical
boundary increments, and a common-air QC/NC moment policy before evaluating a
phase-plus-Phi candidate. Leave unsupported physical tolerances and terms
explicitly unassessed; do not infer them from endpoint residuals.

## Evidence references

- `docs/PR65_OBSERVATION_JOINT_PREFLIGHT_20261007.md` and its receipt/log: actual
  12 UTC input counts and blocked result.
- `src/common/cloud_bal_pipeline.f90`: the joint contract data model and
  per-cell endpoint assessment.
- `src/common/cloud_bal_real_netcdf.f90` and `src/common/cloud_bal_state.f90`:
  paired model-target input checks and model-origin target authority.
- `tests/run_pr67_model_target_compatibility.sh` and
  `docs/evidence/pr67_model_target_compatibility_20261007/`: pinned-Intel
  O0/O2 compatibility receipt, original-mask rejection, derived 13 UTC
  `PASS_SCOPED` results, exact 12 UTC rejection, and immutable source/input/
  executable hashes. The retained run used test source SHA-256
  `cf8944230054c8cc3d39a08e97acab3d7612f52cd91ad82689e99332a53dd65d`; a
  later diagnostic-wording-only change generalized the rejection message to
  “invalid paired model target” without changing acceptance logic or recorded
  run artifacts.
- After that reader run, `prepare_pr67_model_target.py` gained checks that
  require a regular, non-symlink source and a genuinely absent output before
  copying. `tests/test_prepare_pr67_model_target.py` passes four focused
  alias/existing-file/symlink cases. These safeguards were not part of the
  retained O0/O2 model run; that run used a fresh output path and remains bound
  to its recorded source hashes. No full-input rerun is claimed for the later
  guard-only edit.
- A copied compiler hash in the model-target evidence manifest had a one-digit
  metadata typo. It now matches the unchanged `receipt.txt` and the actual
  pinned `ifx` hash; the receipt and reader-run artifacts were not modified or
  rerun. The manifest sidecar hash was regenerated.
- `docs/CP02_MODEL_DYNAMICS_INCREMENT_EXPERIMENT_20260914.md` and
  `scratch/cp02_native_omega_remap_6v2c9m1a/README.md`: the retained 13 UTC
  comparison target's scope and limitations.
- `/var/tmp/cloud_bal_pr67_model_target_compat.8W26bh/result.log` and the
  target-reader stack trace: pinned-Intel 13 UTC integration attempt; the
  minimal `int32` probe reproduces the reader crash.
- `docs/PHYSICAL_COLUMN_TERMS_20260921.md` and
  `docs/PR65_NC_DONOR_CAUSE_20261007.md`: incomplete physical boundary transport
  and separate later native donor evidence.
