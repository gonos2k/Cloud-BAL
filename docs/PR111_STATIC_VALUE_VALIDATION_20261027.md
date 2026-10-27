# PR111 — static-grid values before WPS output

Baseline: PR110 merge `e381c88ebcc14ecc5f100e7a74d571752dee0789`.

PR110 fixed static input types, dimensions and read status. A correctly shaped
FLOAT variable can still contain missing data or invalid coordinates. In
particular, the default NetCDF FLOAT fill is finite and positive, so a positive
spacing check alone cannot reject an unwritten Dx.

This change validates static values before unit conversion and before the WPS
writer is called. It preserves the existing producer storage contract and
meters-to-kilometers conversion. The reader and writer remain production modules
in the boundary regression; only unrelated configuration/date support is supplied
by fixtures.

All numeric static fields reject nonfinite values, the default FLOAT fill and
values equal to declared `_FillValue` or `missing_value` markers. Attribute
lookup/read failures and malformed marker metadata fail explicitly. Nonfinite
markers are allowed as metadata for otherwise finite data; the data check rejects
nonfinite payloads before any marker comparison.

Every latitude and longitude cell is checked, not just the WPS corner values.
The existing one-wrap longitude and encoded southern-latitude conventions are
retained within bounded input ranges. LoV follows the same longitude convention;
Latin1 and the Lambert-specific Latin2 must be geographical latitudes. Terrain
requires valid finite data without imposing a new physical height threshold.

## Validation scope

Pinned Intel O0/O2 runs passed with compilation and linking in fresh external
scratch directories:

- The actual LAPSPREP caller, static reader and WPS writer rejected 12 malformed
  static inputs per build, including the five reported cases. Each rejection
  required a nonzero status, the intended diagnostic and no WPS output.
- Normal input and finite input declaring a NaN missing marker passed in both
  builds. The verifier read all 23 binary WPS geometry records in each output;
  the existing vapor, pressure-order, hydrometeor and SHADOW checks also passed.
- The standalone actual-reader suite retained its 17 layout/type/range failures
  per build, now with case-specific diagnostics. Synthetic array order and
  conversion checks and the hash-pinned archived static grid passed.
- Independent pinned Intel validation confirmed the retained encoded-coordinate
  convention: latitude 330 and longitude 350 produce corners -30 and -10.

[Validation and source hashes](evidence/pr111_static_values_20261027/validation.json)
and [team review](evidence/pr111_static_values_20261027/team_review.json) record
the scope. Review caught and resolved the LoV input-range gap and test diagnostic
and verifier-call issues. The final native run supersedes intermediate harness
development runs. Test discovery still registers 310 modules; the complete
portable tier was not rerun for this native-only change.

## Research scope

No C2 physics, wind candidate, solver tolerance, source-cache policy or forecast
run is changed. The existing 640-second evidence remains scoped to its original
experiments. H/A/N one-hour integration remains INCOMPLETE at 760 seconds and
14 UTC observation skill remains NOT_EVALUATED. Static-input regression does not
close T39 diagnosis or whole-host water, energy and mass–wind acceptance.
