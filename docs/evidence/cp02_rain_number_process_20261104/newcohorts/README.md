# Deterministic +3h rain process cohorts

These nine cells are diagnostic locations for comparing the current B1 configuration (`IMPROVED_BG_FIXED`) with the `B1_RAIN_NUMBER_PRIOR` candidate. The 26-condition evaluation plan, paired 3,688-cell samples, and full-array scores remain the performance evidence. The point table does not define a new score subset or select a winner.

`P01`, `P02`, and `FA03` keep their existing RN1 sample indices and identities. The six new identifiers start with `H3_` to distinguish them from prior lead-specific cohorts. Weak observations (0.1–1 mm) and moderate observations (1–5 mm) are labeled separately. The +3h set contains two weak hit-loss examples, one moderate-rain hit loss at 0.5 mm, a new 0.1 mm false alarm, a 5 mm false alarm at a 2.7 mm observation, and one retained 5 mm hit.

Selection uses fixed eligibility rules in `selected_points.csv` and deterministic maximum paired-change ordering with RN1 flat index as tie-break. `H3_L05` uses index 575: eligible index 574 ranks first but overlaps `H3_L01` at native cell (81,139), so it is skipped. Index 575 is the next eligible point in descending absolute paired change, with no corner collision. The selector records the disjoint-stencil filter and flat-index tie-break, and the superseded index-2666 draft is retained under `attempts/prefreeze_fixed_indices/`.

`point_corners.csv` contains the four bilinear source WRF corners for each analysis point, with exact weights and both zero-based RN1/WRF coordinates and Fortran one-based WRF indices. `unique_global_corners.csv` assigns each of the 36 distinct global WRF cells a stable ID for native instrumentation. `point_transitions.csv` tracks ORIGINAL, current B1, and candidate forecast categories at all six leads and six thresholds for these points. It does not replace the full-sample scoring tables.

Mapping used the actual candidate-run 12 UTC WRF history and the archived curvilinear mapper through the existing CP02 mapping tool. The history grid is 234×282×39; the real interior is 232×280. `mapping_receipt.json` binds all six analysis NPZs, mapping code, mapper, coordinate file, history file, and maximum coordinate reconstruction residual.

The independently reviewed frozen inputs have SHA-256 `aa5da1ef6cdb8773addb139ef4cc385d3ea9e2b9d490368f79fd77086bca4b1b` for `point_corners.csv` and `169adba4177e9efcd11d54603a4ce451593c24927b6f8e0a93a2d16480eeddc3` for `unique_global_corners.csv`. The review verified selection ranking, four normalized weights per point, 36 unique cells and history dimensions before native instrumentation. The earlier receipt with reversed geometry metadata is preserved under `attempts/prefreeze_axis_metadata/`.

At P01, the 0.1 mm threshold changes from a B1 miss to a candidate hit at +2h, then from a B1 hit to a candidate miss at +3h. This is a same-location timing diagnostic; it does not establish aggregate performance.
