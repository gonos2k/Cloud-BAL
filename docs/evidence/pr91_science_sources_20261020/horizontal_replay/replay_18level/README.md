# LAPS QC horizontal replay, 18 pressure levels

This bundle records the source-bound WPS horizontal replay for the original PR78 support columns, restricted to QC. The LAPS WPS v5 file has 21 QC records; the support's k0=3..20 maps to 95,000 down to 10,000 Pa. For each of the 16 target mass-grid cells touched by the 3×3 source support, direct WPS `interp_sequence('four_pt+average_4pt')` was evaluated against the corresponding exact met_em pressure level: 288/288 REAL32 predictions match bitwise.

The WPS source projection uses the preserved LAPS v5 header radius `6371.22900390625 km`, passed to `push_source_projection` as `6371229.00390625 m`. The separate `grid_rows_288_wrong_radius.f90` run uses 6,370,000 m as an intentional negative control: it matches only 65/288 values; at 95,000 Pa and target `(133,15)` it predicts `39A0D267` instead of `39A3C6D5`.

`direct_interp_288.json` contains all 288 level/target comparisons, all 16 target fractional coordinates and 64 four-point corner weights, the 36 links to the original 3×3 source cells, and the inverse target support for each source cell. A separate direct `lltoxy` scan of all 65,988 met_em mass-grid coordinates independently enumerates the same 16 supported target columns and 36 nonzero links; all coefficient HEX values match the persisted rows. `laps_qc_horizontal_rows.json` is the concise indexed source-link record. `qc_levels.txt.gz` preserves the extracted source QC arrays from all 21 records (all values originate from the source file identified by SHA-256 in the JSON); `targets_288.txt` preserves the matched target coordinates and met_em QC values. The compressed slab and target grid coordinates let a reviewer replay both the WPS operator and the global inverse-support scan without copying the 60 MB source intermediate or 140 MB met_em file.

## Scope

This validates the horizontal QC source component at this input, time, and these pressure levels. It does not establish that QC alone selected each final met_em value, map other fields with their different WPS methods or masks, or derive the real.exe pressure-to-hybrid influence into native eta cells. No WPS or real.exe run was performed here.

## Reproduction

`commands.sh` copies this entire evidence bundle to the requested scratch directory and runs the build/replay there; regenerated JSON is written only to that scratch copy. It sources the archived `toolchain/intel_toolchain.sh`, whose hash and the exact ifx binary hash are pinned in `manifest.json`. It freshly compiles `interp_module.F`, `llxy_module.F`, and `module_map_utils.F`; the small WPS support objects (debug, parallel, I/O, bitarray, queue) are linked from the preserved PR82 build and their hashes are recorded in `manifest.json`. Decompress `qc_levels.txt.gz` before running `grid_rows_288`. The target row file is keyed to the preserved met_em hash and can be regenerated with `make_targets.py` when that met_em file is available.
