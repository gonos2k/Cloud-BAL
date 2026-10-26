# PR105 GK2A LVD scope at 14Z

This is a read-only source and data audit of the actual LAPS satellite product
`ANAL/NE57/DAOU/00/lapsprd/lvd/kogk2a/262281400.lvd`. The file SHA-256 is
`e7d2e745782dcfec29f0097183c510b759cefceab6617b2398d8a2b68cecb841`.
Its `valtime` and `reftime` are both 2026-08-16 14:00 UTC. The extracted
metadata and finite-value counts are in
[`satellite_lvd_audit_v3.json`](evidence/pr105_satellite_scope_20261026/satellite_lvd_audit_v3.json).
Superseded development readbacks are retained externally with paths and hashes
in `evidence/pr105_satellite_scope_20261026/superseded_manifest.json`; only v3
is used for the findings below.

## Channel meaning and coverage

The source `lvd_driver_sub.f` names the five legacy LAPS channel slots as visible, 3.9,
6.7, 11.2, and 12.0 micrometres. In this LVD, the populated IR arrays are
`S3A` (channel 2, 3.9 µm averaged), `S4A` (channel 3, 6.7 µm averaged),
`S8A` (channel 4, 11.2 µm averaged/warm-pixel/cold-pixel products), and
`SCA` (channel 5, 12.0 µm averaged), plus `S3C`, `S4C`, `S8W`, `S8C`, and
`SCC` companion products. Their units are degrees Kelvin. This is brightness
temperature (BT), not a radiance array and not a QC score. The wavelength
labels are source-declared; this audit did not inspect GK2A spectral response
functions or independently calibrate the channel labels.

Each populated IR array is finite and non-fill at all 66,505 points of the
235×283 LVD raster. The visible `SVS`, `SVN`, and `ALB` arrays, as well as
`S5A`/`S5C` unused slots, are entirely `_FillValue` in this file. The three
visible slots carry counts/counts/none metadata respectively; they do not
provide a usable reflected-radiation observation here. Non-fill coverage does
not itself establish calibration, cloud validity, independent QC, or
observation representativeness.

PR104 froze source-composed QC support at 613 target mass-level cells in 16 columns
and the fixed five-cell Chebyshev buffer at 7,644 cells in 196 columns. Its
actual 14Z station-stencil audit found zero intersections with either mask
(0/765 eligible temperature stations; all 765 stencils were inside the WRF
mass grid). The source pins and counts are preserved in
`PR104_OBSERVATION_AUDIT_20261026.md` and
`evidence/pr104_observation_audit_20261026/station_mask_coverage_14z.json`.
The receipt-bound `ANAL/NE57/DABA/static.nest7grid` (asset role `static_grid`,
SHA-256 `384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b`)
has 235×283 LAPS latitude/longitude arrays and the same Lambert projection
metadata and SW corner as the LVD: all nine checked parameters differ by
exactly zero in native NetCDF values and the corner differences are 0.0°.
The pinned PR93 horizontal-row artifact also declares a 235×283, 5 km Lambert
source grid with the same SW corner and projection parameters; each comparable
parameter differs by exactly zero from LVD/static. Its source metadata includes
a 6371.229 km Earth radius, but the LAPS files have no numeric counterpart for
that value. This directly registers the LVD raster. The
frozen WRF 16 support columns and 196-column buffer were mapped to nearest
LAPS grid-cell centers using the closed 13Z WRF history XLAT/XLONG grid. This
maps to 16/16 and 196/196 unique LAPS cells, with maximum center distance
3.487 km on the 5 km grid. Each populated IR channel has BT at 16/16 support
and 196/196 buffered mapped cells. Separately, the original 162 pressure-cell
QC support resolves to nine distinct LAPS source cells; each populated IR
channel has values at 9/9. These are geometry and data-availability counts,
not an equivalence between QC and BT.

An independent post-review readback also verifies the target-index handoff:
the horizontal-row receipt's pinned `geo_em` `XLAT_M/XLONG_M` coordinates are
exactly equal to the closed WRF `XLAT/XLONG` arrays, each 282×234. The before/after
source hashes and zero maximum differences are retained in
`evidence/pr105_satellite_scope_20261026/target_grid_peer_readback.json`.
This check is separate from the v3 audit script's shape check.

## Existing operator and scope limit

Legacy KLAPS cloud code reads `S8A` and optionally `S3A`; its visible path
reads `ALB`. It screens S8A and includes an empirical `compare_radiation`
path that compares analyzed cloud to 11.2 µm BT and adjusts cloud fractions
(4 K threshold, 0.05 cover step, up to 10 iterations). This is an existing
BT-to-cloud-analysis correction, not a general model-column radiative-transfer
operator. A separate NCEP RTM test utility exists, but no GK2A channel-response
binding or use in the closed C2 runtime path was established. Cloud-BAL's
state/operator accepts cloud fraction and radar reflectivity, but has no GK2A
BT field or channel operator. The original 16 QC columns cannot be treated as
BT observations, nor can their QC values be converted to temperatures.

The closed historical C2 host output provides available finite, nonzero
`CLDFRA` and `REFL_10CM` diagnostic values at 13:10 UTC. Actual selected
physics computation provenance remains unresolved because the selected C2
evidence does not bind the WRF source routine/formula. These fields are not
satellite BT simulations.

The actual LVD can document same-time satellite input availability and
possible legacy cloud-analysis consumption. It cannot, by itself, measure
independent forecast skill: upstream initialization/boundary lineage and
whether this particular 14Z product was consumed by the closed run remain
unresolved. The diagnostic inspection uses only previously closed historical
C2 output; no live/new forecast arrays were opened. No physics, operator, or
data were changed.

## Reproduction and source pins

Run `python docs/evidence/pr105_satellite_scope_20261026/audit_lvd_scope.py --output -`
from this Cloud-BAL worktree to print a reproducible JSON result. File output
uses exclusive creation; pass a fresh `--output` path to save a rerun. The
script verifies the LVD,
receipt-bound LAPS `static.nest7grid`, PR93 frozen QC composition, PR104
station-coverage evidence, original replay receipt, and a previously closed
13Z WRF history by SHA-256 before counting coverage. It also verifies the
composition's `horizontal_rows_path`/SHA binding against the preserved PR93
horizontal-row artifact and confirms its nine source cells match the
composed QC links (162 pressure cells). It also compares the horizontal-row
source grid's dimensions/projection/SW corner to LVD/static and records the
numeric differences (exact zero for comparable values). The mapping method
and center-distance statistics are recorded in the JSON.

The absolute source path, line range, and SHA-256 for channel declarations,
legacy LVD readers, empirical BT/cloud adjustment, RTM test utility, and
Cloud-BAL input fields are pinned in the JSON's `source_code_refs`. The C2 `CLDFRA` and
`REFL_10CM` claims refer to output metadata/values in the pinned closed WRF
history, not a source formula: the selected executable/object receipt does
not bind the WRF routine that calculated them.

## Graph and extraction record

The existing Graphify snapshot was queried first for LVD, GK2A, cloud,
radiation, buffer, and observation-operator relationships; it identified the
satellite ingest driver, legacy cloud readers, and `compare_radiation`, but
did not establish a current-run use edge or an LVD/WRF grid-registration edge.
The subsequently inspected source and NetCDF file are authoritative for this
audit. The shared graph snapshot was not updated, so graph delta is none.
Graph extraction says nothing about runtime use or scientific validation.
