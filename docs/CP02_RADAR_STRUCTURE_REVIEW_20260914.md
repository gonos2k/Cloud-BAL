# Existing radar and initialized hydrometeor structure

The user will provide ODAM RN1/PTY later. This preliminary review uses the
existing 2026-08-16 13:00 UTC HYDRO pressure-analysis result; it does not run a
model or use an external model omega target. The HYDRO candidate retains its
background omega exactly and is not a test of the forthcoming diagnostic omega
allocator.

[Machine-readable comparison](../scratch/cp02_radar_structure_20260914/RESULT.json),
[horizontal structure](../scratch/cp02_radar_structure_20260914/radar_hydrometeor_structure.png),
[vertical profiles](../scratch/cp02_radar_structure_20260914/vertical_structure.png).
The read-only comparison preserves the source file SHA256. Mixing-ratio plots
use g/kg dry air, with the same colour scale for background and candidate.
The horizontal mixing-ratio scale is logarithmic above 0.01 g/kg for visibility;
this is not a detection or acceptance threshold.

## Findings

- The retained payload classifies 67,567 above-ground cells as radar echo and
  1,227,129 as no echo, with no missing/unclassified active cells. Its configured
  no-echo sentinel is -10 dBZ; accepted echo values are 0–100 dBZ. The sentinel
  is not a sensor detection threshold. This is the input product's classification, not
  independent proof of radar coverage or sensitivity everywhere.
- Rain/snow/graupel are present in 63,457 echo cells before initialization and
  all 67,567 afterwards. Changes outside the echo cells are exactly zero.
  This spatial agreement is expected because the same radar drives the proposal;
  it is not independent radar validation.
- Precipitating hydrometeors remain in 87,019 no-echo cells, unchanged from the
  background. Their presence alone does not prove detectable radar echo; a
  physically consistent forward reflectivity calculation is needed before
  calling these false echoes or deleting them. This is the main unresolved
  structural comparison item.
- Cloud liquid/ice remain unchanged. Cloud condensate in no-echo cells is not by
  itself a contradiction with precipitation radar observations.
- The layer transport ledger has zero deposition into a lower unobserved
  atmospheric cell: 87.553% of input rate is blocked by an already observed
  destination, 11.336% intersects terrain, 1.108% is no-echo blocked, and 0.0035%
  is suspended. These are kg/s rate-accounting fractions, not accumulated surface
  precipitation, observed rain percentages, or a model forecast.

## Next comparison

Check the retained background precipitation in no-echo regions using radar
coverage/quality and a consistent reflectivity operator, retaining species,
temperature, pressure levels and valid masks. Compare vertical echo extent and
hydrometeor phase structure without requiring every cloud cell to have a radar
echo. Preserve the supplied observations and do not tune omega to force a visual
match. Once RN1/PTY arrive, bind their time windows, grid and phase codes for the
separate comparison to one-hour model-integrated surface precipitation and type.


## One-hour response of retained initialization experiments

The comparison sequence is initialization diagnostics → one-hour forecast response
→ observations/analysis valid at that forecast time → improvement decisions.
For a 12 UTC initialization, instantaneous fields are compared at 13 UTC and
RN1 against model accumulation over 12–13 UTC. PTY uses the matching analysis
time and an explicitly matched model category definition.

[Retained forecast sensitivity](../scratch/cp02_one_hour_sensitivity_20260914/RESULT.json),
[precipitation panels](../scratch/cp02_one_hour_sensitivity_20260914/precipitation_sensitivity.png),
[extracted forecast fields](../scratch/cp02_one_hour_sensitivity_20260914/forecast_precipitation.nc).
No new model run was performed. RAINC+RAINNC is compared; RAINSH is zero in all
three retained forecasts, and snow/graupel amounts are not added again.
The initial files do not serialize precipitation counters. A read-only source
and configuration check binds all three runs to 12 UTC cold starts: the host
zeros RAINC and RAINNC at simulation start, RESTART is false, and bucket resets
are disabled. Thus the 13 UTC counters represent model accumulation over 12–13
UTC. Source/configuration identities are in the sensitivity result; this is not
an observational validation of those amounts.

| Paired initialization | Minimum/maximum local precipitation change (mm) | Grid-mean absolute change (mm) |
|---|---:|---:|
| HYDRO minus OFF | -10.371 / +7.364 | 0.0591 |
| LIQUID minus HYDRO | -5.464 / +6.541 | 0.0315 |

These results establish sensitivity, not improved accuracy. Initial W is unchanged
in both pairs, so they do not test the new diagnostic omega assignment. The
native initial T/Q and U/V also differ between named cases; the differences
must not be attributed to a single isolated physical factor merely from a case
label. The subsequently delivered 13 UTC RN1 was compared in
[the ODAM report](../scratch/cp02_odam_13utc_20260914/REPORT.md); model PTY matching remains open. No instantaneous radar
reflectivity is treated as an observed one-hour rainfall accumulation.

The next diagnostic-omega comparison should hold the remaining inputs and model
configuration fixed, record the actual changed initial fields, and inspect mass
closure and hydrometeor/air-motion consistency before interpreting the one-hour
response. Improvement is determined by reduced error against matching-time
observations/analysis, not by a larger precipitation response or smaller changes
alone.
