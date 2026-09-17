# Actual full-domain balance comparison status

This record covers the preserved actual NE57 case at **2026-08-16 13:00 UTC**
(`262281300`) on the full 235 × 283 × 22 LAPS pressure grid. The source is
`scratch/upstream13.Sfb68E`; no synthetic field and no subdomain are used. The
historical `scratch/actual_thermo_root_run.SuqsSJ` candidate is not part of this
comparison. It is retained only as separate historical evidence.

The machine-readable provenance and status record is
`/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/bpair_20260917/comparison_status.json`.
It records the source, build, runtime, executable, and run-log hashes. Its
final SHA256 is
`f1d5ef1abecaec48d21ff38aaf35d535c0b452dd8fc66e12b43662543eeafded`.

The 90-entry manifest in `scratch/bpair_20260917/original_inputs.json` binds
89 preserved `upstream13.Sfb68E` entries plus one operational
`ANAL/NE57/DABA/namelist/balance.nl` control entry. Rehashing found 90/90
matches, with zero missing files and zero mismatches. Generated private output
trees, including `input/lapsprd/lapsprep/wps/` and any
`input/lapsprd/balance/`, are excluded from that source-input audit. They are
run products, not replacements for the preserved source inputs.

## Pinned build and execution

The current worktree is at commit `7a354e9a14d8faaefd8e958b381983e86a3c89d4`.
The build receipts were produced from the preceding
`74c62aee94a9e87f843093565e3a76fda7fd4fee` tree; the recorded source hashes
match the current tree. Both executables were built in fresh scratch
directories with the pinned Intel profile in `tests/intel_toolchain.sh`;
GNU/gfortran was not used.

| executable | scratch build | executable SHA256 |
| --- | --- | --- |
| `klps_anal_qbal.exe` | `scratch/upstream_balance_build.L8i5OV` | `0736cf776a1725801b37e5009d6cf09623f5b2dbf7f528cdad4818223ba1ab78` |
| `klps_anal_prep.exe` | `scratch/upstream_lapsprep_build.ZtPPiS` | `a32429a0c455bdee5911fbb391019531f577c45c04da5fe26ecba92f5876a831` |

The preserved source includes the historical actual `lco/262281300.lco`
(`516d07e511e2be90b47aad8bd0d0d1000e7f480b68f67d3f6cf1f78972e10d74`). Its
`derived.log` records the `lco COM` write and `LCO_PRODUCER_SUCCESS`. This is
legacy producer provenance for the comparison input; it is not a claim that
COM is a direct observation or that the case has new scientific approval.

## Results

The legacy LAPSPREP OFF run passed after creating its private output directory,
as the original operational caller does with `mkdir -p lapsprep/wps`. Before
that directory existed, the writer returned `WPS output failed` before its
`grid_type` header. The successful run is recorded in
`scratch/bpair_20260917/off/lapsprep.log` and ends with `LAPSPREP Complete.`
Its private WPS output is:

```text
scratch/bpair_20260917/input/lapsprd/lapsprep/wps/LAPS:2026-08-16_13:00
```

The actual QBAL stage was attempted first, as required by the LAPSPREP
`BALANCE=.TRUE.` product selector. Both attempts failed in the initial
continuity solve and published no balance products:

| attempt | result | evidence |
| --- | --- | --- |
| default iteration budget | exit 1; `LEIBP3` non-convergence; no output | `scratch/bpair_20260917/qbal.log` |
| private 2000-iteration probe | exit 1; `LEIBP3` non-convergence; no output | `scratch/bpair_20260917/qbal2000.log` |

The second attempt is a bounded diagnostic probe that changes only the LEIBP3
iteration budget from 200 to 2000. It does not change solver tolerances,
source inputs, or production settings, and does not establish a successful
producer run.
Consequently there is no actual `balance/{lw3,lt1,lh3,lq3}` set for an ON
LAPSPREP run, and the ON run is recorded as `NOT_RUN`. No before/after
numerical result exists yet.

The source path distinction remains explicit: LAPSPREP `BALANCE` only selects
legacy balance products written by QBAL/BALCON. It does not invoke the
canonical Cloud-BAL balance route. The canonical stage/shadow environment is
unset for this legacy comparison.

The reviewed Fortran comparator was built at pinned Intel O0 and O2 in fresh
scratch directories. Twelve self-comparisons cover actual full-domain HT, T3,
U3, V3, OM, and SH. Two controls add missing-coordinate metadata to a private
copy of the actual LT1 file; both reject even when both comparison inputs have
the same missing coordinate. All raw variable values in that copy are unchanged.
These are comparator checks, not an accepted balance pair. The final receipt is
`scratch/balance_compare_reviewed.m53voqfq/validation_manifest.json`, SHA256
`52346a308ea9fd409adf957cf38436525b4644adca8a0413ff47f4d1fe6d2cd9`.
An earlier SciPy control-writing attempt produced an unreadable private file;
it is excluded from successful control counts and retained in the receipt.

Further private instrumentation reproduced non-convergence at cell (45,208,4),
where influence is 4.31490e-4 and the terminal correction remains about 244.
This identifies where the solve stalls, not its physical cause. Conditioning
and componentwise compatibility remain unproven hypotheses; global forcing
sums alone cannot establish the latter. No forcing, boundary, acceptance, or
production-source change is made on that basis.

The FUA background `2622806000700.fua` has NetCDF reference time 06 UTC and
valid time 13 UTC: the 06 UTC cycle with a seven-hour lead. It matches the
13 UTC analysis valid time; it is not a 07 UTC valid-time fallback.

## Reproduction path

From the PR24 worktree, source the pinned profile and build the two producers:

```sh
. tests/intel_toolchain.sh
bash tools/build_upstream_producer.sh balance O0
bash tools/build_upstream_producer.sh lapsprep O0
```

Stage a private writable copy of `scratch/upstream13.Sfb68E`, preserving the
90-entry manifest. Add the operational `static/balance.nl` before QBAL, create
the private `lapsprd/balance/{lw3,lt1,lh3,lq3}` directories, and create
`lapsprd/lapsprep/wps` before LAPSPREP. Invoke each executable through its
generated `run_verified.sh` with `LAPS_DATA_ROOT` set to that private root and
with `CLOUD_BAL_STAGE_MODE`, `CLOUD_BAL_STAGE_CONTEXT`, and
`CLOUD_BAL_SHADOW_EXPERIMENT` unset. Run QBAL before the ON LAPSPREP attempt.

This record is a bounded execution/provenance report. It does not claim a
completed actual balance pair, numerical correctness, native startup
equivalence, scientific approval, or operational publication.
