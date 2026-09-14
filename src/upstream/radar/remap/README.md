# Isolated radar remap consumer

This directory contains the reviewed consumer-side corrections for the legacy
NetCDF-to-LAPS radar remapper. Operational files under
`klaps-v5.0_/src/ingest/radar/remap` and
`klaps-v5.0_/src/lib/radar/remap_ftn` are left untouched. The build runner
overlays these files and uses operational copies for the remaining remap
sources.

The input boundary now validates required NetCDF variable names, primitive
types, ranks, and dimensions. Dimension and variable read errors are returned
to the caller. The raw input set must contain one contiguous `elev01` through
`elevNN` sequence; missing intermediate tilts are rejected. The final absent
`elev(NN+1)` request is treated as the explicit end-of-volume marker.

The decoder stores every field in a normalized 920-bin array. Per-tilt
`numGatesV` and `numGatesZ` metadata are read and used to mark padded bins as
missing. Both fields must agree and fit the normalized array. The remapper
uses the metadata first-gate range and spacing (converted from source metres
to internal kilometres, then back to metres for geometry) and rejects a
mismatched velocity/reflectivity geometry before processing. The caller invokes
`lut_gen` for every volume, and lookup tables are regenerated from the current
radar coordinates, LAPS domain, first-gate range, and gate spacing, so a stale static LUT cannot silently move
the rays. The current configured consumer contract supports 920 bins and equal
fields with 250 m spacing; other spacing is rejected before ray processing.
The first-gate range is metadata-bound and may differ from the old zero-origin
assumption. No NYQ physical range is advertised in
the output CDL; positive finite Nyquist observations are retained and a
volume-wide value becomes missing when tilt values differ.

The legacy packing remains unchanged: `fill_common` stores `nint(2*value)` and
`ld_ray` restores values with a factor of one half. Output NetCDF fields carry
no `scale_factor` or `add_offset`. Ray-major offsets remain
`(ray - 1) * gates + gate`, and output array order is `(record,z,y,x)`.
Existing reflectivity and velocity screening rules are retained.

Build and run with the pinned Intel profile:

```text
Cloud-BAL/tests/build_radar_remap.sh
python Cloud-BAL/tests/run_radar_remap.py --radar-root <decoder-output>/RADR/ouda/GSN
python Cloud-BAL/tests/test_radar_remap.py --output <output>.v04
```

The runner accepts `--base-snapshot` so the remap time binding can be supplied
by the corrected decoder receipt. A run is accepted only when the bound
process exits zero and the complete output exists. Failed input or output
status is preserved in the run log and receipt. A failed geometry or input run
may leave diagnostic static LUT files because LUT generation precedes later tilt
validation; those files are retained as evidence and are not products. The
receipt distinguishes this state from an accepted run with a v04 product. The
run is bound to a sealed executable and Landlock-private working tree.

This is a provisional raw-decoder consumer binding. It establishes no
fall-speed correction, dealiasing, additional QC, target authority, or raw
radial timestamp authority.
