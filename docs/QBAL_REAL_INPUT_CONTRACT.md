# QBAL real-input contract

Status: `BLOCKED_PENDING_ORIGINAL_UPSTREAM_REGENERATION`
Authority: the original KLAPS source tree at `../klaps-v5.0_`; final WPS,
`met_em`, `LAPS:*`, `KLBG:*`, and merged `bigfile` products are never inputs.

This document defines one fail-closed contract for every real case.  A field is
not accepted merely because a numerically similar field exists in a downstream
product.  It must come from the original producer named below, at the requested
time, on the 235 x 283 x 22 LAPS pressure grid, with its declared units and
cell-validity information intact.

Supplying a directory with correctly named NetCDF files is deliberately
insufficient.  The current checker never returns READY for a `--pre-qbal-root`:
the missing isolated upstream runner must first emit a hash-pinned generation
manifest that binds every product to its producer executable, source tree,
configuration, complete input closure, command, time, and output hash.  This
keeps renamed, copied, or hard-linked final/bigfile products inadmissible.

## 1. Direct QBAL read closure

The direct read closure comes from
`../klaps-v5.0_/src/balance/qbalpe.f:183-245,263-274` and
`../klaps-v5.0_/src/lib/bgdata/lapsio.f:332-479`.

| Role | Native product and fields | Native units | Native shape | Required behavior |
|---|---|---|---|---|
| pressure coordinate | `static/pressures.nl`: 1100, 1050, ..., 50 hPa | Pa after `get_pres_1d` | 22 levels | exact ordered levels; no 21-to-22-level fill |
| grid and terrain | `static/static.nest7grid`: `LAT`, `LON`, `AVG` and `static/nest7grid.parms` | degree, degree, m | 235 x 283 | exact grid identity and above-ground mask |
| background 3-D | one pinned `fua/wrf/*.fua`: `U3,V3,T3,HT,SH,OM` | m s-1, K, m, kg kg-1, Pa s-1 | record x 22 x 283 x 235 | all six fields from one file; field-by-field fallback is forbidden |
| background surface | matching `fsf/wrf/*.fsf`: `PSF` | Pa | record x 1 x 283 x 235 | same initialization and valid time as FUA |
| analysis thermodynamics | `lt1/<YYJJJHHMM>.lt1`: `HT,T3` | m, K | record x 22 x 283 x 235 | exact analysis time |
| analysis humidity | `lq3/<YYJJJHHMM>.lq3`: `SH` | kg kg-1 | record x 22 x 283 x 235 | exact analysis time; below-ground replication is recorded, not hidden |
| analysis wind | `lw3/<YYJJJHHMM>.lw3`: `U3,V3,OM` | m s-1, m s-1, Pa s-1 | record x 22 x 283 x 235 | exact analysis time and pre-QBAL producer |
| cloud forcing | `lco/<YYJJJHHMM>.lco`: `COM` | Pa s-1 | record x 22 x 283 x 235 | required; absence is a rejection, never a silent zero field |
| analysis surface | `lsx/<YYJJJHHMM>.lsx`: `PS` | Pa | record x 1 x 283 x 235 | exact analysis time |
| runtime control | `time/systime.dat`, `static/background.nl`, `static/balance.nl` | n/a | n/a | pinned case time and configuration hashes |

`lw3/OM` is read at `lapsio.f:469-477` but discarded.  The `omo` cloud target
passed to QBAL is `lco/COM` from `lapsio.f:440-447`.  The original routine
silently replaces a missing COM with zero and later overwrites its status with
the wind-reader status.  Cloud-BAL forbids that behavior: missing or malformed
COM leaves the case `BLOCKED` and preserves the input state unchanged.

The shell comment at
`../ANAL/NE57/SHEL/klps_lc05_anal_all_ajob.csh:260` mentions `lwc` and `lh3`,
but the actual QBAL reader does not read either product.  They remain upstream
and downstream science products, not direct QBAL inputs.  The source call
graph, not the comment, defines this table.

## 2. Original producer chain needed to recreate the direct inputs

The original operational order is fixed by
`../ANAL/NE57/SHEL/klps_lc05_anal_all_ajob.csh:72-284`:

```text
prepared observations + FUA/FSF
  -> radar mosaic                 -> vrz, vrc, vrt
  -> wind analysis               -> lwm, lw3
  -> surface analysis            -> lsx
  -> temperature/height analysis -> lt1
  -> cloud analysis              -> lc3, lcb, lcv, lps
  -> humidity analysis           -> lh3, lh4, lq3
  -> derived-cloud products      -> lcp, lty, lwc, lco, ...
  -> QBAL                        -> balance/{lw3,lt1,lh3,lq3}
  -> LAPSPREP                    -> WPS final product
```

The required executable/config pair for each stage is:

| Stage | Original executable | Required static control | Required native predecessors |
|---|---|---|---|
| radar reflectivity mosaic | `klps_anal_radr.exe` | `radar_mosaic.nl`, `nest7grid.parms`, `pressures.nl` | prepared per-radar grids/raw ingest |
| radar TID mosaic | `klps_anal_radr_tid.exe` | `radar_mosaic_tid.nl` | prepared radar TID |
| wind | `klps_anal_wind_openmp.exe` | `wind.nl` | FUA/FSF and prepared wind observations, including gridded radar radial velocity |
| surface | `klps_anal_lsfc.exe` | `surface_analysis.nl`, `drag_coef.dat` | `lwm` and prepared surface observations |
| temperature/height | `klps_anal_temp.exe` | `temp.nl` | `lsx`, including the original previous-time policy |
| cloud | `klps_anal_clod.exe` | `cloud.nl`, `satellite_lvd.nl`, `goeslib` | `lsx`, `lt1`, `vrc/vrz`, previous `lm2`, satellite inputs |
| humidity | `klps_anal_humd.exe` | `moisture_switch.nl`, `pfcgim8.dat` | `lt1`, `lsx`, `lc3`, humidity observations/background |
| derived/cloud omega | `klps_anal_derv.exe` | `deriv.nl`, `thetae_lut.dat`, `tmlaps_lut.dat` | `lt1`, `lc3`, `lps`, `lcv`, `lsx`, `lw3`, `lh3`, radar |
| balance | `klps_anal_qbal.exe` | `balance.nl`, `background.nl`, grid/pressure static files | the direct read closure in section 1 |

For the preserved operational shell, the legacy cloud-profile environment is
`CT=1.3`, `CU=0.5`, `SC=0.10`, and `ST=0.017`
(`klps_lc05_anal_all_ajob.csh:222-225`).  These values are provenance for the
legacy comparison, not default scientific authority for the new method.
`deriv.nl` sets `MODE_EVAP=0` and `L_BOGUS_RADAR_W=.false.`; the dormant radar
evaporation/bogus-w path stays disabled.

The direct COM producer has a wider read gate than the abbreviated shell
comment.  `laps_deriv.f:128-225`, `laps_deriv_sub.f:438-534`, and
`get_cloud_deriv.f:35-75` require current LT1 `T3/HT`, LH3 `RHL`, LSX
`PS/T/RH/U/V`, exact-time LC3, LCV, LCB, LSO, the pressure/grid description,
and lightning handling; LPS is optional and falls back to cloud-only COM.  A
fresh-generation manifest must capture this complete closure.  File existence
alone is not success because several original writers assign normal status
without checking the write and the main programs can return process status
zero after a required-input failure.

`L_BOGUS_RADAR_W=.false.` does **not** remove all legacy radar influence.  The
cloud analysis fills radar gaps with model first-guess reflectivity, writes the
mixed field as LPS, and `get_cloud_deriv.f:369-390` promotes cloudy cells above
30 dBZ to Cb.  The legacy profile can then extend a convective updraft through
the connected cloud layer.  This is a source-code-supported mechanism for the
reported broad wind change in observation-poor regions.  It is also why LPS is
not an admissible pure-radar input for the candidate.

The legacy profile is resolution dependent: its amplitude is proportional to
cloud depth divided by horizontal grid spacing and it applies a positive
minimum motion to non-clear cloud.  It has no base-path precipitation
downdraft.  These facts are comparison provenance only; the canonical design
keeps cloud type as support/uncertainty and does not give it a deterministic
grid-mean vertical-velocity amplitude without an observed/dynamic driver.

## 3. Candidate radar extension

Radar fields are an explicit extension to the original QBAL closure.  They do
not replace `lco/COM`, `lw3`, or any background field.

| Product | Field | Use | Hard validation |
|---|---|---|---|
| `vrz/<time>.vrz` | `REF` | 3-D S-band mosaic reflectivity | finite, 0 to 100 dBZ, exact time/grid/physical pressure level, and above ground |
| `vrt/<time>.vrt` | `TID` | bright-band/mixed-target quality | finite code 0 to 2; `TID=2` is retained as a quality reason |
| `v01..v04,v06..v11/<time>.vNN` | `VEL` | optional LOS soft constraint/diagnostic | radar identity, beam geometry, uncertainty, usage and observation identity required |
| same `vNN` | `NYQ` | dealias/uncertainty metadata | currently all missing; therefore the existing gridded LOS path is diagnostic only |

The mosaic files contain no wavelength/band attribute.  S-band identity must
come from a versioned, hashed site registry.  It must never be inferred from
the value of `REF`.  The absent `v05` site is not silently substituted.

The 2026-08-16 VRZ files encode no echo as exactly -10 dBZ while
`nest7grid.parms:46` declares `REF_BASE_USEABLE_CMN=0`.  Consequently `-10`
must not create observation support.  Pressure levels in the file are matched
by their physical value; array reversal by position alone is forbidden.

In the prepared VRT files, the retained values are `2` and `-10`; code 2 is a
bright-band marker used by the original temperature analysis as a gated 0 C
pseudo-observation.  It is not a rain/snow/graupel phase label.  The original
job starts the VRZ and VRT mosaics asynchronously but waits only after the
temperature stage, so an isolated replay must insert an explicit VRT-complete
gate before temperature analysis.

## 4. Prepared cases and current readiness

The prepared hourly cases are 2026-08-16 12, 13, 14, and 15 UTC.  For each
case the following source data exist:

- matching 06 UTC-cycle FUA/FSF (`+06`, `+07`, `+08`, `+09` hours),
- QC'd 3-D `vrz` and `vrt`,
- ten S-band gridded radar files `v01..v04,v06..v11`,
- the other prepared observation products used by the upstream analyses, and
- a separately reproduced pre-QBAL `lw3` from the wind-analysis benchmark.

The live prepared root does **not** contain `lsx`, `lt1`, `lc3`, `lcv`, `lps`,
`lh3`, `lq3`, `lwc`, or `lco` for those times.  Therefore all four cases have
the same current state:

```text
PREPARED_SOURCE = AVAILABLE
DIRECT_QBAL_CLOSURE = INCOMPLETE
ORIGINAL_UPSTREAM_REGENERATION = REQUIRED
REAL_QBAL_COMPARISON = BLOCKED
```

No clear-cloud, background-cloud, WPS, `met_em`, or final-bigfile field may be
inserted to make the closure appear complete.  A pair of absent cloud-analysis
fields is absence, not an observed clear sky.

## 5. Deterministic background selection

The original `get_best_fcst` contains a defect at
`../klaps-v5.0_/src/lib/get_maps_lapsgrid.f:396-404`: it assigns
`i4_fcst_time = i4_fcst_time_min` instead of updating
`i4_fcst_time_min`.  When several forecasts share a valid time, file-list
order can select the background.  The new real-case harness must therefore
pin one FUA/FSF pair per case and verify all required variables from that pair
before reading any field.  Per-field fallback to another cycle or to `lga/lgb`
is rejected.

## 6. Forbidden inputs and fail-closed gates

The adapter rejects a path before opening it when its role is a final or
downstream product, including:

- merged `bigfile`, `LAPS:*`, and `KLBG:*`,
- `met_em*.nc`,
- `lapsprep/wps/*`, and
- `balance/*` when constructing a pre-QBAL state.

For every case, one manifest must bind source hash, Intel compiler/runtime and
library hashes, configuration/environment, fixed input hashes, empty candidate
root, stage status, intermediate hashes, and output hashes.  A case is runnable
only if all direct fields have exact valid time, grid, level values, dimensions,
units, finite/range-valid active cells, and source/quality masks.  Missing,
partial, stale, mixed-cycle, below-ground, or undeclared input causes an
unchanged `BLOCKED` result.  There is no numerical proxy or case-specific
fallback.

The final `bigfile` remains a held-out downstream comparison only after both
legacy and candidate chains have independently produced their results from the
same declared pre-QBAL closure.
