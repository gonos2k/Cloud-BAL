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
