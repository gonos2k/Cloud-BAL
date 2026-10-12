# PR82 native stage trace reproduction record

This records the exact source and commands for the PR80 clean replay captured in [the raw package manifest](pr82_native_stage_raw_package_20261012.json). It is an evidence reproduction note, not a maintained general-purpose builder.

The observer patch `patches/pr82_native_nc_boundary_trace.patch` (SHA-256 `8a365b69931e15bb24e7b96ae0661a16c7aa036113750319dc68e83c48b908f1`) was applied with `patch --fuzz=0` to the source snapshot `/var/tmp/pr64_qc_channel_20261007/source/solve_em_pr64_qc_channel.f90` (SHA-256 `72aa50d495fa13d58029189f643fba218c819f8d0911c5138997124d6e99459b`). The staged compile source hash is `25d0614215a22ffc892789dc41e18e21c114d0bf206cb99fe0da0c2e7923f8d0`.

Build receipt [pr82_native_stage_build_recipe](pr82_native_stage_build_recipe_20261012.json) preserves the exact ifx compile and mpiifx link argv, cwd, compiler hash, candidate hashes, and logs from fresh scratch `/var/tmp/pr82_native_stage_trace_build1`. [The companion audit](pr82_native_stage_build_audit_20261012.json) pins the prior link metadata and verifies the occurrence-preserving archive change. The build-time pre/post snapshot covers the solve source and base archive; it does not cover every external link input.

The exact clean replay was run as:

```bash
PR82_NATIVE_INPUT_RUN=/var/tmp/pr80_kdm6_radar_contract.nsUNuj/run \
  tests/run_pr82_native_number_trace.sh \
  /var/tmp/pr82_native_stage_trace_build1/wrf_pr82_stage.exe \
  /var/tmp/pr82_native_stage_trace_run2
```

For a replay, use a new, nonexistent run-root path because the runner is create-only. It copies from the pinned PR80 source case through the detached copier, invokes the native first-step GDB runner, and emits the single shared KDM6 rejection trace plus the selected-cell stage records. The executed helper hashes and source-snapshot result are bound in the run receipt summarized by the package manifest. The captured source snapshot had 109 files; the explicit model inputs are identified by their individual hashes, not by that count.

The small captured artifacts are [the 19-row selected-cell stage CSV](pr82_native_stage_trace_pr80clean_20261012.raw) and [the one-row shared rejection CSV](pr82_native_rejection_pr80clean_20261012.csv). The exploratory run using an older case with prior diagnostics is retained separately under filenames containing `run1_exploratory` and is excluded from this clean replay attribution.
