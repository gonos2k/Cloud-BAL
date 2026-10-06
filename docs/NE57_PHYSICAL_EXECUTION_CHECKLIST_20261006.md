# NE57 physical execution checklist — 2026-10-06

Status: **CLEAN FROZEN-SOURCE RESEARCH REPLAY PASSED; FIRST NATIVE CALL CAPTURED; REFLECTIVITY ACCEPTANCE FAILED; JOINT AND SCIENTIFIC APPROVAL OPEN.** This checklist carries the PR59 review into a bounded NE57 execution plan. A valid build, WPS pair, or graph snapshot is not a native initialization or forecast result.

## Prior actual-case baseline

The retained source-901 replay is commit
`90179191edc33b5ae5606a37f4cd67eac507eed0`. Its declared cycle is
`262281200` = 2026-08-16 12:00 UTC, grid is 235 x 283 x 22 at 5 km, and
configuration is `LIQUID_RADAR_RH1_PHI` against an unset-experiment BASE run.
The candidate namelist selects `hotstart=false`, `balance=false`, WPS output,
grid-relative winds, and vapor output. The prior pair has 235 records; its
baseline and candidate WPS SHA256 values are recorded in
`evidence/pr59_current_lapsprep.json`.

The exact preserved inputs are in the PR59 worktree at
`scratch/current_lapsprep_aug16_262281200/inputs` (122 files, 470,989,067
bytes). `PREPARED_INPUTS.json` carries the file inventory and digest;
`PREPARED_RUN_CONFIG.json` carries the cycle, static namelist digest, and
candidate/BASE settings. The old build directory is
`scratch/upstream_lapsprep_build.JGlEuo`: `inputs.sha256` has 391 build-input
entries, `runtime.sha256` has 41 runtime entries, and
`executable.sha256` pins the LAPSPREP executable. `run_verified.sh` verifies
build/runtime hashes and launches the pinned executable. `run_JGlEuo` retains
BASE and candidate launcher logs, outputs, readback, and receipts. The
successful research generation is
`/var/tmp/cloud_bal_pr59_current_lapsprep_20261002/generations/lapsprep-262281200-9017919-o0`;
it is research-only and does not establish compiler-process closure. The
executable was compiled before commit 901 from a dirty worktree; the recorded
391-entry build-input manifest was subsequently rechecked against source 901
and all entries matched. That proves recorded file membership and bytes, but
not a clean-at-build source checkout or compiler-process closure.

The preserved `inputs/` copy currently has writable mode bits on 101 files.
Do not run a producer against that tree. For a new replay, make a new
run-specific copy, hash-check it against `PREPARED_INPUTS.json`, remove write
bits from that copy, and grant the producer read access to that copy only.
Keep output and temporary directories separate. Hash-check the copied inputs
again after each process. The retained inputs and prior generation are
historical evidence and must not be changed.

## Current source identity and safe replay setup

This worktree starts at `ea2c02bb808bc9cf77b97fc4a25a2da06dfd73a1`, the PR59
merge now named `origin/main`. It contains audit changes after source 901,
including the diagnostic-operator NaN guard and receipt-validator checks.
The new producer replay is bound to clean commit
`44212f938f0a529d298e903dc4146d7e0401134a`, recorded before the later
documentation-only evidence update. The source-901 and source-442 executions
remain distinct even though their output bytes match.

For a subsequent replay, record the full commit and clean-worktree status, then
use a new `/var/tmp` root. From this Cloud-BAL checkout, the pinned Intel O0
build command is:

```bash
freeze=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"
run_root="/var/tmp/cloud_bal_ne57_${freeze:0:12}_262281200"
mkdir -m 700 "$run_root"
mkdir -m 700 "$run_root/build"
build_dir=$(CLOUD_BAL_BUILD_SCRATCH_ROOT="$run_root/build" \
  CLOUD_BAL_WORKSPACE_ROOT=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50 \
  bash tools/build_upstream_producer.sh lapsprep O0)
```

The resulting builder path is printed first. Preserve its `build.log`,
`inputs.sha256`, `runtime.sha256`, `executable.sha256`, link map, and runtime
log under the run root. Verify the captured producer source and compiler
inputs against the frozen source before accepting the build. The builder now
defaults to `/var/tmp`; `CLOUD_BAL_BUILD_SCRATCH_ROOT` lets a run keep all
objects and module files in its dedicated fresh scratch directory. No Fortran
compile or link directory belongs under the source checkout.

For each BASE and candidate process, use a fresh run directory and the
run-specific read-only input copy described above. Set `LAPS_DATA_ROOT` to that
copy; leave `CLOUD_BAL_SHADOW_EXPERIMENT` unset for BASE, and set it to
`LIQUID_RADAR_RH1_PHI` for the candidate. Set `CLOUD_BAL_WPS_OUTPUT` and
`TMPDIR` to unique paths below that process's output directory. Launch through
`tools/run_detached_runtime.py` with the newly built `runtime.sha256`, the
sealed executable digest, the process-specific input as its sole read root,
and only its output/temp paths as write roots. Pass `262281200` as the producer
argument. Record process start/end time, exit status, complete launcher log,
environment, runtime snapshot identity, input pre/post hashes, and output
hashes. A baseline/candidate run pair is comparable only if source, build,
runtime, input copy, cycle, and static configuration identities match.

These commands create a new input copy and check its bytes without changing
the preserved input set:

```bash
prior=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr59_joint_diagnostic_20261002/Cloud-BAL/scratch/current_lapsprep_aug16_262281200
cp -a --reflink=auto "$prior/inputs" "$run_root/inputs"
jq -r '.inputs[] | select(.kind == "file") | "\(.sha256)  \(.path)"' \
  "$prior/PREPARED_INPUTS.json" > "$run_root/inputs.sha256"
(cd "$run_root/inputs" && sha256sum -c "$run_root/inputs.sha256")
chmod -R a-w "$run_root/inputs"
test -z "$(find "$run_root/inputs" -type f -perm /222 -print -quit)"
```

The producer launch shape for either arm is below; use separate output and
runtime directories and omit the experiment variable from the BASE `env`
command. Confirm the helper's detached loader list before an execution is
accepted, and capture its output in the arm's launcher log.

```bash
arm=candidate                         # use baseline for the BASE arm
out="$run_root/$arm"
mkdir -m 700 -p "$out/tmp" "$out/runtime"
env LAPS_DATA_ROOT="$run_root/inputs" \
    CLOUD_BAL_WPS_OUTPUT="$out/output.wps" \
    TMPDIR="$out/tmp" \
    CLOUD_BAL_SHADOW_EXPERIMENT=LIQUID_RADAR_RH1_PHI \
  python3 tools/run_detached_runtime.py \
    --runtime-manifest "$build_dir/runtime.sha256" \
    --snapshot-parent "$out/runtime" \
    --sha256-file "$build_dir/executable.sha256" \
    --read-path "$run_root/inputs" \
    --write-dir "$out" --execute-path "$build_dir/klps_anal_prep.exe" \
    "$build_dir/klps_anal_prep.exe" -- 262281200 \
    > "$out/launcher.log" 2>&1
```

After both arms, repeat `sha256sum -c` on the input copy and preserve each
arm's input-check log. A failed hash check rejects both outputs from that arm.

The prior successful research publication used local `/var/tmp`; the earlier
Lustre `OutputTransaction` attempt failed its atomic no-replace rename and
created no published generation. Publish a new run only on a filesystem that
passes `preflight_publication_filesystem`; keep failed output generations
separate and preserve their receipts. Even a successful transaction binds
bytes and declared lineage, not physical validity.

## Current actual-case execution

- The historical NE57 LAPSPREP BASE/candidate pair, readback, retained 122-file
  input copy, 391-entry build-input list, and 41-entry runtime list are
  inspectable and hash-verifiable.
- The clean source-442 replay completed on 2026-10-06 in
  `/var/tmp/cloud_bal_pr60_ne57_20261006`. Pinned Intel O0 built in fresh
  external scratch; 391 recorded build inputs, 41 runtime entries and the
  read-only 122-file input copy passed their hash guards. Both producer arms
  completed and the closed WPS/SHADOW snapshot passed the full pair verifier.
  Source status remained clean through the final guard. The transaction was
  not committed or published.
- All three new product hashes match the retained source-901 generation:
  BASE WPS, candidate WPS and candidate SHADOW are byte-identical. This links
  candidate content to the retained native trace; it does not turn that trace
  into a source-442 native execution or establish native compiler closure.
  [The replay receipt](evidence/pr60_current_lapsprep.json) records source,
  inputs, executable, runtime, product and readback identities. The producer
  still runs `balance=false` and supplies no optional component contract. It
  is a research candidate, not an accepted coupled physical solution.
- Full original upstream generation is still blocked pending its declared
  producer chain and authority. LAPSPREP replay alone does not recreate or
  authorize every upstream input.
- The retained source-901 candidate now has a diagnostic WPS -> metgrid ->
  real -> first-KDM6 trace and a completed 20-second native run. The cadence
  repeat reproduces the same input/executable/raw-trace hashes and finds
  33,617 nonfinite reflectivity cells, exactly where post-call rain mass is
  positive and rain number is zero. See
  [the native report](PR59_CURRENT12_NATIVE_KDM6_FIRST_CALL_20261006.md).
  This closes first-call capture for one active tile; it fails native
  reflectivity acceptance and does not close moment initialization,
  source/boundary conservation, joint optimality, or forecast acceptance.

## Joint-state and native gates

- [ ] Freeze one candidate contract over the same NE57 background, observations,
  grid, cycle, support masks, units, wind frame, pressure inventory, and
  configuration. Keep BASE, HYDRO-only, and COUPLED runs under the same source,
  build, runtime, inputs, and model settings.
- [ ] Record independent observation values/operators/errors and permitted
  increments. Report observation fit and coverage by variable and level;
  missing observations do not authorize filling state cells.
- [ ] Recompute pressure geometry, dry-air mass, vapor and each hydrometeor
  mass, mixture enthalpy, continuity, geostrophic diagnostics, and applicable
  hydrostatic thickness on the final stored candidate. Separate measurement
  support, evaluation domain, and change authority. Treat unassessed layers as
  unassessed, not zero residual.
- [ ] Close independently sourced analysis increments and physical boundary
  fluxes for dry air, each water species, and energy. Do not count a candidate
  endpoint change as its own source term. State omitted pressure work,
  kinetic/gravitational terms, and boundary energy before describing any
  energy budget as closed.
- [ ] Bind the candidate's WPS, metgrid and real products to one source/grid/time
  identity. Read back pressure/eta mapping, soil/surface state, QV and
  hydrometeor species, units, dry-mass basis, wind orientation, vertical
  motion conversion, masks, and all changed fields. Show that the exact
  read-back fields enter native initialization.
- [ ] Before the first KDM6 call, log each native Q/N field's value, units,
  source, initializer, and mass/volume denominator for BASE, HYDRO, and
  COUPLED. Trace QNCCN and QNCLOUD/QNICE/QNRAIN/QIB individually. The retained
  profile configures a source-bound QNCCN initializer but has no implicit
  initializer for QNCLOUD/QNICE/QNRAIN/QIB. An earlier unguarded source probe
  divided by zero QIB before the density clamp. The selected traced source
  explicitly uses `rhox=900` for its zero-volume branch, then reconstructs
  QIB; that numerical protection is not a physical prior. The separate
  `rho_mid=400` branch is not the zero-volume fallback.
- [ ] For each setting, retain native states at t0 and through t+60 min,
  including the first-call trace, every model output interval, and at least
  each 10-minute checkpoint. Record timestep-level fatal/nonfinite counts,
  water/energy budgets with boundary terms, pressure/geopotential and
  temperature tendencies, cloud/rain/ice/snow/graupel number and mass,
  precipitation, surface fluxes, vertical motion, and observation fit.
- [ ] Define acceptance ranges before comparing runs. Check physical
  positivity and conservation with declared numerical and observational
  uncertainty; compare BASE/HYDRO/COUPLED initial adjustment and 0–60 min
  evolution for stability, precipitation/cloud structure, surface response,
  and forecast skill. Do not impose universal zero divergence, zero
  acceleration, or exact hydrostatic/geostrophic balance on every regime.
- [ ] Have independent reviewers reproduce the source/input/build/native
  bindings and scientific diagnostics. Keep research status until all physical,
  native, boundary, and operational gates have explicit dispositions.

## Graph and evidence limit

Graph navigation located the actual-source input contract, LAPSPREP build
path, writer mapping, and research transaction path. It does not establish
runtime execution or meteorological validity. After each completed batch,
incrementally update the Cloud-BAL graph and dated KG audit. Keep this Cloud-BAL snapshot dated independently from the
KLAPS50 snapshot; report extraction limits and graph deltas with any graph
freshness claim.
