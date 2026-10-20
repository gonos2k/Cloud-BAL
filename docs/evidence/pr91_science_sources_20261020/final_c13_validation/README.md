# PR91 C13 focused regression evidence

The focused set contains 21 files. Its final unique case count is 57: 55 unchanged cases from the full pre-fix run, plus the two final FogDES fixture cases rerun after the test-only positive-flux correction. The pre-fix full run passed 57 in 40.08 seconds, but its two FogDES cases are superseded; do not count those twice. The final two-case run passed in 2.164 seconds under pinned Intel O0/O2.

- Full focused command and case list: `focused_command.sh`.
- Pre-fix full run retained as historical baseline: `pre_fix_baseline/`.
- Final superseding two-case command/log: `superseding_two_cases.sh`, `final_positive_flux_two_cases.log`.
- Current test, tool, generated source, and profile hashes: `source_pins.json`.

The test-only correction adds positive common flux and reconstructed source-conservation assertions to the fixture. The maintained FogDES transform and generated source were unchanged. This is focused regression evidence only, not a native model runtime or science approval. Standalone joint transport O0/O2 validation remains bound by the prior C12 receipt.
