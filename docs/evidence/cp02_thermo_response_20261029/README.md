# CP02 weighted thermodynamic and rain response

This package combines the frozen `P01`/`P05` initial-field CSV with the three
validated CP02 KDM6 captures. `tools/cp02_thermo_response.py` calls the strict
`tools/cp02_kdm6_controls.py` validator before producing any analysis output.
The CSV SHA-256 is pinned, and its point/corner/level coordinates and weights
must match `selection.json` exactly. The output directory is created atomically
and must not already exist.

Initial `T`, `THM`, `P`, and `PB` profiles are also read from the hash-pinned
`binary/initial_thermo.csv`. Its extraction receipt and extractor hash are
pinned, and its three source `wrfinput_d01` hashes must match the frozen copy
manifest. Each arm/point/corner/level coordinate and weight is checked against
the selection; initial `QVAPOR`, `QCLOUD`, and `QRAIN` at P01/P05 must also
match the separately pinned selected-fields CSV. `T`, `THM`, `P`, and `PB` keep
their source labels and separate values. No actual-temperature conversion is
made; `T00_K_metadata_only` stays metadata and is not added to either `T` or
`THM`.

The profiles contain weighted four-corner values for `QVAPOR`, `QCLOUD`, and
`QRAIN` from the initial CSV and for captured `q`, `qc`, `qr`, `th`, `pii`, `p`,
`den`, `nc`, and `nr` at entry and return for both calls, for all 39 levels and
all three arms. Captured REAL*4 corner bytes and original initial CSV decimal
values are included in `profiles.csv`; the `q`, `qc`, `qr`, `th`, `pii`, `p`,
`den`, `nc`, and `nr` argument names remain candidates and carry no inferred
runtime unit or physical interpretation.

For the frozen 624 selected 3-D keys per arm, the call 1 return to call 2 entry
transition has 155 newly positive `qr` samples for OFF, 163 for HYDRO, and 123
for LIQUID. Newly positive means the previous captured value is `<= 0` and the
next captured value is `> 0`. The corresponding QR median and range are
reported in `analysis/thermo_response/summary.json`, both for all newly
positive samples and for the subset with exact-zero `nr`. Call/endpoint
distributions also report positive `qr` with exact-zero `nr`; LIQUID call 2
entry has 162 such samples and a maximum of `4.505567485e-4`, while call 2
return has 63 such samples and a maximum of `4.488841805e-4` in the captured
numeric values. Each distribution includes median, quartiles, and range.

At weighted P05 level 8, HYDRO call 1 entry/return `qr` is `2.718877195e-4` /
`0`; LIQUID is `2.710022856e-4` / `2.615345799e-4`. The same rows retain `q`,
`qc`, and `th`, which differ between the two arms. These are captured-state
comparisons; they do not establish process causality.

The companion plot script writes argument-profile and QR figures after checking
the analysis summary, profiles CSV hash, both initial CSV hashes and receipt,
and the selection hash.
No mass closure, runtime unit assignment, actual-temperature conversion,
causality conclusion, or scientific threshold claim is made. Graph freshness
would not establish runtime or scientific validation.

Regenerate the analysis and figures with:

```sh
python tools/cp02_thermo_response.py
python docs/evidence/cp02_thermo_response_20261029/analysis/plot_cp02_thermo_response.py
```
