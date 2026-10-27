# CP02 first-hour native trace scope (2026-10-27)

This note traces the canonical 20 SE lost-hit cells in the archived CP02 OFF/HYDRO/LIQUID case. It records saved model state; it does not assign causality.

## Archived artifacts and mapping

The authoritative six-hour case is `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914/{off,hydro,liquid}/run/`. Each arm retains native WRF histories at `2026-08-16_12:00:00` and hourly through `18:00:00`; each history is 328,253,340 bytes. `scratch/cp02_six_hour_20260914/RESULT.json` pins SHA-256 identities for the histories; `ONE_HOUR_REPRODUCTION.json` independently confirms that the extended 13 UTC `RAINC`, `RAINNC`, and `RAINSH` match the retained one-hour files exactly in all three arms.

Selector: `reference >= 5 mm` and `OFF >= 5 mm` and (`HYDRO < 5 mm` or `LIQUID < 5 mm`), evaluated from the canonical `hour_13_arrays.npz`. This selects 20 of the 3,688 source-bound comparison cells, spanning 34.8394–35.6069 N and 128.5662–129.1609 E. The source mapping follows `scratch/cp02_six_hour_20260914/compare_six_hour_csi.py`: ODAM target crop 253×149, native WRF mass grid 282×234, source-corner one-cell halo and curvilinear bilinear inversion, with no extrapolation. The maximum coordinate residual for the full mask is 2.84e-14 degrees. Lost-hit stencil lower-left indices are WRF `(j=72..89, i=162..172)` (zero-based). The mapping CSV preserves `losthit_rank`, the original 3,688-cell vector position, the target flat index, and each of the four native corner indices and weights; the profile CSV stores the resulting bilinearly interpolated state.

## Extracted state

[Reproducible extractor](evidence/precip_transitions_20261027/native_trace/extract_cp02_losthits.py) writes the [4,680-row profile CSV](evidence/precip_transitions_20261027/native_trace/final-v2/losthit_native_profiles.csv), a [point-to-stencil mapping CSV](evidence/precip_transitions_20261027/native_trace/final-v2/losthit_mapping.csv), a per-point [precipitation cross-check CSV](evidence/precip_transitions_20261027/native_trace/final-v2/precipitation_crosscheck.csv), and a [full-level mean-profile figure](evidence/precip_transitions_20261027/native_trace/final-v2/losthit_mean_profiles.png). The [receipt](evidence/precip_transitions_20261027/native_trace/final-v2/extraction_receipt.json) records input hashes, archived history identities, mapping details, and validation. The extractor checks the six-hour run's recorded SHA-256 values, valid times, grid and field dimensions, coordinate consistency, and complete finite unmasked thermodynamic fields. Output creation is exclusive; pass `--output-dir` for each new extraction. It reads only the archived 12:00 and 13:00 histories for the three arms. Saved state fields include native `T`, `P`, `PB`, `QVAPOR`, `QCLOUD`, `QRAIN`, `QICE`, `QSNOW`, and `QGRAUP` across all 39 mass levels.

`T` is WRF perturbation potential temperature, not temperature. `T_K_diagnostic` is explicitly a derived quantity computed at each of the four native stencil corners as `(T+300) * ((P+PB)/100000)^(287.05/1004.5)`, then bilinearly interpolated. It is a diagnostic conversion with stated constants, not a claim of exact equivalence to WRF's runtime thermodynamic routine. Pressure is interpolated from `P+PB`; water species remain in native kg/kg mixing-ratio units.

As a cross-check of the point selector, the extractor calls the archived comparison's precipitation reader, separate float64 accumulator sum, crop and remap operations, then differences the 12:00/13:00 cumulative fields. `numpy.array_equal` is required: all 20 values for each arm exactly equal canonical `hour_13_arrays.npz` (max absolute difference 0 mm). An exploratory implementation that added the two float32 accumulators before promoting to float64 produced discrepancies up to 1.21e-7 mm. The archived operator promotes each component and adds them in float64; the accepted extraction follows that exact operation, and no tolerance is used for the final check.

Across these 20 cells and native levels `bottom_top k=0..10` only, spatial/vertical means from the diagnostic profiles are:

| Arm | T (K), 12→13 UTC | QVAPOR (g/kg), 12→13 UTC | QCLOUD (g/kg), 12→13 UTC | QRAIN (g/kg), 12→13 UTC |
|---|---:|---:|---:|---:|
| OFF | 292.760→293.124 | 15.875→16.151 | 0.387→0.118 | 0.175→0.135 |
| HYDRO | 292.752→293.114 | 15.875→16.153 | 0.387→0.129 | 0.118→0.126 |
| LIQUID | 292.625→293.115 | 15.928→16.154 | 0.334→0.130 | 0.118→0.122 |

These are equal-weight means over cell×level samples at `k=0..10`, included only as a compact summary and not as a physically selected layer or a mass-weighted budget. The figure reports unweighted means over the full 39 mass levels for temperature, QVAPOR, QCLOUD and QRAIN; its vertical axis is mean pressure across the 20 mapped cells at each level. No column-mass weighting is applied. Ice, snow and graupel are retained in the full per-cell CSV.

## Scope limits

The archived histories provide state snapshots, winds/vertical velocity, and precipitation accumulators, but no microphysics process-rate tendencies or conversion budgets. They cannot identify which process made a cell miss. The three initializations differ in multiple native fields, and their one-hour precipitation response is not an isolated thermodynamic or omega experiment; the CP02 precision review records that initial W is shared. This trace establishes that relevant CP02 histories exist and provides the actual native first-hour state on the lost-hit stencil. It does not establish causal attribution, a general forecast effect, or CP02 completion.
