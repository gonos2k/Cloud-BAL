# Approved WPS output → actual metgrid reader

The input is the unchanged four-case PR21 cold-LAPSPREP handoff: producer O0/O2,
base/alternate Lambert geometry, at `2023-05-18_03:33:20.0000`. PR19 numerical,
PR20 geometry, and PR21 observation-window/exact-time results retain their
separate scoped status. The user-supplied independent GNU function tests are
external review evidence, not additional local Intel executions.

This test calls the unmodified WPS `read_met_init`, `read_next_met_field`, and
`read_met_close` routines. It builds their actual dependencies, including serial
parallel initialization and the original C logging routine; there are no reader
or dependency stubs. The fixed upstream source is
[WPS v4.6.0, commit 335c76a](https://github.com/wrf-model/WPS/tree/335c76a111f84503e8b963abaf273ea8053645bb).
`tests/wps_reader_sources.sha256` supplies the same ordered source list for
compilation and hash verification. The upstream source is an external test
prerequisite, not vendored or downloaded automatically by the runner.

The Fortran comparison reads the approved intermediate record independently and
checks the actual reader's returned `met_data`: exact timestamp, field names,
levels, units, grid dimensions, wind basis, Lambert metadata, and float32 slab
values. It permits only the source-declared transformations: `HGT` becomes `GHT`,
Lambert format code 3 becomes `PROJ_LC`, and `DX/DY` change from km to m under
`_METGRID`. The radius stays in the reader's km representation. `SWCORNER`
becomes `starti=startj=1`. Candidate thermodynamic formulas remain in the prior
Fortran oracle; they are not duplicated in Python.

The runner requires the caller's expected PR21 manifest SHA256, verifies every
listed artifact, and copies each approved WPS file without changing any byte.
The input copy is named `LAPS:2023-05-18_03:33:20` for the exact consumer lookup
key. Python handles only hashes, staging, process execution, byte truncation,
and receipts. Pinned ifx/icx O0/O2 builds run in new scratch directories.

The approved PR21 artifacts are little endian. Both the upstream reader and
independent Fortran comparison are explicitly compiled with `-convert
little_endian`; `F_UFMTENDIAN` is unset to prevent an inherited override. The
initial big endian test configuration rejected the version and is retained as a
failed attempt. The original input bytes were not rewritten. Retained 2026 full
metgrid examples are big endian, so byte-order configuration is another explicit
prerequisite for the eventual installed-binary handoff.

## Reproduction

From an isolated Cloud-BAL checkout with the pinned Intel installation:

```bash
git clone --depth 1 --branch v4.6.0 https://github.com/wrf-model/WPS.git ../WPS
bash tests/run_qbal_metgrid_reader_tests.sh \
  ../WPS /path/to/pr21/run_time_final \
  170c3c8027af34e1fed2499ac38d7a4fa78934bd64f7236cf610d97421a601f0 \
  /new/scratch/metgrid_reader
```

An existing output root is rejected. The original writer and LAPSPREP artifacts
are reused, not rebuilt by this command. Their approved numerical/geometry
checks remain bound through the manifest and hashes.

## Full metgrid time configuration remains a separate gate

The upstream `process_domain_module.F` lines 141–151 chooses the filename date
precision from `interval_seconds`: an hour multiple uses 13 characters, a minute
multiple 16, otherwise 19. Lines 882–902 construct the output time from that
lookup date. Consequently, a precise intermediate header alone is insufficient
to certify the full metgrid output time. A later single-time second-resolution
case must configure its lookup/output time accordingly and inspect actual
`met_em` and `wrfinput` timestamps. This test calls the real reader at the
19-character lookup key; it does not execute that full domain-processing loop.

The installed KLFS metgrid executable's provenance is not inferred from this
new official-source build. Existing 2026-08-16 metgrid/real receipts describe a
different input case; their ancillary products cannot be relabelled as inputs
for the 2023-05-18 synthetic approved candidate.

## Remaining scope

This is reader-entry evidence before interpolation, not geographic remapping,
full metgrid/real execution, native startup/halo, or the final consumed state.
The five WPS fields do not carry omega. Separate omega/W conversion and final
native boundary/metric checks remain required. Actual observation availability,
scan-time representation, Barnes reuse, mass/thermodynamic closure, initial
response and forecast effects remain OPEN.

## Source tracing for the following integrations

Read-only inspection of the existing radar path found a separate policy boundary:
`klaps-v5.0_/src/wind/main_sub.f` sets `i4_tol=900`, while `get_multiradar_vel`
in `src/lib/getradar.f` retains selected file times in `i4time_radar_a`.
`src/wind/windanal.f` assigns `obs_radar(i)%i4time=i4time` before both Barnes
passes. Thus canonical LOS's ±300-second gate is not evidence that this legacy
collector uses the same window or that Barnes retains original observation age.
The next bridge needs per-radar selected time and post-QC source-cell membership
through derived U/V and Barnes rows. No receive-time evidence was established.

The retained raw CF/Radial sample is a different May 2026 case: seven files,
only one valid VELH cell in SDS and none in the other six according to its
`baseline/20260818_rdr_input/input-manifest.md`. It cannot establish useful
multi-Doppler geometry for this approved candidate. File naming and time-coverage
metadata also disagree for two radars; interpretation must precede use as an
analysis-time source. These are inspected sample limitations, not a new failure
of PR21's canonical contract.

The existing native-W consumer requires exact 19-character `Times` agreement on
`wrfinput_d01`; that contract alone does not deliver pressure omega to native W.
A prepared native seed, stagger/metric conversion, final boundary/halo treatment,
and observed consumed W/WW remain separate prerequisites.

## Local execution evidence

Pinned Intel O0/O2 reader builds each read all four approved producer/geometry
files: **8 normal executions, 33 records each**, with exact analysis seconds and
all declared metadata/array comparisons passing. **14 negative executions**
failed with their designated `FAIL:` text and nonzero exit status: wrong expected
second, lost seconds, missing lookup file, truncated slab, partial trailing
record, a copied reader that zeroes seconds, and a copied reader that changes
one returned slab cell. The last two are deliberate source mutants, not changes
to the official-source normal builds. Rejection is the comparison driver's
contract; it does not mean the upstream reader independently validates every
one of these conditions.

The parent rechecked all **78 artifact hashes**, test-source hashes, unchanged
original/staged inputs, fresh build cwd, and **12 recorded compiler commands per
optimization level**. O0 retains `-check all`; O2 uses the pinned reproduction
profile without it. Manifest:
`scratch/pr21_native_20260916/reader_final/manifest.json`, SHA256
`61690b6a911411d047ff2c774f3af032287ab468ecaa394d73c583f3ce456928`.
Parent receipt: `scratch/pr21_native_20260916/reader_parent_verification.json`.
The earlier wrong-endian attempt is in `reader_run_1.log`; it is not counted as
a successful handoff. No production source was changed, so the validation run
is this focused integration suite, not a new full-unit or native-model PASS.
