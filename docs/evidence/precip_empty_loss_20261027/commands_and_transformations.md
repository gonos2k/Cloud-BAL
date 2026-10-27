# Empty lost-hit regression

The canonical six hourly NPZs were used as scratch-only source data. For the rainy OFF case, HYDRO and LIQUID were replaced by copies of OFF; reference and OFF arrays and coordinates/indices were retained. For all-dry, the four precipitation fields were zeroed while coordinates/indices were retained. No transformed NPZs were written into the repository. SHA-256 pins for source and transformed inputs, commands, CLI results, and byte comparison results are in `regression_receipt.json`.

The a777d39 baseline reproduces the empty-array minimum reduction failure for both cases. The current CLI completes both cases and emits all eight outputs, including the header-only focus CSV. The rainy-case focus PNG is retained here. The unchanged canonical run byte-matches the original three CSVs and `summary.json`.
