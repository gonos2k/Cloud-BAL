# PR103 observation connection

> **Historical pre-review output invalidated.** The original readback appended
> excluded records and used the wrong Earth radius. Its code and outputs remain
> preserved under the `*_pre_review` filenames and are not cited as results.
> The corrected reader and source-mapped comparator were reviewed before the
> root-authorized v2 readback below.

## Scope and v2 input-consistency result

This adds one same-cycle input-consistency comparison for the PR102 2026-08-16
13:00 UTC case: LSO surface air temperature against WRF's saved 2 m temperature
(`T2`). The signed residual is `H(X) - Y`, reported as model minus observation
in degrees Celsius. It is a diagnostic adapter built from existing source
geometry and interpolation code; it is not a registered assimilation operator.

The pinned LSO contains 816 records. The source reader's time field gives 803
records at 13:00; 765 have a temperature other than the source `badflag=-99.9
degF`. The remaining 13 records have other report times and 38 exact badflag
temperatures. The report includes reduced per-record station identity, time,
latitude, longitude, elevation, observation temperature, the LSO
expected-accuracy field and sampled T2. Expected accuracy is retained as
supplied; it is not treated as a QC flag or covariance. No station QC mask was
present in the record authority inspected, so no QC filter or quality cutoff
was added.

| Arm | Valid station matches | Bias (C) | MAE (C) | RMSE (C) | Max abs (C) | T2 difference from O |
|---|---:|---:|---:|---:|---:|---|
| O | 765 | -0.1891 | 0.8336 | 1.3098 | 21.7863 | reference |
| H | 765 | -0.1891 | 0.8336 | 1.3098 | 21.7863 | bitwise identical |
| C | 765 | -0.1891 | 0.8336 | 1.3098 | 21.7863 | bitwise identical |
| P | 765 | -0.1891 | 0.8336 | 1.3098 | 21.7863 | bitwise identical |
| N | 765 | -0.1891 | 0.8336 | 1.3098 | 21.7863 | bitwise identical |

All 765 valid-time stations had a complete in-domain 4×4 interpolation stencil.
The equal arm residuals are a valid null result: the compared `T2` fields are
bitwise identical across O/H/C/P/N. This says nothing about independent
forecast skill or physical approval. The LSO can share upstream analysis
lineage with the model input, and the observed records do not carry a station
QC authority in this source path.

## Observation and model authority

- Observation: `ANAL/NE57/DAOU/00/lapsprd/lso/262281300.lso`, SHA-256
  `b70ee7a7…e03b9fd`, pinned under
  `surface_observations[20260816T130000Z]` in
  `tests/original_upstream_replay_20260816.json`. The legacy reader and format
  declare station identity, WMO/provider, coordinates, record HHMM, and air
  temperature in degrees Fahrenheit (`read_surface_obs.f`,
  `lso_formats.inc`). The exact temperature badflag is `-99.9` from
  `surface_obs.inc`.
- Model: each closed 13:00 history is pinned in the PR102 five-arm history
  readback and by its arm receipt. `T2` has units K, mass-grid shape
  282×234, is finite, and spans 285.3764–301.9744 K in every arm. The LAPS WRF
  adapter reads `T2` and only falls back to the lowest sigma temperature when
  T2 is invalid (`module_wrf_lga.f90`).
- Corrected source candidate: project station lat/lon with the WRF-v4.8.0
  Lambert implementation in `share/module_llxy.F` (source SHA-256
  `0c777e66ffbb0602479cadcc0ab484769a140c4cb2b3e9a8f757597086f0c76b`). Its
  `EARTH_RADIUS_M` is 6370000 m. The previous exploratory reducer used the
  KLAPS map utility's 6371200 m constant; that output is not validated. The
  corrected candidate uses the exact `gridconv.f:gdtost`/`binom` interpolation
  logic and excludes points outside the source domain. Root and independent
  source review passed within this diagnostic-adapter scope.
- Archive adaptation: these archived histories contain `XLAT`/`XLONG`, but
  not `LAT_LL_T`/`LON_LL_T` read by `module_wrf_netcdf:get_wrf2_map`. The
  adapter anchors at `XLAT[0,0,0]`/`XLONG[0,0,0]`, corresponding to WRF's
  lower-left mass-grid point, and retains the pinned map attributes. Under the
  corrected 6370000 m WRF geometry, all 65,988 point deltas from archived
  1-based XLAT/XLONG indices have i RMS/max absolute 0.0003453/0.0007493 grid
  units and j RMS/max absolute 0.0001524/0.0004817 grid units. These are raw
  source-conformance readbacks, without a fitted acceptance tolerance. The
  geometry-only record is
  [`wrf_geometry_audit_v2.json`](evidence/pr103_observation_20261026/wrf_geometry_audit_v2.json)
  (SHA-256 `f35188ccdaa66fa6918c3296578efaaf8d42ca84491aa1b946a144af896844b1`).

The v2 reduced station records and five-arm result are in
[`surface_temperature_input_consistency_v2.json`](evidence/pr103_observation_20261026/surface_temperature_input_consistency_v2.json)
(SHA-256 `1813cf577e1030ac8c20b1651c1a857c6dd938092bb662d41278d94ddda7bf8c`).
The run receipt records 25 pre/post input, source, and code pins in
[`comparison_run_receipt_v2.json`](evidence/pr103_observation_20261026/comparison_run_receipt_v2.json)
(SHA-256 `4cdac99b83fb78649872d6362b89697b3ad31aaa7a3256d0010c32e9195771c8`).
The previous output and named pre-review copy remain unchanged and invalidated;
their metrics are not carried into this table.
The Python adapter and focused tests are
[`pr103_surface_temperature_observation.py`](../tools/pr103_surface_temperature_observation.py)
and [`test_pr103_surface_temperature_observation.py`](../tests/test_pr103_surface_temperature_observation.py).

The amplitude control's closed base-C2 20-second run was checked separately at
T0 using the same frozen comparator. Its T2 array is bitwise identical to O
and gives the same 765 matches and residuals. The
[A20 sidecar](evidence/pr103_observation_20261026/amplitude_t0/amplitude_t0_input_consistency.json)
and [run receipt](evidence/pr103_observation_20261026/amplitude_t0/run_receipt.json)
bind 17 unchanged observation, model, code, and source pins. This extends the
same-cycle input-consistency comparison to A20; it does not establish
independent observation skill.

The later closed A640 run was also checked at its generated T0 history only,
using the same frozen comparator and the same 13Z LSO/O inputs. The
[A640 T0 sidecar](evidence/pr103_observation_20261026/amplitude640_t0/amplitude640_t0_input_consistency.json)
and [run receipt](evidence/pr103_observation_20261026/amplitude640_t0/run_receipt.json)
bind the 32-step `AMPLITUDE` run closure, its generated T0 history SHA, and 21
unchanged pins including the earlier A20 and five-arm v2 artifacts. A640 T2 is
bitwise identical to O at T0; all 765 residuals and summary metrics therefore
match the same-cycle five-arm result above. This is still initial-time input
consistency only. The closed 640-second run does not make this T0 comparison a
forecast-skill evaluation.

## Source-kernel reference check

The expanded oracle extracts the exact `gdtost` and `binom` bodies from pinned
`gridconv.f`; only the two shared-include statements are replaced by the exact
`missingflag=1.0e37` REAL constant from pinned `bgdata.inc`. Fresh-scratch
Cloud-BAL IFX O0 and O2 runs cover linear fractional/integral samples, a
quadratic mixed-term field, source missing-value fallback/return behavior, and
an in-domain edge stencil. Python and IFX returned 24, 22, 90.5, 76.875,
REAL32 `missingflag`, and 1.0 respectively; accepted values agree at 0 REAL32
ULP after rounding Python's REAL64 result to REAL32. No fitted tolerance is
used. The result comparison is
[`gdtost_oracle_python_comparison_v2.json`](evidence/pr103_observation_20261026/gdtost_oracle_python_comparison_v2.json).
Commands, logs, extracted source, and receipts are under
[`intel_oracle_v2`](evidence/pr103_observation_20261026/intel_oracle_v2/).
Executables remain external; their hashes and retained paths are in
[`oracle_binary_retention.json`](evidence/pr103_observation_20261026/oracle_binary_retention.json).

## Validation and limits

- `python3 -m unittest tests.test_pr103_surface_temperature_observation -v`:
  14 tests pass, including first/last record exclusion ordering, declared
  fill/missing-value rejection for T2/XLAT/XLONG, the all-zero diagnostic
  guard, unit conversion, projection geometry, quadratic/mixed interpolation,
  missing stencil handling, and in-domain edge behavior.
- The v2 run read T2, XLAT and XLONG with `set_auto_mask(False)` and pinned
  `pr87_native_history._finite` before mapping or interpolation. The exact
  all-zero T2 check is an uncomputed-diagnostic guard, not a physical
  acceptance threshold. Historical pre-review files remain invalidated.
- No forecast was run, no Cloud-BAL Fortran production source was compiled,
  and no independent observation QC or skill claim was made.
- The known hourly case LSO files contain no exact 13:10 reports, and
  `262281310.lso` is absent. They cannot support a station-matched 600-second
  forecast residual, including for the closed A640 run. The 13Z file is pinned
  as an upstream observation source; whether those particular records entered
  the initial analysis is unknown without an analysis-consumption receipt. The
  comparison therefore stays same-cycle input consistency, with independent
  skill NOT_EVALUATED.
