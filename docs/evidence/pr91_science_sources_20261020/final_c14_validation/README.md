# PR91 C14 focused validation

The final focused regression set has 63 passing cases across 22 files, run with the pinned Intel profile in a fresh scratch directory. `focused_command.sh` is the exact command and `pytest.log` is its output. The C14 test exercises the maintained joint transport core under pinned Intel O0 and O2.

`source_pins.json` binds the maintained core and tests, C14 generated `module_em.F`, C12 solve source, C13 FogDES source, profile, native overlay build receipt, and executable. The native build is a partial overlay build, not a clean build or model runtime.

The first 63-case attempt and its single failure are retained in `attempt_01_failure.json` and `attempt_01_pytest.log`. `test_pr90_rain_final_psd.py` now proves that the current maintained core is the generated EM prefix and that replacing only that prefix with the frozen original C7 core reconstructs the exact historical C6 source hash. Its T8 behavior assertions continue to run against the current core.

Source-first producer endpoint representation differences are included in the existing `SOURCE_REPRESENTATION` signed pressure-coordinate aggregate together with source sidecar and operator changes. That aggregate does not isolate a source-endpoint quantum count or provide complete process-budget attribution. The grouped storage adjustment=4 count and signed Q/N deltas remain separately reported.

Pinned Intel O0/O2 checks confirmed that the explicit REAL64 `2^-149` quantum and the prior `NEAREST(REAL32)->REAL64` construction yield identical intended values. The explicit constants clarify representation; no global threshold behavior change is claimed.

This is focused source/core validation only. The C14 paired runtime remains external and in progress; these results do not establish native runtime success or science-gate closure.
