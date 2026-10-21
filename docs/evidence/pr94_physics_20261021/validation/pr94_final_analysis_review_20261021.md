# PR94 final analysis review — 2026-10-21

Read-only review of the current per-column water export/report/JSON, HYDRO response receipt/timestamp/grid checks, and cloud support index guard. Did not review the HYDRO source-chain implementation and did not run model analysis.

## Findings

- No correctness blocker found in the reviewed scope. Water inventory changes and precipitation are in kg per native column; accumulated `RAINC + RAINNC` increments are multiplied by cell area once, while phase subset accumulators are not double-counted. The available column residual is `sum_k(Δ water inventory) + precipitation outflow`, and its JSON status remains `OPEN_MISSING_TERMS`; missing surface, boundary, process, and numerical terms are explicitly named. Report does not call this a closed residual.
- Per-column extrema use `argmax(abs(values))` in native JI layout and store zero-based `(j,i)` plus the matching XLAT/XLONG. The report tables match the JSON values: inventory maximum `(j=264,i=69)`, precipitation `(113,30)`, and available imbalance `(71,161)`, with units kg per column. Private arrays are outside the checkout, directory/file permissions are `0700/0600`, and the public JSON exposes only path/hash/array names, not numeric grids. Public PNG hash matches the JSON (`2e9888…b806`); current source JSON SHA-256 is `1e14d2…d6440`.
- Public map axes and colorbar units are labeled. Its symmetric signed-field limits use a pooled 99.5th percentile; precipitation uses a pooled 99.5th percentile upper limit. The report does not currently state that plotted extremes are percentile-clipped, and the JSON does not record the selected color limits. This is a presentation limitation, not a numeric/export error; recommend documenting the clipping/limits so the public map cannot be read as showing full extrema.
- HYDRO response now checks same candidate namelist, exact 30-step model schedule, receipt COMPLETE/rc=0/step30, same expected+executed frozen C4 executable, and a common boundary. HYDRO requires `current_generation: true`, source-bound wrfinput and boundary hashes equal its run receipt, and a live binding check. It reads all three actual history timestamps at 0..600 s, and compares OFF/COUPLED and OFF/HYDRO DX/DY, timestamps, map factors, coordinates, and hybrid coefficients via `verify_paired_grid`. Pointwise three-arm identity is reported separately from pairwise RMS metrics.
- Cloud support rejects out-of-range/negative target indices before subtracting the raw-grid ring offset; its test covers the negative-wrap case. No mask selection depends on result values.

## Targeted validation

`python3 -m pytest -q tests/test_pr94_water_budget.py tests/test_pr94_cloud_response.py tests/test_pr94_hydro_response.py` — 22 passed.

## Optional minor enhancement

Add the signed value at each absolute column maximum to `column_map_stats` and report JSON; signed total plus max magnitude/location currently suffice for the requested aggregate/geography check, but not the local sign at the extrema.
