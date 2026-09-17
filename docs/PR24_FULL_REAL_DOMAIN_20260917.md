# Full-domain real-data initialization replay

## Applied scope

This run uses the already prepared NE57 real-data case at
`2026-08-16_13:00:00`. It does not create synthetic meteorological/static inputs,
extract a subdomain, or combine this case with the earlier 2023 synthetic case.
The existing whole-domain LAPS analysis is reused; the analysis programs are
not rerun in this stage.

The source LAPS log records 235 × 283 horizontal points and 22 slots for
HT/T3/U3/V3/RH/SH. Its inputs are the existing `lt1`, `lw3`, `lh3`, `lsx`, and
`lq3` products under `scratch/upstream13.Sfb68E`. The supplied WPS product is
`scratch/actual_thermo_root_run.SuqsSJ/FILE:2026-08-16_13`, SHA256
`a1cd9870a90454134ae6304f29d3b60aa70306fbecd5506f5e815875c86384ca`.
It is a historical real-data-derived research candidate, not an unmodified
operational analysis or a newly approved Cloud-BAL balance candidate.

The complete prepared inputs include KLBG background, soil temperature and
moisture, SST, OML, RCHA, TAVGSFC, actual geogrid, and the native parameter tables.
The original 34-entry manifest SHA256 is
`2e6fc227f588eac48ebde0976f2a70d5e36157154bcf5b7177c9f969a861e831`.
Every entry is checked before and after execution. Source and prior outputs are
not overwritten. The namelist's table directory alone is relocated to the new
private stage; time, physics, domain, vertical configuration and input cadence
are retained.

## What initialization was applied

The actual sequence is the existing 3-D LAPS product plus the prepared background
and surface inputs → full metgrid → actual `real.exe` → new `wrfinput_d01`.
Metgrid processes LAPS TT/UU/VV/QV/GHT through all supplied levels, including
5000–100000 Pa and the separate surface slot. The resulting mass grid is
234 × 282 with 21 metgrid levels. Native U is 235 × 282 × 39, V is
234 × 283 × 39, and W is 234 × 282 × 40. T, P/PB, QVAPOR and hydrometeors
use 39 mass levels; PH/PHB use 40 interfaces. These are the complete prepared
domain dimensions, not a smaller test domain.

**Existing 3-D analysis reuse and real initialization are applied. Cloud-BAL
wind/omega balance initialization is not established by this replay.**
The producer log explicitly says `BALANCE=F`. It declares the historical
`LIQUID_RADAR_RH1_NOT_KDM6` and `RADAR_COLUMNS_FIXED_SURFACE` experiments.
The later exact-replay report records zero wind and omega increments and
`dynamic_balance_decision=NOT_AUTHORIZED`. Its numerical replay validity does
not constitute dynamic-balance or operational approval. The earlier local
`validation.json` rejection and later exact-replay validation are distinct
historical records, not validation rerun here.

Existing processing also contains declared fallback behavior: the LAPS log
records 168111 below-ground SH surface extrapolations, and real reports a
default silty-clay-loam category at 362 of 65988 mass-grid positions. No new
synthetic fixture was supplied, but “real data” does not mean these legacy
interpolation/fallback operations were absent.

## Actual table selection

The prepared namelist selects a directory whose `METGRID.TBL` symlink resolves
to `METGRID.TBL.ARW.OML.KWW`. The historical manifest had pinned the neighboring
`METGRID.TBL.ARW.OML` file instead. This replay additionally pins the **actually
selected KWW table**, SHA256
`44f1a43af35441957d0bef3a6220831aad1cf56ebc765d64d08e20f439a63b44`.
The KWW table includes CHARNOCK handling. An initial OML-table execution completed
both programs but differed from the prepared outputs, including a missing
`FLAG_CHARNOCK`; it is a diagnostic run, not accepted replay evidence.

## Execution and validation

The installed metgrid and real executables are prebuilt, identified by their
hashes in the prepared manifest. They are executed under the pinned Intel
profile. This is not a fresh O0/O2 build of those programs or proof of complete
source/build provenance. The original prepared case has one analysis time;
its `interval_seconds=10800` is retained. This is not a multi-time cadence test.

The corrected whole-domain replay produces complete-file byte identity:

| New output | SHA256 (same as prepared reference) |
| --- | --- |
| `met_em.d01.2026-08-16_13:00:00.nc` | `bdd5484c916f7b5ec7281b1a2ff41340e33936e87fce059d70052a3d40b1c885` |
| `real/wrfinput_d01` | `f0ccee31f6f7214c9d7b5ccf19e0ae55d9fe43751e0fcffbcaedfc6080a052e1` |

The final run is `scratch/pr23_real_20260917/full_real_final_r2` in the maintained
Cloud-BAL workspace. Its execution manifest SHA256 is
`a958422bcab9e9a73d585160ae6cde7d9a57416ecc9c742f0104269e950974de`;
the combined validation manifest SHA256 is
`69b8bc5a5b791174b2b6dd750b730114ddd1856c84ce415ba7cbe461cf5a565d`.
All 25 recorded validation artifacts were independently rehashed with no mismatch.
The receipt names the selected KWW table and all 35 effective pinned inputs.

A 144-line Fortran checker validates the exact time, complete domain dimensions,
and mandatory 3-D layouts, then compares every byte of both files in bounded
chunks, including metadata and all field values. It passes under pinned Intel
O0 and O2, compiled in fresh scratch directories with actual argument arrays
recorded. O0 retains `-check all`; O2 has no optimization-disabling override.
Those two profiles describe the checker, not two new builds of metgrid/real.
No manufactured input, subdomain fixture or mutated meteorological test file is
used for this validation. The byte reference is the prepared historical output,
not an independent physical oracle.

This proves reproducible initialization from this prepared input set. It is not
an independent physical reference, a fresh 3-D analysis, native startup/halo
consumption, an omega/W handoff, mass/thermodynamic closure, or forecast evidence.
`wrf.exe` is not invoked. Those stages remain open.

## Reproduction

```sh
bash tests/run_real_full_domain.sh /path/to/native_handoff_stage.ymn6MM /path/to/new/run
```

The runner requires the existing host inputs and rejects a reused output
directory or mismatched input hashes. It never creates missing meteorological
inputs. All numerical field checking belongs in Fortran; Python handles
staging, process execution, hashes and receipts.
