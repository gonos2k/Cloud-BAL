# Focused validation

`focused_tests.json` binds the final Python observer/reducer source and
test hashes to `focused_tests.log`: seven tests pass, with the recorded
NumPy ABI RuntimeWarning. This command compiles no Fortran and launches
no forecast.

The `focused_tests_before_portable_fixture.*` records retain the earlier
six-test validation; the final seven-test record includes the team-review
fix removing a private /var/tmp source dependency. The tracked excerpt
fixture tests PR100 hook insertion only, with compact.prepare held fixed.

Raw compiler logs and recorded compile argv retain source-echo or
shell-emission trailing spaces. They are preserved byte-for-byte and excluded only from
the whitespace gate:

- `docs/evidence/pr100_qc_process_20261022/build/logs/compile_final.log`
- `docs/evidence/pr100_qc_process_20261022/build/logs/compile_missing_module_dependencies.log`

- `docs/evidence/pr100_t1_snow_melt_20261022/direct_transfers_and_ground/observer_compile.log`
- `docs/evidence/pr100_t1_snow_melt_20261022/direct_transfers_and_ground/helper_harness_compile.argv`
- `docs/evidence/pr100_t1_snow_melt_20261022/direct_transfers_and_ground/observer_compile.argv`

Their SHA-256 identities remain covered by that bundle's checksum
inventory. This exception does not apply to source, reports, or patches.
