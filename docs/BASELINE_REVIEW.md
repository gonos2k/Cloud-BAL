# Baseline review

This document records the initial review gates for Cloud-BAL. It is not a claim
that the listed defects are fixed in the initial snapshot.

## Current operational behavior

- The default cloud-bogus path produces positive geometric `w` only, so its
  `COM` output represents updrafts (`omega < 0`) or missing values.
- Downdrafts are available only in a limited stratiform branch of the optional
  radar-bogus path. The active `config/deriv.nl` disables that path.
- Thin-cloud liquid/ice insertion occurs after cloud omega is calculated.
- LAPSPREP is configured for hot start, balance input, and WPS output.
- WPS receives the five hydrometeor species but not pressure omega or geometric
  vertical velocity directly.

## Priority defects

1. `lapsprep.f90` does not initialize `ice`; failed or missing NetCDF variables
   can leave negative sentinel values or undefined data in hydrometeor output.
2. Whole-array `MAXVAL` validity tests discard complete species for one missing
   cell while accepting the negative `-999` initialization value.
3. The active saturation helpers change water vapor without subtracting the
   corresponding liquid/ice mass.
4. Thin clouds can contain liquid/ice while `COM` remains missing because the
   two paths use different cover thresholds and run in different phases.
5. Cloud layers reaching the highest cloud level and multiple convective layers
   are not handled consistently by the vertical-motion profile code.
6. Lightning-missing data are assigned from a real missing sentinel to an
   integer array, making classification processor-dependent.
7. A missing `lco/COM` file is silently converted to zero omega, preventing the
   intended pointwise background fallback in qbal.
8. Radar and cloud coverage missing values are not consistently rejected before
   reflectivity/cloud-cover threshold comparisons.
9. Radar-reflectivity quality and time-tolerance variables have initialization
   gaps in the selected legacy call path.
10. Writer and workflow status handling can report success after a failed or
    incomplete `lco`/hydrometeor output.

## Required acceptance gates

- All five hydrometeor fields are finite and nonnegative at every output cell.
- Missing masks are checked cell-by-cell; a partial missing field does not erase
  valid cells.
- Total water is conserved across vapor/liquid/ice adjustment within an agreed
  floating-point tolerance.
- `w > 0` maps to `omega < 0`, and any implemented `w < 0` maps to
  `omega > 0`.
- Clear, thin-cloud, thick-cloud, multi-layer, and top-boundary cloud cases have
  explicit expected masks.
- Radar-off, partial-radar, and radar-on cases distinguish missing reflectivity
  from strong reflectivity.
- Missing/corrupt input variables and failed output writes fail explicitly or
  emit a documented degraded status.
- Unchanged fields remain bitwise identical; intentionally changed `COM` and
  hydrometeor fields use recorded missing-mask and numeric tolerances.

## Initial test matrix

```text
cloud:  clear | thin | thick | multilayer | top-boundary
radar:  absent | partial coverage | valid | malformed metadata
hydro:  each species valid | absent | partial missing | NaN | negative
mode:   radar omega off | radar omega on
repeat: deterministic reruns and compiler/runtime bounds checks
```
