# Native startup diagnostic — 2026-10-12

The local runtime-choice run used one executable and unchanged `-fpe0` trap policy for its one-rank, one-thread `PRESERVE` and `CLEAR_FTZ_DAZ` arms. Both arms were rejected with floating invalid before KDM6. Startup MXCSR was `0x1920` in both, where FTZ and DAZ were already clear, so the local pair did not create an FTZ/DAZ contrast and supports no FTZ/DAZ causal claim.

A separate copied-source Noah observer captured the actual cold-branch inputs at `I=138`, `NS=4`, `J=197`. All recorded operands were finite. `TSLB<T0` and `PSISAT>0` make the temperature ratio and first FK factor negative; their full base is positive, approximately `191.15005`. The observer retained the original FK expression and changed no Noah physics or LSM scheme. This observer build is separate from the same-executable runtime-choice pair; its source, object, archive, executable, compile profile, hashes, and exact trace are linked in the [machine-readable receipt](evidence/cp06a_native_controlled_20261012.json).

`pr78` in local filenames is a retained batch identifier; the existing PR linked below is a separate evidence source.

The primary diagnosis for the Noah invalid remains the independent evidence already recorded by [open PR 78](https://github.com/gonos2k/Cloud-BAL/pull/78): the same-executable policy pair traps at `DIVPS` with identical operands, where two unused upper SIMD lanes evaluate `0/0`; subsequent instructions consume only the scalar result lanes. The diagnostic’s receipt and disassembly are identified by Git blob hashes in the local receipt. Those artifacts came from the PR branch and were not rerun or produced by this package.

No successful native candidate or time integration is established. No model inputs, original model data, or large NetCDF files are included. The compact `rawlogs/` directory contains only the runner receipt, startup/error/stdout logs, the source diff, GDB trace, and operand trace.
