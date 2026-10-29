# CP02 first-hour point mapping and initialization controls

This evidence binds a 20-column source-grid selection to the first-hour CP02
precipitation comparison and the original initialization files. It does not
claim a precipitation cause or an observed radar-invalid classification.

## Frozen selection

`capture_points.csv` is the current capture input (SHA-256
`5c842c51422cf144bce81ec2143258e3b54a0de7c85674d91a8194b826e14472`). It
contains 20 unique IDs (`P01`–`P20`) and unique zero-based original source-grid
indices `shadow_j_zero_based` / `shadow_i_zero_based`.

The 16 RN1 comparison points come from the canonical 3,688-point
`hour_13_arrays.npz` sample. Selection uses four points per class:

- lost hit: reference ≥ 5 mm, OFF ≥ 5 mm, and HYDRO or LIQUID < 5 mm;
- retained hit: reference and all three forecasts ≥ 5 mm;
- removed OFF false alarm: reference < 5 mm, OFF ≥ 5 mm, and HYDRO or LIQUID < 5 mm;
- positive reference below 5 mm with all three forecasts below 5 mm.

The remaining four points are two positive-background rain columns and two
positive-background snow columns selected where payload
`radar_reflectivity_valid` is zero. They are external exploratory controls,
not linked to the RN1 verification sample; their nearest-sample distances are
recorded (about 283–467 km). The payload mask is a proxy from the initialization
input, not independent observed radar truth.

The earlier file `capture_points_prelabel_draft.csv` preserves the unused draft
selection. It was not consumed by a runtime capture. Use the corrected frozen
`capture_points.csv` and its hash above.

## Mapping and initialization fields

`wrf_mapping.csv` records the original comparison operator's curvilinear
bilinear mapping from each RN1 point to the four native WRF grid corners and
weights. It uses the archived `compare_six_hour_csi.py` implementation and
explicit XLAT/XLONG coordinates. The maximum coordinate residual for this
mapping is 2.84 × 10⁻¹⁴ degrees.

`source_grid_mapping.csv` separately inverts the point coordinates on the
original payload latitude/longitude grid. Its four corner weights identify
the original source-grid column; the maximum-weight column is listed in the
capture CSV. These are geographic coordinate matches. They do not claim to
reproduce any historical WPS/metgrid interpolation weights or establish
index identity between the WRF and payload grids.

`wrfinput_corner_controls.csv` contains all 39 WRF levels for T, P, PB, QVAPOR,
QCLOUD, QRAIN, QICE, QSNOW and QGRAUP, with each corner value and its bilinear
point value for OFF, HYDRO and LIQUID. `metgrid_corner_controls.csv` separately
records QR and QS across the 21 metgrid levels. WRF and metgrid vertical levels
are kept distinct.

## Reconstruction and limits

`precipitation_reconstruction.csv` remaps 12Z and 13Z RAINC + RAINNC from the
original WRF history files using the archived first-hour operator, differences
the remapped accumulations, and compares the results against the canonical NPZ.
All 48 checks (16 points × 3 arms) are exactly equal, with a maximum error of
0.0 mm. The receipt pins sizes and SHA-256 values before and after for 22 inputs,
including the source NPZ, mapper, payload, shadow file, WRF histories,
initializations, metgrid files and comparison-grid references. It also binds
the extractor's own SHA-256.

The historical six-hour OFF `wrfinput_d01` hash is checked against the source
lineage receipt; the separate paired-preparation OFF file is not substituted.
This mapping task does not itself run GDB. The subsequent archived Intel
replay completed using this selection; see [capture results](../capture/control_analysis.json)
and the [replay receipt](../capture/replay_receipt.json).
