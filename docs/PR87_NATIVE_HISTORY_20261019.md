# PR87 native-history endpoint contract

`tools/pr87_native_history.py` reads only closed WRF history files and emits
receipt-bound elapsed-time inventories and native state-field changes. Its
default complete window is elapsed 0 to 60 s at 60 s output intervals. A
shorter window requires the explicit `--allow-incomplete-window` option and a
run receipt marked `INCOMPLETE`; every history file hash must still match that
receipt. A selected history endpoint may precede the receipt's last completed
timestamp, as long as it follows the expected output schedule and is no later
than the requested endpoint. The tool does not open a running output file.

## Mass and inventory meaning

The hybrid dry layer pressure thickness follows the V42 call contract:

```text
dp_dry(k,i,j) = -(C1H(k)*(MU(i,j)+MUB(i,j))+C2H(k))*DNW(k)
area(i,j)     = DX*DY/(MAPFAC_MX(i,j)*MAPFAC_MY(i,j))
m_dry         = area*dp_dry/g
```

`module_em_pr85.F` forms the level carrier from `C1H*(MU+MUB)+C2H`; the
native-mass contract in `docs/NATIVE_MASS_FRAME_CONTRACT.md` records the
pressure-thickness and map-factor area relationship. Gravity is taken from
the checked compile-time constants receipt used with the pinned Intel profile
and module interface; the receipt hash and promoted gravity value are pinned.
It is not inferred from the run.

Each output time reports whole-file-native-grid and descriptive horizontal
interior inventories for `QVAPOR`, `QCLOUD`, `QICE`, `QRAIN`, `QSNOW`, and
`QGRAUP` in kg; `QNCCN`, `QNCLOUD`, `QNICE`, and `QNRAIN` as mass-weighted
number inventories; and `QIB` as a separate rime-volume inventory in m³.
Values use the dry hybrid mass recomputed at each endpoint. Total dry mass is
reported for each scope. Per-species and total differences from elapsed zero
are endpoint differences, not timestep source or transport ledgers. Extensive
per-cell total-water changes are formed before their signed sum, L1, maximum
cell, and column summaries; BG and each moment species have the same signed,
L1, maximum-cell, and column diagnostics. Moment changes are descriptive and
make no conservation claim. The horizontal interior is index `1:-1` on both
mass-grid axes and is not asserted to equal the KDM6 consumer footprint. It is
called the boundary-ring-excluded scope, not a ghost-cell mask.

## Native state descriptors and limits

At every endpoint the report summarizes changes from elapsed zero in total
pressure `P+PB`, mass-level geopotential (the adjacent-interface average of
`PH+PHB`), perturbation potential temperature `T`, and mass-point `U/V/W`
(adjacent-face averages). The 300 K offset in WRF `T` cancels in this change.
These are field descriptors only: they do not establish EOS temperature,
momentum, face-flux, divergence, or energy closure. `P+PB` is total EOS
pressure, not the dry mass coordinate. Staggered wind averages are for
description only and are not used to compute face transport.

The report makes no observation-fit claim and does not treat modeled
reflectivity as observed reflectivity. It does not infer missing output
species as zero, combine precipitation accumulators, or claim a closed water
budget. WRF history output existence, elapsed-time coverage, and hash binding
are checked separately from physical interpretation. Status is `ACCOUNTED` /
`PASS_SCOPED_DATA`; `physical_approval` is false, and state and observation
evaluations are `NOT_EVALUATED`.

## Invocation

From `scratch/pr87_two_step_20261016/Cloud-BAL`:

```sh
python tools/pr87_native_history.py \
  --history /path/to/wrfout_d01_... --history /path/to/wrfout_d01_... \
  --run-receipt /path/to/closed-run/receipt.json \
  --constants-receipt docs/evidence/pr87_followup_20261019/history/receipt.json \
  --output /path/to/native_history.json
```

Use `--endpoint-seconds` and `--history-interval-seconds` for other windows.
Incomplete windows must also pass `--allow-incomplete-window`.
