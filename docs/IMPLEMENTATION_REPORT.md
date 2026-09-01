# Cloud-BAL implementation report

## Preserved comparison baseline

The legacy analysis was copied before any algorithm change to:

```text
scratch/baseline_legacy_0d4c9a8_20260816
```

The archive contains three final `ANAL/.../LAPS` files, their three KLBG
background files, three downstream `met_em` files, active namelists/CDLs, and
the three legacy executables.  Its 21 payload files are independent read-only
files and pass `sha256sum -c SHA256SUMS`.  `ANAL` and `MODL` are not test output
locations.

Use the read-only comparison gate after an isolated rerun. Changed WPS
intermediate and NetCDF files are expanded into field-level dimension/unit,
valid-count, RMS-delta, and maximum-delta diagnostics:

```bash
tools/compare_baseline.py \
  scratch/baseline_legacy_0d4c9a8_20260816 \
  /path/to/isolated/candidate
```

## Implemented changes

1. `qbalpe` now initializes pressure staggering and allocated work arrays,
   selects `k8/k5` by nearest pressure, fixes the eight-point SH average,
   bounds-safe `destagger_x`, and applies `sfctempadj` to the actual output.
2. A field contract carries field name, valid time, dimensions, canonical
   units, status, source, and a 1-D/2-D/3-D cell-valid mask. LAPSPREP validates
   mandatory input fields and handles optional hydrometeors cell by cell.
3. Pressure thickness, Coriolis support, `delo`, `tau`, coefficients, and solver
   iterates have finite/range guards. Both continuity and PHI solvers return a
   failure/non-convergence status; failed candidates are not written.
4. Pre/post continuity and momentum diagnostics call the same guarded
   operators. A continuity candidate is rejected if its shared residual grows.
5. Background arrays are no longer reused as continuity or destagger output;
   dedicated candidate/output arrays hold all modified fields.
6. The continuity correction solves `div(C grad(lambda))=-div(V)` with spatially
   varying inverse-error and `tau` coefficients in flux form.
7. Vapor/liquid/ice changes are paired transfers in dry-air mixing-ratio units.
   LWC/ice cap excess moves to rain/snow, precipitation phase allocation closes
   exactly, thin-cloud column mass is thickness-normalized, and post-transfer
   density is recomputed before omega-to-w conversion.
8. The cloud layer detector closes top-boundary layers and processes every
   separated layer. Convective layers ascend; precipitating stratiform layers
   have lower descent and upper ascent lobes.
9. Radar evaporation remains compile-time locked off even if an old namelist
   requests it. `MODE_EVAP=0` remains the active configuration.
10. The replacement S-band radar path runs only after rain/snow/precipitating-
    ice concentration exists. It converts dBZ to linear reflectivity for fall
    speed, preserves observed 3-D echo geometry, fills only unobserved lower
    gaps along wind/fall characteristics, diagnoses bounded loading/cooling
    downdrafts, and returns failure/degraded status transactionally.
11. `COM` read status is now independent of later wind reads, so a missing COM
    file cannot become a valid zero observation. A compact Wendland-C2 support
    with `Rh=clamp(6*dx,30 km,60 km)` and `Rp=150 hPa` localizes the full
    balance candidate and its variable-coefficient continuity projection.
    Increments are bitwise unchanged outside support and are rejected above
    10 m/s.
12. Wind increments are diagnosed separately through divergence (velocity
    potential) and vertical vorticity (streamfunction) profiles. Lower/middle/
    upper supported levels and divergent roughness are reported. Reflectivity
    does not directly prescribe a vortex, although the existing momentum
    balance can diagnose a localized rotational response. Independent wind or
    vorticity-tendency support remains a future acceptance gate for that
    midlevel rotational update.
13. Empirical cloud vertical motion is treated as a resolution-dependent
    target rather than an observation. Cloud depth/grid spacing, analyzed
    cloud fraction, and vertical sampling scale the target, with provisional
    5 m/s convective and 0.5 m/s stratiform grid-mean safety caps.

## Verification

Run:

```bash
tests/run_unit_tests.sh
```

The suite checks field masks/metadata, conservative phase transfers, phase-sum
closure, scale-aware multi-layer/top-boundary profiles, S-band linear-Z fall
speed, tilted precipitation-gap fill, downdraft sign, deterministic/no-publish
behavior, compact localization, divergent/rotational separation, the exact
extracted production qbal continuity operator, invalid
`dp`/`tau`/NaN/Coriolis cases, residual improvement, and fixed-form compile
checks for both derivation and balance paths. The current synthetic continuity
case reduces RMS residual from about `8.31e-5` to `2.58e-6`.

The full LAPSPREP source also passes a gfortran syntax check against the
archived NetCDF include and the full-tree LAPSPREP modules (using the legacy
`-fallow-argument-mismatch` compatibility flag). A scientific production
comparison still requires building in a separate full KLAPS tree and rerunning
the retained 2026-08-16 inputs into an isolated output root; it must not write
to live `ANAL` or `MODL`.

## Full-tree build integration

This focused repository intentionally has no operational KLAPS make system.
When the files are copied into the full build, compile the free-form modules
before their fixed-form consumers in this dependency order:

```text
cloud_bal_field_contracts
cloud_bal_moisture
cloud_bal_cloud_profiles
cloud_bal_localization
cloud_bal_radar_downdraft   (depends on cloud_bal_moisture)
cloud_bal_wind_modes
  -> vv_lgt_ct, get_cloud_deriv, pcpcnc, laps_deriv_sub, qbalpe
```

`tests/run_unit_tests.sh` performs this source-order compile gate. Enabling the
new derivation path requires the new module objects to be linked into the
derived-product executable; enabling localized balance requires the
localization and wind-mode objects in the qbal executable.
