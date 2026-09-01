# Cloud-BAL

Focused KLAPS baseline for improving cloud-derived vertical motion, balance
coupling, and hydrometeor initialization.

This initial snapshot intentionally contains only the source boundaries needed
to study and change:

- cloud classification and cloud-derived `w`/`omega`;
- optional radar-reflectivity adjustment of cloud vertical motion;
- `lco/COM` coupling into the balance analysis;
- cloud liquid, cloud ice, rain, snow, and precipitating-ice initialization;
- LAPSPREP hot-start conversion and WPS hydrometeor output;
- the relevant namelists and NetCDF schemas.

## Data flow

```text
cloud + reflectivity
        |
        v
get_cloud_deriv --> lco/COM (Pa/s) --> qbal --> balance/lw3
        |
        +----------> lwc/ice/rain/snow/pic --> LAPSPREP --> WPS
```

Positive geometric `w` is an updraft. The legacy conversion writes it as
negative pressure vertical velocity: `omega = -(w * pressure) / 8000`.

## Repository layout

- `src/cloud`: cloud-analysis call boundary and radar status handling.
- `src/deriv`: derived cloud products, thin-cloud insertion, and output.
- `src/lib`: cloud/radar vertical-motion algorithms and precipitation
  concentration support. The legacy mixed radar reader is reduced to its
  reflectivity routines; radial-velocity readers are intentionally omitted.
- `src/balance`: cloud-omega ingestion and balanced-field output.
- `src/lapsprep`: hydrometeor hot-start conversion and WPS output.
- `src/include`: includes directly required by the selected legacy sources.
- `config`: active cloud-derivation and LAPSPREP controls.
- `schema`: `lco`, `lwc`, `lcp`, and `lw3` field contracts.
- `docs`: baseline scope, known defects, and acceptance requirements.

## Deliberate exclusions

No observations, model data, operational output, executables, object/module
files, logs, benchmark products, graph/wiki artifacts, or wind Barnes/OpenMP
release files are included. Raw radar ingest/remap and the complete KLAPS build
system are also outside this initial repository.

The selected files preserve their upstream FSL public-domain notices. This is
a focused source snapshot, not yet a standalone KLAPS build. External KLAPS and
NetCDF dependencies will be isolated behind tests as the implementation is
improved.

See [docs/BASELINE_REVIEW.md](docs/BASELINE_REVIEW.md) before changing the
algorithms.

The staged correction and validation strategy is documented in
[docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md).
