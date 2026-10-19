# PR87 V42 saved-state graupel activity audit

This read-only audit classifies the saved QG/BG snapshots from the OFF and COUPLED 60-second V42 runs against the ProgB pair, transient, and raw-density gates in the hash-pinned frozen `module_mp_kdm6.F`. It records all saved stages for timesteps 1–3. Timestep 3 ends at `PRE_KDM6`; no T3 `POST_KDM6` record exists.

## Source and inputs

| Artifact | SHA-256 |
| --- | --- |
| Frozen `module_mp_kdm6.F` | `bdb1882afed860068cecbb6c7b958eef0938cadbd4225222ba7522e28ecc071a` |
| OFF moment-stage trace | `b36fb364ea80f329370a2fc85d5177db56b1485be018f23174f9365fd6c3d868` |
| COUPLED moment-stage trace | `2cb10b7d6013dba56c73cf114fb59a364c833bd93c9a78e0c72fb6345934ec79` |

The audit pins the source hash and fails if it changes. The source gate is applied in this order: finite pair; exact `(QG,BG)=(0,0)` absent state; positive pair; joint transient when `QG<=REAL32(1e-9)` and `BG<=REAL32(1e-15)`; then finite `REAL64(QG)/REAL64(BG)` in inclusive `[100,900] kg m-3`. `DEN` is reported separately because ProgB's graupel density gate is QG/BG and does not consume the host dry-air density.

## T3 PRE_KDM6 result

There are 2,533,440 cells in each saved state.

| Arm | Absent | Positive pair passing QG/BG density gate | Joint transient | Unsupported pair | Unsupported density | Orphans, negative, or nonfinite QG/BG |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| OFF | 2,524,032 | 9,390 | 18 | 0 | 0 | 0 |
| COUPLED | 2,524,020 | 9,402 | 18 | 0 | 0 | 0 |

All positive pairs are inside the exact stored QG/BG cone. All T3 DEN values are finite and positive. The 18 transient cells in each arm are the source's joint low-mass/low-volume corner; they should not be described as active merely because their QG/BG density is cone-feasible.

The first transient cell is identical in both arms: active-relative `j,k,i=(30,16,115)`, absolute `i,j,k=(117,32,17)`. Its saved values are:

| Field | Value | REAL32 bits |
| --- | ---: | --- |
| QG | `8.0841117220537e-13` | `0x2b638c2a` |
| BG | `9.122162618311366e-16` | `0x268376d7` |
| DEN | `0.6773980855941772` | `0x3f2d69f6` |

Its QG/BG is about `886.2056 kg m-3`, within the [100,900] cone, while both values meet the separate transient cutoffs. This explains why cone-only classification misses it.

## Timestep 3 stage counts

| Arm | State | Active gate passes | Transient | Absent |
| --- | --- | ---: | ---: | ---: |
| OFF | PRE_RK | 4,415 | 0 | 2,529,025 |
| OFF | RK stage 1 | 9,360 | 65 | 2,524,015 |
| OFF | RK stage 2 | 9,376 | 48 | 2,524,016 |
| OFF | RK stage 3 | 9,390 | 18 | 2,524,032 |
| OFF | PRE_KDM6 | 9,390 | 18 | 2,524,032 |
| COUPLED | PRE_RK | 4,418 | 0 | 2,529,022 |
| COUPLED | RK stage 1 | 9,372 | 65 | 2,524,003 |
| COUPLED | RK stage 2 | 9,386 | 48 | 2,524,006 |
| COUPLED | RK stage 3 | 9,402 | 18 | 2,524,020 |
| COUPLED | PRE_KDM6 | 9,402 | 18 | 2,524,020 |

No unsupported pair or density was found in any saved state across timesteps 1–3. The JSON receipts contain the full per-stage status counts, first positions by status, float32 bit patterns, and density summaries.

## Interpretation and limits

This audit establishes that a cone-feasible transient pair exists in T3 PRE_KDM6 in both arms and that the saved state passes the source's pair/transient/raw-density gates for the other positive pairs. It does not identify which of the 18 cells triggered the native fatal. The snapshot does not contain `progb_status`, ProgB's derived gamma/PSD fields, or the fatal cell context, so `ACTIVE_GATES_PASS` means the saved inputs pass the reproduced source gates, not that native `PROGB_PSD_ACTIVE` was observed. The root follow-up's failure-context capture is needed to establish the actual cause.

No model rebuild or runtime was performed. Graphify was not refreshed in this bounded audit: the maintained graph has zero additions/removals from this batch, and these new files are not represented in its current snapshot. Graph status does not change the runtime conclusion.

## Files

- `OFF_60s_v42_activity.json` — OFF source-bound per-stage receipt.
- `COUPLED_60s_v42_activity.json` — COUPLED source-bound per-stage receipt.
- [`pr87_graupel_activity_audit.py`](../../../../tools/pr87_graupel_activity_audit.py) — reusable classifier and CLI.
- [`test_pr87_graupel_activity_audit.py`](../../../../tests/test_pr87_graupel_activity_audit.py) — focused unit tests.
