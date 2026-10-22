# PR99 native `ww` consumer replay

The bounded canonical report is [pr99_native_consumer_20261022_canonical.json](evidence/pr99_native_consumer_20261022_canonical.json). It contains the C1 archive/object and module bindings, strict pinned-Intel build identity, input and raw-output hashes, fixed-support metrics for OFF/HYDRO/COUPLED, and the projected U/V candidate comparison.

The archived C1 `calc_ww_cp` consumer emits mass-coordinate `ww` in Pa/s, not physical W. The replay includes all 40 vertical faces, including the zero top face, over the safe interior. The candidate changes U/V only and remains a research proposal; these initial-state consumer replays do not reproduce the T32 grouped failure, establish a full momentum or moisture balance, or validate a forecast.

The driver input reader checks the archived C1 grid dimensions (234 × 282 × 39 mass cells), uses the existing PR87 sentinel-aware finite-field policy for every NetCDF input, and rejects nonpositive map factors and `RDX`/`RDY` before reciprocal use. Focused NetCDF tests cover wrong-grid rejection before field access and declared fill-value rejection. Re-serializing the frozen OFF input after the reader changes produced the same native-consumer input SHA-256 as the retained strict-profile run, so no new forecast or native-operator execution was needed.

Older detailed run directories and raw fields are superseded and excluded from the published evidence. No field arrays or executable binaries are committed.
