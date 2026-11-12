# Scientific audit records and later metadata correction

The copied lineage and recount files preserve their executed/audited bytes and original absolute paths, as listed in `export_inventory.json`.

`fua_lineage/input_audit.md` was written before the REAL manifest correction. Its last paragraph describes the then-current wrong staged paths. The current `native/real06_inputlevels25/inputs.json` is corrected; `inputs.historical_wrong_staged_paths.json` retains the wrong paths. See `native/prior_forecast/postrun_metadata_links.json` for the correction, unchanged weather-file identities, and unavailable earlier validation bytes. This clarification supersedes that paragraph's present-tense description without rewriting historical audit bytes.

The fresh REAL run consumed archived met_em files, not raw KIM GRIB. GRIB headers and configured production paths were inspected separately. Historical ungrib/metgrid logs binding those exact GRIB and auxiliary messages to met_em were not recovered. The new run's input/output identities are recorded, while complete historical field provenance and statistical independence are not established.

Recount groups are overlapping observations, not exclusive causes. Descriptive mass bins do not alter the frozen selection or policy. `diagnostic_only.npz` is not an initialized model input.
