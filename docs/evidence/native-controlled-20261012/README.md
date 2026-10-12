# Native controlled startup diagnostics (2026-10-12)

The primary policy-causality comparison is the same executable and fixed `-fpe0` trap behavior, with only runtime MXCSR FTZ/DAZ bits differing at WRF initialization. `gradual_policy_gdb.log` and `ftz_daz_policy_gdb.log` are that paired run. Both trap at the same Noah `DIVPS`, before KDM6, with identical operands. `receipt.json` records build/input hashes; `noah_divps_disassembly.txt` and `scalar_noah/` retain the source-to-instruction and follow-on diagnostic evidence.

`gradual_replay_gdb.log` is one additional repeat of only the gradual arm. `ftz_daz_setup_failure.log` records a separate runner attempt that failed before executing WRF. `prepolicy_gdb4_startup_exit.log` is an initial debugger startup attempt that exits before `wrf_init`; `prepolicy_gdb5.log` is an initial pre-policy trap capture. These are retained for execution-count accounting, not as additional paired policy arms.

The scalar Noah build is separate from the policy contrast: both Noah objects were rebuilt together with pinned strict O0 plus `-no-vec`, preserving `-fpe0`, and linked into one executable for its two-arm diagnostic. The Noah trap is removed in that diagnostic, which next stops at radar initialization on an uninitialized `xam_g` reciprocal in KDM6. This does not constitute a successful native candidate run. No model source or physics was changed.

Execution accounting is in `execution_counts.json`: 10 WRF exec starts total (4 starts in the two eligible paired comparisons, 5 unpaired startup probes, and 1 process that exited before `wrf_init`); six GDB setup attempts with no WRF exec are excluded. No run reached time integration.
