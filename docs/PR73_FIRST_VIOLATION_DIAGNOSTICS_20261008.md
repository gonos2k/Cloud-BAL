# PR73 first-species rejection diagnostics

The PR72 KDM6 preflight stopped with a generic fatal message. The PR73 composition adds one first-violation record at the initial `KDM62D` species scan. It reports the failed species pair, Q/N/B values and units, source stage, `i/k` indices, the explicit `i/k` dummy bounds, and the `lat` argument as `call_lat_index`. It does not change species state or proceed into PSD work after a rejection.

The captured partialhost run rejected ice with:

```text
KDM6_FIRST_VIOLATION|stage=KDM62D_INITIAL_PREFLIGHT|species=ice|state=mass_only|q=3.5308575789291633E-035|q_unit=kg kg-1|n=0.0000000000000000E+000|n_unit=m-3|b=null|b_unit=m3 kg-1|i=133|call_lat_index=2|k=1|scope_i=2:233|scope_k=1:39|index_origin=KDM62D_dummy_bounds|j_global_mapping=unclaimed
```

For ice, B is not an input to the paired-state check, so its value is null. The captured Q and N are the live values at the rejection. PR72 had inferred the same Q/N values and numeric index values from the earlier trace; this PR73 record is a direct runtime capture and labels the second coordinate only as the `KDM62D lat` argument. It does not establish geographic latitude or a global-j mapping.

The initial validator walks the actual `KDM62D` domain `i=its:ite`, `k=kts:kte`, mapping assumed-shape storage back through those explicit lower bounds. The captured bounds were `i=2:233`, `k=1:39`. The ordering is `k`, then `i`, then rain, cloud, ice, and graupel. The first invalid pair was ice at `i=133`, `k=1`.

## Validation and evidence

The pinned Intel profile passed the focused wrapper fixture at O0 and O2. Both runs emitted the structured record for a manufactured ice mass-only state before any PSD calculation. The fixture receipt is [receipt.json](evidence/pr73_first_violation_20261008/receipt.json), with generated source composition and captured output lines alongside it.

A fresh partialhost build copied the retained PR72 host objects and archive into `/var/tmp`, recompiled KDM6 from the frozen PR72 source with the PR73 diagnostic, replaced the selected archive member in that fresh copy, and relinked. A new isolated run staged the same 100 input files by hash and used fresh output paths. The staged `wrf.exe` was also included in the isolated runner's input guard. All 100 model inputs and the executable were unchanged; the first-call pretrace hash matched the PR72 baseline. Output isolation passed for the 14 files produced by the earlier PR72 run. A separate [completion audit](evidence/pr73_native_first_violation_20261008_attempt2/completion_audit.json) declares required post-call outputs independently and records `REJECTED`, required-output guard `FAIL`, and incomplete execution: `pr67_kdm6_process.raw`, `pr69_water.raw`, `kdm6_first_call_post.raw`, and `wrfout_d01_2026-08-16_12:00:20` are all missing. The run returned 128 at the controlled initial admission rejection before KDM62D returned or the 20-second model step completed. The [attempt 2 native receipt](evidence/pr73_native_first_violation_20261008_attempt2/native_receipt.json) records compile/link commands and hashes for the fresh KDM6 object, archive member and archive, linked and staged executable, toolchain profile, and input proof. The diagnostic source and reproducible patch are retained beside it, with the captured WRF logs. Attempt 1 remains preserved at `evidence/pr73_native_first_violation_20261008_attempt1/` as the initial capture.

This is partialhost evidence. The retained host objects, WRF dependencies, and libraries were not rebuilt as a complete full-physics host. The diagnostic establishes which species state failed first and its stored values, not the upstream physical cause or a successful model step. PR72's inferred cause remains an inference; this capture does not establish why the live ice mass was positive while ice number was zero.
