# Isolated Cf/Radial decoder

`klps_radr_dcod.f90` is a reviewable Cloud-BAL copy of the legacy decoder. It
is kept outside the operational KLAPS source tree and is driven by
`Cloud-BAL/tests/run_radar_decoder.sh`.

The isolated downstream consumer corrections are in `remap/` and are built
and exercised by `Cloud-BAL/tests/build_radar_remap.sh` and
`Cloud-BAL/tests/run_radar_remap.py`.

The decoder reads raw Cf/Radial FQC moments and writes the legacy fixed output
shape of 800 radials by 920 gates. It validates dimensions, variable types,
packed ray offsets, sweep indexing, range coordinates, moment packing
attributes, geometry, times, and Nyquist metadata before writing any output.
The source Nyquist value is selected by sweep index. Packed values are decoded
as `raw * scale_factor + add_offset`; input fill values become the output
`NODATA` value (`131072.0`).

The time contract accepts only CF `seconds since YYYY-MM-DDTHH:MM:SSZ` with a
supported Gregorian calendar. The decoder checks that the requested epoch
matches the declared origin and that every radial epoch is covered by the raw
`time_coverage_start`/`time_coverage_end` metadata. The runner snapshots and
hashes each raw input before decoding, derives each output cycle from that
input's origin, and records the source and snapshot hashes in its receipt.

Reflectivity, velocity, and range units are checked against the decoder
contract. Spectrum-width units are copied from the raw input so a source
metadata discrepancy remains visible in the output rather than being silently
relabelled.

Some raw inputs have more than 920 gates. The output contract cannot represent
those extra gates, so the decoder retains the first 920 gates and records
`source_gate_count`, `output_gate_count`, and `gate_data_truncated=1` in each
output file. It never claims those omitted gates were processed.

Each sweep is written to a private temporary NetCDF file and published with an
atomic no-replace hard link only after the file is closed. The runner keeps the
whole radar stage private until all per-radar output validation and durable
malformed/offset/time probes pass, then publishes the stage with an atomic
no-replace directory rename. A failed run retains its private stage and failure
receipt for inspection.

This copy emits raw reflectivity, velocity, and spectrum-width moments. It does
not apply dealiasing, fall-speed correction, quality control, or target/grid
authority.

Run the pinned validation from the repository root:

```sh
./Cloud-BAL/tests/run_radar_decoder.sh
```

The runner defaults to the `RDR_*_FQC_202608162200.nc` snapshot. Set
`RAW_TIMESTAMP` to validate another single snapshot. It compiles with the
pinned Intel profile in `tests/intel_toolchain.sh`, builds in a fresh
`Cloud-BAL/scratch` directory, and launches every case through Landlock and
the sealed hash-bound executable runner.
