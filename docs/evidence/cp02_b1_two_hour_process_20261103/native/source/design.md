# B1 two-hour native diagnostic plan (pinned, not yet launched)

## Scope

This is a diagnostic-only overlay on the archived first-hour BASE/FIX KDM6 source. It does not change microphysics expressions, thresholds, or state updates. Native execution is gated on parent approval of the exact sample indices, staged B1 initial input hashes, and CPU sets. The matched case is the same B1 initial condition (`9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5`), common boundary input (`74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45`), and identical `dt=20` namelist. The reference B1 six-hour case is `scratch/weak_strong_balance_20261030/ORIGINAL_B1_100`; its archived executable hashes to BASE `de110a7f…`, and its 12/13/14Z output hashes are recorded in the existing case receipt. BASE/FIX anchors are source and executable hashes in `pins.json`.

## Instrumentation point and identity

`kdm6(th,...)` owns `itimestep`, domain-global loop index `j`, and WRF arrays; it converts `nr` to `nrs = nr*den`, then calls `kdm62D` once per `j`. `kdm62D` owns the saturation variables, `dtcld`/substep loop, rate limiter, process rates, and updates. The diagnostic patch will pass `itimestep`, a wrapper call sequence ID, and `wrf_get_myproc()` rank into `kdm62D`. Each record carries `(rank, call_id, itimestep, loop, j, i, k, phase)`.

Selected `i,j` pairs are the 16 exact global WRF mass-cell corners supplied by the cohort analysis: four each for weak RN1 hit-lost, weak false alarm, weak stable hit, and strong stable-hit fallback. A threshold-5 hit-gain mask is empty, so the strong point is explicitly a fallback. A record is emitted only when both indices match the configured pair. One OpenMP thread is fixed. Per-rank append-only files avoid MPI file contention; a tile-bound record is emitted for each match. The runner records rank PID ownership only when `/proc/<pid>/cwd` and the resolved executable both match that arm’s case directory. This excludes simultaneous opposite-arm or unrelated WRF processes. Runtime trace audit will verify every selected point belongs to exactly one rank and has no duplicate row in any timestep. Any duplicate or missing owner stops interpretation.

## Values and phases

Real values are logged through `TRANSFER` to signed decimal integer words; each signed integer preserves the exact IEEE binary32 bits. The raw `n0r` value uses a separate signed 64-bit transfer word. No real-to-decimal conversion is used. Logs contain:

- Entry raw state before KDM62D's initial nonnegative clamps: `q`, `t`, `den`, `qci`, `qrs(rain/snow/graupel)`, `nci`, `nrs(rain/snow/graupel)`, `brs`.
- Post-clamp state and corresponding `nr=nrs(rain)/den`.
- After saturation setup: `qs_liquid`, `qs_ice`, `rh_liquid`, `rh_ice`, and `sw`.
- For each timestep/substep and selected level: `dtcld`, `satdt`, `prevp` after its unbounded formula and `fac_evap`, then snapshots immediately after the condensate cap and final saturation cap. Record branch-specific pre/post values at the existing source branch; no limiter predicate or rate expression is recomputed.
- Immediately before/after each KDM62D state update: the rain and vapor budget terms, all directly relevant process rates (`praut`, `pracw`, `prevp`, `piacr`, `pgacr`, `psacr`, `pmulrs`, `pmulrg`, `pseml`, `pgeml`, `psevp`, `pgevp`, `psdep`, `pgdep`, `pinud`, `pidep`), `q`, `qrs(rain/snow/graupel)`, `nrs(rain)`, and `t`.
- Returned `rainncv`/`rain`, plus bottom-level rates, after the 2D call. `den` is logged directly; the derived density hypothesis is not substituted.

This captures the `prevp` limit and associated phase-budget terms. It does not claim full column water/energy closure; precipitation source/writer verification remains a separate gate.

## Build and run protocol

1. Stage all 89 common files from the verified `IMPROVED_BG_FIXED` B1 six-hour case into separate scratch OLD/FIX run directories. Confirm immutable input and boundary hashes against pinned receipts. Modify only time-control fields to stop at +2 h (`run_hours=2`, `end_hour=14`, `history_end_s=7200`); preserve `dt=20`, physics, grid, boundary, and all other staged bytes.
2. Confirm archived source/executable hashes in `pins.json`. Preserve the archived originals; create separate instrumented BASE/FIX sources and fresh build directories.
3. Source only `Cloud-BAL/tests/intel_toolchain.sh` (SHA-256 5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4), initialize the pinned MPI environment, and use the archived build recipe/host libraries. Compile both diagnostic builds in fresh scratch build dirs. Save full compiler/link receipts and hashes. Never build in the repository or run GNU/ifort.
4. After independent source-patch review and explicit parent GO, run OLD on CPUs 32–39 and FIX on CPUs 40–47, each with 8 MPI ranks and one OpenMP thread. Execute the same B1 initial input, common boundary files, and 2 h control window; write all model output and trace only under this scratch root.
5. Before trace interpretation, compare every shared numerical history variable and coordinate at 0/1/2 h bitwise against the retained OLD (`ORIGINAL_B1_100`) and FIX (`IMPROVED_BG_FIXED`) six-hour histories. Only the documented end-time control fields may differ. Any mismatch stops interpretation; do not relax the match.
6. Parse trace phase counts, verify one owner per selected point and all expected timesteps/substeps, then assess whether the source-linked processes show a same-input BASE→FIX response. Do not describe a forecast improvement unless the CSI/hourly gates and the existing matched 6-hour B1 comparison also pass.

## Exact launch commands (parent GO required)

```bash
cd /var/tmp/b1-two-hour-probe-20261103
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/tests/intel_toolchain.sh
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh
export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
# After explicit parent GO, root supplies B1_NATIVE_GO=ROOT_GO in the environment.
python3 run_pair.py --case OLD --authorize-native
python3 run_pair.py --case FIX --authorize-native
python3 compare_histories.py --case OLD
python3 compare_histories.py --case FIX
python3 validate_trace.py --case OLD
python3 validate_trace.py --case FIX
```

`OLD_CPUS=32-39` and `FIX_CPUS=40-47` are parent-pinned; root reserved CPUs 64–71 for pytest. The 16 global cells, source hashes, OLD/FIX reference paths, staged inputs, and bitwise match criteria are pinned in this bundle. The independent source-patch review is complete; native launch remains gated on explicit parent GO. No model run has started.
