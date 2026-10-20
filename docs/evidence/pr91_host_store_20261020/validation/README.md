# PR91 host-store diagnostic validation

This bundle records failure-only diagnostics for the pinned PR90 C7 source pair. Maintained physics sources were not modified. Generated host/core snapshots are retained only for final `_i`; attempt sources, compiler outputs, and executables otherwise remain in `/var/tmp` and are identified by path, size, and SHA-256 in `artifacts.json`.

## `_i` writer and shared-core checks

The extracted writer ran with `PR91_RUN_ID=stub_run_20261020`. Its raw output is `final_i/pr91_actual_store_failures.raw`; the record readback checked its 48 fields, exact hexadecimal words, attempted scale 1 versus returned theta 0, and failure stage 6. The external writer executable and its hash are listed in `artifacts.json`.

The existing `test_joint_qnb_transport.f90` passed against the transformed core at both O0 and O2 using the pinned Intel profile. Executables remain in `/var/tmp/pr91_core_forwardcompat_20261020/{O0,O2}` and their hashes are in the manifest. The focused Python transform suite passed all 3 tests.

Compiler profile: `tests/intel_toolchain.sh`, SHA-256 `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`; compiler is pinned Intel `ifx 2026.0.0` (binary SHA-256 in the manifest). Audit and reproducibility flags are also recorded there. Compile/run commands and captured outputs are recorded per check in `artifacts.json`.

## Generated host attempts

- D1 was interrupted before host compilation. Its exact external generated source path and hash are recorded; no successful compile is claimed.
- D2 failed compilation with Intel error #6099 at generated line 4592: `END DO` without a matching `DO`. Its external source, preprocessed source, compiler log paths and hashes, plus the diagnostic excerpt, are recorded in the manifest.
- D3 built a nine-object partial native overlay. Its receipt and compiler log are retained under `native_d3/`; the receipt records `PASS_OVERLAY_BUILD`, `full_clean_build=false`, and `model_run=false`. The 81,174,464-byte executable remains external; its path and SHA-256 are in `artifacts.json`.

The separate OFF 200-second diagnostic run at `/var/tmp/pr91_OFF_200s_d3_20261020`, run ID `PR91-D3-OFF-200s-20261020`, closed INCOMPLETE with return code 1 after nine steps and the T10 RK3 failure. Its first 73 complete trace records match the preserved C7 OFF 180-second prefix exactly; see `../diagnostic_d3/closed_run.json` and `step9_prefix.json` for closed-run bindings. The archived Cloud-BAL graph snapshot does not represent generated host source and gives no runtime evidence.

`SHA256SUMS` uses paths relative to this directory and can be checked with `sha256sum -c SHA256SUMS`.
