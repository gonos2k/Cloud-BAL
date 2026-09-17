# Full metgrid handoff of the approved 2023 synthetic case

## Contract

This stage connects the approved cold LAPSPREP output to the complete serial WPS
metgrid program, including interpolation, wind rotation, and NetCDF output.
The source WPS v4.6.0 commit is
`335c76a111f84503e8b963abaf273ea8053645bb`. The two-file exact-time patch is
applied to a fresh scratch copy; the reference checkout is not edited.

The source analysis time is `2023-05-18_03:33:20`. The single-time namelist uses
that exact start/end and retains `interval_seconds=300`. It does not change the
input cadence to one second to obtain a longer filename. The patch retains
legacy abbreviated filenames when the represented time is exactly aligned;
nonzero seconds require the full 19-character key.

Observation acceptance remains ±300 seconds, inclusive. It is a different
contract from the exact analysis time checked here.

## Input and target

The existing LAPSPREP manifest has SHA256
`170c3c8027af34e1fed2499ac38d7a4fa78934bd64f7236cf610d97421a601f0`.
Its artifacts are verified before staging. The base O0/O2 WPS files are copied
without changing any bytes, endian, timestamp, or field. Alternate-geometry
files remain part of that earlier receipt; this full-domain test uses only the
base Lambert geometry.

The source is the same all-valid 6×6, four-pressure-level synthetic candidate.
The target is a small synthetic Lambert C-grid inside that source, with 4×4
mass points and 5×4 / 4×5 staggered wind arrays. The source sphere has radius
6371229 m; the target uses the WPS/WRF default 6370000 m. A Fortran program generates
coherent target coordinates and explicitly synthetic static fields. Static
`Times=0000-00-00_00:00:00` is the WRF I/O lookup key, while the analysis WPS
header and resulting `met_em` retain the exact 2023 analysis time. No 2026
native seed, soil product, SST, or observed terrain is borrowed or retimed.

The minimal table declares nearest-neighbor interpolation. U/V retain the real
metgrid wind flags and stagger handling. They are not treated as scalar fields
to bypass rotation. This fixture is not a full operational geogrid or METGRID.TBL.

## Reference checks

All numerical reference calculations and comparisons are Fortran. Python
stages bytes, checks hashes, changes individual output values for negative
controls, invokes programs, and records results.

The reference checks exact `Times` and the start-time attribute, pressure versus
surface slots, target mass/U/V coordinates and projection attributes, dimensions,
field units and staggering, and the five WPS meteorological fields. Scalars use
exact float32 comparison after declared nearest-neighbor selection. Wind values
first undergo nearest-neighbor selection at target U/V faces. Actual metgrid
then rotates that interpolated pair from source-grid to earth coordinates and
from earth to target-grid coordinates. The reference implements both rotations
and the C-grid cross-component averages directly in real64. It does not call
WPS rotation routines. The comparison bound per level is
`64*epsilon(real32)*max(1,maxabs(source_U),maxabs(source_V))` m/s.

An independent tangent-Lambert equation checks every target latitude/longitude,
with `8*epsilon(real32)*max(1,abs(reference_angle))` degrees for the generator's
float32 projection arithmetic. Inverting the actual generated coordinates using
the source sphere verifies the nearest source cell for every mass/U/V point.
Metadata transfer from geogrid to `met_em` itself remains bitwise checked.

The derived PRES values are in Pa under the standard metgrid contract. Its
legacy output `units` attribute is empty (a NUL byte through WRF I/O); the oracle
checks that representation and rejects a changed `hPa` attribute. No Pa label
is claimed to have been added to the upstream writer.

## Validation evidence

**PASS_SCOPED: complete serial metgrid on this bounded synthetic target.**
The final pinned Intel O0/O2 run is
`scratch/pr22_full_metgrid_20260917/run_final_r2/manifest.json` in the maintained
Cloud-BAL workspace, SHA256
`7f7685faf9b1749d8773fddd278a319235fa155bafd2ffe9e7c86124820376c1`.
All 412 recorded artifact hashes were independently rechecked after completion.
Each build records 67 command arrays, including 34 ifx compile/link commands;
the additional generator, oracle, and formatter links have three separate
validation argv records per profile. Actual compiler arguments preserve O0
`-check all`, O2 optimization without that override, and strict floating point.

The 32-source ordered pin list is reused for copying, compiling and linking.
Compilation occurs in fresh `O0/objects` / `O2/objects` directories, separately
from the copied sources. Twenty-one prebuilt/header/module/runtime files are
pinned before the build and checked afterward. Explicit archive paths select
the audited WRF/NetCDF link inputs.

The test matrix consists of four full-program normal runs (two approved base
producer files × two metgrid compiler profiles), twenty designated Fortran
output rejections (time, coordinate, spacing, pressure units, five meteorological
fields and PRES × O0/O2), and two original-time-selection full-program controls.
The latter emit the exact missing minute-key warning and mandatory TT error,
produce no `met_em`, and return zero via the upstream serial plain STOP. They
are recognized by all three conditions, not counted as successful runs or
misrepresented as nonzero-exit rejections.

The formatter tests additionally cover 24 alignment/cadence cases per compiler
profile and two exact timestamps separated by 300 seconds. They are unit tests,
not two independently approved analyses or a multi-time full-domain run.

The full WPS program is compiled here; WRF I/O/frame objects and its KIM NetCDF
libraries are pinned prebuilt dependencies, not newly rebuilt WRF/NetCDF source.
The Fortran generator/oracle uses the separately pinned baseline NetCDF-Fortran
library. Hashes identify these inputs without claiming installed KLFS binary
identity or complete compiler provenance for the prebuilt dependencies.

Exploratory runs exposed missing parallel-module linkage for the generator,
static-file time-key mismatch, incomplete stagger coordinates, and legacy unit
string representation. Moving compilation out of the copied source tree also
exposed `module_internal_header_util.mod`; it is now an explicit pinned input. These were corrected before the final passing run.
Earlier helper/fixture smoke checks and the failed initial `run_final` build
are not acceptance evidence. The final clean
run is the acceptance receipt; exploratory logs remain under `run_probe`.

## Remaining scope

This is a single synthetic analysis time, not a multi-time operational cadence
run. A formatter test for two timestamps does not substitute for that run.
The small all-valid target does not establish terrain/missing-data behavior or
all geographic projections. Full-domain output does not establish `real.exe`,
`wrfinput`, or native consumed-state correctness.

WPS carries five meteorological fields in this path, without omega. Separate
omega/W conversion and native startup/halo preservation remain open. Actual radar
selection times and Barnes lineage must still be connected to the canonical
±300-second validator. Mass, thermodynamic budgets, initial adjustment, and
forecast effects require subsequent native runs on one consistently bound case.

## Reproduction

```sh
bash tests/run_qbal_full_metgrid_tests.sh \
  /path/to/pinned/WPS \
  /path/to/run_time_final \
  170c3c8027af34e1fed2499ac38d7a4fa78934bd64f7236cf610d97421a601f0 \
  /path/to/new/scratch/run
```

The runner requires the recorded host Intel, WRF and NetCDF inputs. It rejects
an existing run directory, an unpinned WPS source or dependency, a changed
approved input, and incomplete result sets. The artifact hashes establish
reproducible file relationships; they are not signed execution attestation.
