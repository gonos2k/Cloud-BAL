# PR104 actual observation and provenance audit

This audit pins the actual 14Z LSO and checks what the existing PR102/PR103
receipts establish about observation use and the reported 13Z maximum T2
residual. It covers the historical runs retained before the separately
authorized H/A/N 3600-second runs; it does not report on those later runs.

## Actual 14Z LSO

`ANAL/NE57/DAOU/00/lapsprd/lso/262281400.lso` is present at the workspace
root. Its SHA-256 is
`5897d4ec8d4979a71369f68de95c68f7229ae76fa6104619d893b204b9ad6ec9`, matching
the `surface_observations[20260816T140000Z]` pin in
[`original_upstream_replay_20260816.json`](../tests/original_upstream_replay_20260816.json).
The header says `16-AUG-2026 14:00:00.00`, and an independent record walk
parsed all 803 declared records. All 803 record HHMM fields are 1400. Of
these, 765 temperatures are not the source sentinel `-99.9°F`; 38 equal that
sentinel. The 765 unfiltered values span 62.96–116.06°F (17.2–46.7°C).

No station QC flag or accepted plausibility range is supplied by this audit.
It does not remove records or label values as outliers. The source reader
receives report time and Fahrenheit temperature; the published PR103 source
pins identify `-99.9°F` as the missing-temperature sentinel. Details and file
pins are in
[`actual_lso_and_provenance.json`](evidence/pr104_observation_audit_20261026/actual_lso_and_provenance.json).

## What the historical H/A/N comparison establishes

The published comparison is at 13Z and uses `262281300.lso` (SHA-256
`b70ee7a7…e03b9fd`), not the actual 14Z `262281400.lso`. H, N, and the other
retained 13Z five-arm T2 fields are bitwise equal to O. The A640 control is
also bitwise equal to O in its retained 13Z T0 T2 field. Those existing
results therefore cannot discriminate H/A/N using a timestamp-matched 14Z
surface residual. The historical A640 integration ends at 13:10:40 and its
observation sidecar uses only the 13Z LSO. No 14Z model sample is claimed
here. The new 3600-second runs require their own readback before this finding
can be revisited.

The upstream inventory does not bind the full surface-analysis ancestry:
`original_upstream_replay_20260816.json` marks the surface-analysis stage
`SURFACE_OBSERVATION_CLOSURE_UNDECLARED`. Accordingly:

- **Initial state:** no stored H/N/A640 input receipt directly names the 14Z
  LSO. Indirect influence through an upstream analysis is not established or
  excluded by the retained closure.
- **Lateral boundary:** H, O, and N share the same `wrfbdy_d01` hash, which
  proves common boundary-file identity across those arms. It does not prove
  independence from 14Z analyses; the boundary's upstream ancestry is
  unresolved.
- **Observation nudging:** the inspected WRF namelists have an empty `&fdda`
  group, so these runs do not configure WRF FDDA nudging.
- **Candidate selection:** the retained candidate controls do not use a 14Z
  station residual as a selection score. The published status remains
  `observation_skill: NOT_EVALUATED`.

These are limits on the historical receipts, not a claim about the forthcoming
3600-second runs or their shared upstream products.

## 13Z maximum-residual sample

The published 13Z maximum absolute residual is station **22485** (KMA), at
34.62°N, 128.54°E. The source LSO reports 13:00 and 114.44°F (45.8°C), with
station elevation 0.0 m and expected accuracy 1.08°F. The sampled O-arm T2 is
297.163654 K (24.013654°C), giving signed `model − observation` residual
−21.786346°C.

The 4×4 interpolation neighborhood has T2 values 296.737–297.615 K and model
terrain HGT 0–48.578 m; source interpolation of HGT at the station gives
0.602 m, close to the reported 0.0 m station elevation. Terrain mismatch does
not explain this residual. The same station's 14Z LSO record is also present:
KMA, 34.62°N, 128.54°E, 0.0 m, 14:00, 116.06°F (46.7°C), expected accuracy
1.08°F. Both records remain raw here. No sample is discarded, and no QC or
plausibility threshold is inferred from the comparison.

The observation is not assigned a cause or QC verdict by this audit. The
PR103 comparator documents the LSO badflag `-99.9°F`, model T2 units K,
declared-fill/NaN checks, and interpolation missing value `1.0e37`; its
expected-accuracy field is reported but is not treated as QC or covariance.

## Graph and evidence limits

I queried the existing Cloud-BAL Graphify snapshot for surface-observation,
initial, boundary, selection, temperature, and residual relationships. It
returned generic Cloud-BAL nodes and no extracted edge proving the external
KLAPS LSO-to-WRF lineage. Source, input bytes, and published receipts were
used for this audit. The graph was not refreshed; graph delta is none. No
KLAPS50 graph snapshot was created or changed by this task. Graph extraction
does not prove runtime use, scientific validity, or independence.

The structured pins and record calculations are retained in
[`actual_lso_and_provenance.json`](evidence/pr104_observation_audit_20261026/actual_lso_and_provenance.json).

## Bounded station 22485 source follow-up

The actual 14Z record (pinned LSO SHA-256 above, lines 6416–6418) gives
station/provider `22485`/`KMA`, coordinates 34.62°N/128.54°E, elevation 0 m,
HHMM 1400, the literal following line `BUOY`, and temperature 116.06°F with
expected accuracy 1.08°F. The same station's 13Z raw LSO field is 114.44°F.
The source-reader implementation at
`src/upstream/read_surface_obs.f` (SHA-256
`f9053d3ee62d7b917119528cd133fe3ad1d073c15dd747c30afc940ae816eab3`) reads
report metadata at lines 110–119 and temperature/expected accuracy as degrees
Fahrenheit at lines 123–125. It has a separate reader for a distinct `.lso_qc`
file (lines 876–882 and 894–905); the raw LSO record itself carries no
station-QC verdict through this reader interface.

The retained replay inventory binds
`ANAL/NE57/DABA/namelist/surface_analysis.nl` by SHA-256
`725b1c8f6464a9a1e5a2e044ea81c44b5a196f4c576038af2707bb09a80cb107`.
The published replay execution record (SHA-256
`52994f8ab4a810e31138ccd22405682f2483595faac1af4e7af73c4e25d88f4e`, lines
1349–1353) documents `USE_LSO_QC=0` and `L_REQUIRE_LSO=false`. This describes
the replay configuration; it does not establish whether an upstream producer
QC-processed the input before writing the pinned LSO.

The raw temperatures are Fahrenheit and their Celsius conversions are
correct. The `BUOY` label alone does not establish the measurement kind, and
the retained inventory provides no station-level producer report or lineage.
No authoritative station QC flag or verdict was found. Therefore the
measurement kind, producer chain, and upstream station-QC status remain
unresolved. All station observations remain in the valid-time comparison;
no plausibility threshold or exclusion is introduced. Structured pins and
record excerpt are in
[`actual_lso_and_provenance.json`](evidence/pr104_observation_audit_20261026/actual_lso_and_provenance.json).

## 14Z station coverage of the fixed QC region and old N−A signal

Using all 803 14Z station coordinates and the old closed 13Z O-arm grid
geometry, I projected each location with the pinned PR103 Lambert operator
and checked the exact 4×4 `gdtost` stencil against the horizontal columns of
the frozen QC support (16 columns) and its fixed 5-cell buffer (196 columns).
No station stencil intersects either region: 0/803 and 0/765 valid-temperature
stations for both support and buffer. All stencils are fully inside the WRF
mass grid. The coverage test uses only coordinates and the declared −99.9°F
sentinel to define the valid-temperature subset; it does not use temperature
values as scores. This establishes that the 14Z stations do not geometrically
sample the frozen source region under this operator and these masks. It does
not imply the observations have no indirect influence through analyses or
boundaries.

As a separate model-only check, I applied the same source interpolation
operator to the old closed N and A T2 fields at 13:10 UTC at station
coordinates, without subtracting any observed temperatures. Across all 803
locations the N−A signal is nonzero at 803, with RMS 0.02815 K and maximum
absolute difference 0.28402 K. On the 765 locations with non-sentinel 14Z
temperature, it remains nonzero at 765, with RMS 0.02835 K and maximum
absolute difference 0.28402 K. These are descriptions of the old N−A fields
sampled at a predeclared valid-time station set; they are not residuals,
observation scores, or forecast skill results. The all-803 historical check is
preserved alongside the valid-765 subset.

Pins, exact stencils, coverage counts, and both model-only metric summaries
are in
[`station_mask_coverage_14z.json`](evidence/pr104_observation_audit_20261026/station_mask_coverage_14z.json).
