# ODAM precipitation reference variables

The user selected ODAM **RN1** (one-hour accumulated surface precipitation)
and **PTY** (surface precipitation type) as the first comparison variables for
later model integration. They are not the integrated-file `pc`, `spt`, `ptt`,
the three-dimensional `ptyp`, or a Cloud-BAL layer transport ledger.

## Source-confirmed file contract

- Producer: `klaps-v5.0_/dfsd/ODAM/klps_lc05_dfsd_odam.f`.
- RN1 file: `DFS_VSRT_GRD_KLPS_ODAM_RN1.YYYYMMDDHH00` (lines 888–894).
- PTY file: `DFS_VSRT_GRD_KLPS_ODAM_PTY.YYYYMMDDHH00` (lines 1076–1082).
- Grid: x=149, y=253; original analysis crop x=76..224, y=7..259,
  one-based Fortran indices (lines 47–50). Retain this coordinate mapping.
- Text format: timestamp header, then `10F7.1` values, x varying fastest.
  The header contains analysis time and a separately labelled LST time.
- PTY codes: 0=no precipitation, 1=rain, 2=mixed rain/snow, 3=snow;
  thermal selection at lines 958–1003 and observation override at 1055–1058.
- RN1 uses the separate RAIN analysis `INFILE_RAIN`, with AWS adjustments;
  it is not copied from integrated `pc`. Preserve its numerical units until
  actual product/time metadata and the upstream rain unit contract are checked.
- Wrapper destination: `ANAL/NE57/DAOU/DFSD/YYYYMMDD/`, from
  `ANAL/NE57/SHEL/klps_lc05_dfsd_odam.csh:153–156`.

## Acquisition status

The user delivered files in
`/NHNHOME/WORKSPACE/26weather002_A/yhlee_data/ODAM/`.
RN1 and PTY for 2026-08-16 13:00 UTC are now present and were read directly:
both headers are `2026081613+000hour     2026081622LST`. Each has 149×253
values. The earlier 21–00 UTC-only delivery did not match the retained forecast;
the newly delivered 13 UTC pair does.

[Acquisition and same-hour comparison](../scratch/cp02_odam_13utc_20260914/REPORT.md)
records the raw identities, coordinate matching, RN1 errors, and PTY limits.
The retained 12–13 UTC model accumulations have been compared pointwise with RN1.
PTY forecast-type agreement remains uncomputed until its instantaneous model
category definition is matched. These pilots do not isolate an omega effect.

For subsequent cases, preserve the raw bytes and bind timestamps, one-hour
accumulation windows, units, grid coordinates, missing-value handling, and PTY
codes before comparison. Compare RN1 to model accumulation over the same hour;
compare PTY using a declared matching-time/type definition. Do not sum overlapping
one-hour analyses or replace model accumulation with instantaneous flux.

## Six-hour land-only verification

The supplied 13–18 UTC RN1/PTY files are inventoried. The requested South Korean land-only six-hour comparison is complete; sea and North Korea are excluded with a fixed 3,688-point mask. See [experiment and results](CP02_SIX_HOUR_PRECIPITATION_VERIFICATION_20260914.md). Earlier full-domain scores are superseded for this verification scope.
