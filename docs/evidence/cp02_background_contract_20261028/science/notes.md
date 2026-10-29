# CP02 background and radar capture audit

Read-only audit of archived CP02 artifacts; no model replay, forecast, Fortran compile, or edits to the maintained workspace. The standalone decoder is [recompute.py](recompute.py), and its output is [results.json](results.json). It decodes captured GDB array bytes, reads the archived payload and shadow NetCDFs, and cross-checks all 440 preserved profile CSV rows without calling the saved analyzer. Input hashes and byte sizes are in `results.json`.

## Quality × phase candidate/background ratios

The 190 valid-reflectivity rows are grouped by captured post-diagnose phase code (1 rain, 2 snow) and archived reflectivity quality integer (0 or 32/`0x20`). Ratio is the sum of the final published candidate species divided by the sum of its background species over the group. Candidate final values are REAL32 from the archived shadow NetCDF; the REAL64 captured publish work-array ratio is also shown because it differs slightly after output storage rounding.

| Species / reflectivity quality | Count | Sum background (kg/kg) | Sum final REAL32 candidate (kg/kg) | Final candidate/background | REAL64 work-array ratio |
|---|---:|---:|---:|---:|---:|
| Rain / 0 | 43 | 0.00956236585444 | 0.00655271038704 | 0.6852603725 | 0.6852603723 |
| Rain / 32 (`0x20`) | 111 | 0.02480377073880 | 0.01694101236171 | 0.6830014896 | 0.6830014874 |
| Snow / 0 | 32 | 0.01877787463309 | 0.00256170933517 | 0.1364216870 | 0.1364216867 |
| Snow / 32 (`0x20`) | 4 | 0.00388418376679 | 0.00051641591563 | 0.1329535230 | 0.1329535259 |

The 440 preserved profile CSV rows cross-check exactly for payload/shadow background values and captured REAL64 publish work arrays; final REAL32 NetCDF candidate values are reported separately because output storage rounds them. In the 250 rows where the captured `radar_observed` flag is false, background rain, background snow, final candidate rain, and final candidate snow are all zero. Those rows therefore do not test preservation of a nonzero background.

The reflectivity quality integer `0x20` is separate from the `phase_uncertain` field; the capture records `phase_uncertain=false` at all 190 observed locations. No historical QC label or policy is inferred from the bit value.

## Full-grid inventory and verification-array overlap limits

Across the archived 22×283×235 payload/shadow grid, 27,762 rain and 60,425 snow cells have positive background species where `radar_reflectivity_valid=0`; all are above ground. At those invalid-mask cells the stored candidate equals background exactly for each species. The output includes a few coordinates and values as a shortlist.

This is a **reflectivity-validity proxy**, not a reconstruction of the complete binary's `radar_observed` predicate or an observation-coverage finding. The preserved 3,688-point hour-13 arrays contain 55 kept hits for each candidate, 19 lost hits each, and 13 HYDRO / 16 LIQUID removed false alarms. The bundle does not preserve all 3,688 WRF bilinear source stencils; only the 20-point lost-hit stencil is retained. I therefore do not join those forecast transition categories to the native invalid-positive inventory or claim an overlap.

## Historical source and formula evidence

The archived payload and shadow `background_rain`/`background_snow` arrays match exactly over the full grid, and both NetCDFs declare `kg kg-1 dryair`. The stored lineage describes an upstream LAPSPREP path that reads radar hydrometeor concentrations in `kg m-3`, applies validity/negative clipping and `hydrometeor_scale`, then divides by dry-air density to produce mixing ratios. It records `CAP_POLICY=TRANSFER`, rain/snow fraction 1, and `GRID_SCALE=NONE`. This is a source-path description, not a demonstrated first differing operation.

Exact historical source is only partially recovered. The LAPSPREP build input hash is `f69735e8a4e006db92930e3119b594fb8a9d5d7fbf41673a5e60ab73ae749579`; the bounded search found no exact source match among 61 basename candidates or 8 Git revisions. The column-physics hash is `f7d640bbee19a128af6556f16e346e9574d1845997d77eab48e844109f14e17d`; no exact source match was found among 74 basename candidates or 17 revisions. The pipeline hash is `188a2e1b9f467c6fa28e8f317e493975ddaf8dfbf5100398867666bbb6f2b478`; 14 archived scratch copies have that exact content hash, but none is tied to the CP02 executable's link step and no matching Git revision was identified among 23. Thus the exact LAPSPREP conversion coefficient and source expression remain unestablished. The archived payload starts at mixing ratio, so it cannot independently recover the preceding concentration-to-mixing-ratio calculation.

Separately, the old binary's archived 190 allocator calls support the numeric identity

`total = reference_mass_concentration × (zlinear / 1000)^0.55 / rho_d`.

`reference_mass_concentration=1e-4` was decoded from the binary's captured runtime configuration; the captured `rho_d` return and total were compared for each sample; pressure, temperature, and vapor inputs are preserved alongside those calls. All 190 float64 residuals are exactly zero. This supports the sampled allocator relation, not the historical LAPSPREP background-generation equation; the exponent and scale are empirically confirmed by output and are not elevated to source-level proof while the relevant old source is unavailable.

## Reproduction and evidence hashes

```bash
/var/tmp/pr108_portable_env_20261026/bin/python /var/tmp/cp02-background-science-20261028/recompute.py
```

The JSON report records its own script hash plus hashes for the capture, both profile CSVs, lineage/source-search records, payload/shadow NetCDFs, and the 3,688-cell NPZ. It also records the script's scoped limitations and does not claim model or scientific validation.
