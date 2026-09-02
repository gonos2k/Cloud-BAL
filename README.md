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
files, logs, benchmark products, wiki content, or wind Barnes/OpenMP release
files are included. `graphify-out` contains the persistent source-and-document
structural graph of this focused snapshot. Raw radar ingest/remap and the complete KLAPS
build system are also outside this repository.

The selected files preserve their upstream FSL public-domain notices. This is
a focused source snapshot, not yet a standalone KLAPS build. External KLAPS and
NetCDF dependencies will be isolated behind tests as the implementation is
improved.

See [docs/BASELINE_REVIEW.md](docs/BASELINE_REVIEW.md) before changing the
algorithms.

The staged correction and validation strategy is documented in
[docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md).

The completed source changes, preserved legacy baseline, and verification
commands are summarized in
[docs/IMPLEMENTATION_REPORT.md](docs/IMPLEMENTATION_REPORT.md).

The historical candidate-v1 design for S-band precipitation fall trajectories,
downdraft energetics, compact balance support, divergent/rotational modes, and
wave-control handoff is retained in
[docs/RADAR_PRECIP_DOWNDRAFT_DESIGN.md](docs/RADAR_PRECIP_DOWNDRAFT_DESIGN.md).

The original-source-derived direct QBAL inputs, upstream producer chain,
prepared 2026-08-16 cases, radar extension, and fail-closed ban on final
`bigfile` inputs are defined in
[docs/QBAL_REAL_INPUT_CONTRACT.md](docs/QBAL_REAL_INPUT_CONTRACT.md).  Run
`tests/run_real_input_inventory.sh` to validate the four prepared hourly source
sets; the command intentionally confirms a `BLOCKED` direct closure until the
missing original upstream intermediates have been regenerated.

The current one-page authority and promotion decision is
[docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).  The cloud-regime,
S-band radial-velocity, precipitation-trajectory, local-balance, and wave-noise
basis is summarized with primary literature in
[docs/SCIENTIFIC_BASIS.md](docs/SCIENTIFIC_BASIS.md).

The focused real-data evidence commands are:

```bash
tests/run_real_shadow_cases.sh
tests/run_real_shadow_figures.sh
tests/run_radar_velocity_audit.sh
```

The real runner requires a clean exact-head tree and the pinned Intel ifx 2026
binary.  The figure and velocity-audit wrappers verify and pin that committed
generation before reading it.  The four prepared hours are never filtered by
outcome.  A failed stage returns the input state and is not published as a
candidate; its failure reason remains available in the stage result.
