# CP02 P05 QR response capture plan

## Goal

Explain the first-call QR endpoint response at the selected P05 column by
bracketing the internal KDM6 working-array operation and its copyback to the
outer KDM6 arguments. The capture is an observation of one execution of the
existing binary. It will not identify the exact source revision, assert a
physical process, or claim conservation or forecast skill.

## Known executable and outer-boundary contract

- Binary SHA-256: `de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168`.
- ELF BuildID: `8baf18e56c6a582ccc7a27fb4d1653ad18fb8810`.
- Existing outer KDM6 entry/return PCs: `0x25df680` and `0x20c3722`.
- Existing 77-argument ABI map is documented in
  `docs/evidence/cp02_wrf_first_call_20261029/abi/README.md`. The six register
  arguments are followed by 71 pointer arguments on the stack. Argument names
  are candidate labels from co-located source; the executable has no DWARF.
- Existing CP02 controls capture 624 unique points (16 horizontal points by
  39 levels) from OFF, HYDRO, and LIQUID. The new stage must reuse the exact
  selection file and verify its recorded SHA-256 before launch.

The endpoint contrast motivating the probe is P05_00, `(i=163,j=70,k=8)`:

| Arm | First KDM6 entry QR | First KDM6 return QR |
| --- | ---: | ---: |
| OFF | 4.6017105341888964e-4 | 0 |
| HYDRO | 2.8401799499988556e-4 | 0 |
| LIQUID | 2.8331656358247972e-4 | 2.7311345911584795e-4 |

These are captured endpoint values and do not identify where or why QR changes.
The first-call per-arm endpoint is already retained in the prior CP02 evidence.
Capture chronology is ordinal and runtime-observed: record each rank's raw
`itimestep` and `delt`; the prior outer captures observed timestep 1 and
`delt=20`, but the new helper must validate rather than assume them. Do not
label the event with a model clock or RK stage. The parent receipt may record
stage start/end UTC as operational timestamps, separate from model time.

## Candidate internal bracket

Static binary inspection found the KDM6 CALL instruction at `0x25e0fe4`, its
next instruction at `0x25e0fe9`, and the KDM62D function entry at `0x25e2490`.
The six pointer values in registers at the call setup are loaded
from `[rbx+0x218]`, `[rbx+0x20]`, `[rbx+0x180]`, `[rbx+0x188]`,
`[rbx+0x178]`, and `[rbx+0x170]`. Co-located source labels these candidate
arguments `(t,q,qci,qrs,nci,nrs,...)`; exact compiled-source identity is not
established.

The requested capture scope is the full 624-point outer KDM6 entry/return for
the first call on all eight ranks of each arm, plus KDM62D entry/return at the
P01 and P05 four-corner columns at `k=8` (eight horizontal coordinates, two
profiles). Stop each rank only after its first outer KDM6 return and after all
eight ranks have settled successfully. Record the six pointer values and
selected raw REAL*4 state from candidate `qci` and `qrs` buffers at both
internal boundaries, as well as actual outer `qr`, `qc`, `q`, `th`, `pii`,
`nc`, and `nr` values at outer entry/return. Keep raw bytes authoritative; include finite/value
decoding only as a convenience. Preserve PCs, return PCs, stack pointer,
backtrace, all relevant registers, bounds/index registers if they can be
established from binary instructions, rank, PID, arm, observed timestep and
`delt`.

The targeted hardware WRITE watchpoints are on the local KDM62D working
buffers for P05_00 `(i=163,j=70,k=8, rank 1)` and P01_00
`(i=163,j=73,k=8, rank 3)`, armed only during the matching internal KDM62D
interval. Binary inspection reports a 62-argument inner ABI: `rdi=t`,
`rsi=q`, `rdx=qci`, `rcx=qrs`, `r8=nci`, and `r9=nrs`. The helper retains all
62 pointer words and each null position before validation.

The captured binary has null pointers at positions 14, 17, 18, 21, 32, 39–44,
47, and 48. Candidate labels for these slots are not used as runtime facts.
Domain bounds (39–44), memory j bounds (47–48), and the candidate current-j
pointer (32) are unavailable. Memory i/k bounds are at 45, 46, 49, and 50;
tile i/j/k bounds at 51–56 are required. The helper
requires the first six array pointers and memory i/k plus tile i/k bound
pointers to be nonnull; it records unavailable bounds rather than dereference
null pointers. Any null at an unlisted position fails the stage.

Because the current-j pointer is null, the helper derives current `j` from the
candidate q slice pointer: `(q_inner-q_outer)/(4*Nxmem*NkMem)`, added to outer
`jms`. It requires nonnegative exact row alignment, a result inside outer
memory and tile j bounds, and equality of the candidate q pointer to the
calculated row base. This is a runtime pointer relationship; it does not
assert the source meaning of a procedure argument.

The candidate work arrays use Fortran order `(its:ite,kts:kte,species)`. On
their first species planes the float offset is `(i-its)+(k-kts)*Nx`, where
`Nx=ite-its+1`. The q slice uses `(i-ims)+(k-kms)*Nxmem`, where
`Nxmem=ime-ims+1`. Local `t`, `qci`, `qrs`, `nci`, and `nrs` use tile bounds.
All labels and dimensions remain provisional; the binary has no DWARF.

Before arming a watchpoint, verify from runtime pointers and raw bytes that the
candidate `qrs` and `qci` values at the computed selected offsets match outer
`qr` and `qc` respectively at KDM6 entry; verify candidate `q` at the expected
offset against outer `q`, and candidate `t` against REAL32(`th*pii`) within an
explicit rounding-aware contract. KDM6 may have processed neighboring `j`
slabs before a selected slab, so any mismatch fails closed; do not assume those
operations leave the selected `q` unchanged. Verify available candidate bounds
include the selected point, pointer-derived `j` equals the selected coordinate,
and the owner mapping is unique. Any failed or ambiguous check aborts the inner
probe before setting watchpoints.
For each write event, capture candidate `qrs/qci/q/t/nci/nrs` raw bytes, all
registers, breakpoint PC, backtrace, and a bounded instruction window around
the watchpoint. Cap the trace at 256 events; overflow is a stage failure. A
watchpoint PC is the instruction after the store and must not be called the
producer instruction without disassembly confirmation.

KDM6 copies the local work arrays back to outer arrays after KDM62D returns,
so outer-array watchpoints cannot identify writes inside the internal call.
The internal work-array watchpoints are the intended probe. If runtime
verification cannot establish their address-to-point relation, do not arm
them or infer a process; preserve valid outer and internal boundary records
with the write trace marked unavailable.

This bracket can establish whether candidate working-array values changed
across the KDM62D call, and whether outer QR differs before and after KDM6. It
does not by itself identify the specific arithmetic branch or prove a source
line's physical meaning.

## Hard gates before a GDB script or model launch

1. Recheck the executable SHA-256 and BuildID against the values above. Any
   mismatch aborts before inferior launch.
2. Recheck that KDM6 entry/return (`0x25df680`, `0x20c3722`), KDM62D call
   instruction (`0x25e0fe4`), KDM62D entry (`0x25e2490`) and return
   (`0x25e0fe9`) resolve as expected in that exact binary. Any mismatch aborts;
   do not search for a substitute address during capture.
3. Confirm from existing binary evidence the KDM62D entry/return PCs and
   six-register pointer ABI. Derive `j` only from exact row alignment of the
   current q pointer against the outer q base and captured outer bounds.
   Compare available inner i/k and tile bounds with the outer bounds and use
   raw values to prove a unique point mapping before watchpoint installation.
   Missing bounds remain unavailable; never fill them from source or call
   order.
4. Validate the exact 624-point selection, unique coordinates, hash, and
   current memory/tile ownership at runtime. Sample a point only on its owning
   tile. Missing, multiply-owned, or halo-only target samples fail the stage.
5. Use the same pinned Intel profile and launch setup as the accepted CP02
   controls. Do not build a binary. The parent owns any model launch.
6. Give each arm a fresh stage directory. Never merge files across arms or
   runs. Write raw files to temporary names and atomically finalize only after
   every expected rank has completed the required entry/return sequence.
7. Bind every capture and derived receipt to SHA-256 values for the executable,
   GDB helper, selection, run inputs/receipt, and all per-rank raw files.
   Hash verification, expected rank count, arm identity, point ownership, and
   event order are all fail-closed gates. Preserve failure markers and leave
   no successful completion receipt if any gate fails.

## Metadata contract

The stage receipt must contain: stage ID; arm; status; binary path, size,
SHA-256, and BuildID; GDB version; pinned Intel environment/profile identity;
helper SHA-256; selection SHA-256 and point count; run-input receipt hash;
expected and observed rank counts; per-rank PID, event sequence, observed
`itimestep`/`delt`, target owner bounds, breakpoint PCs and return PCs; hashes
and sizes of raw files; parent-recorded stage start/end UTC; and any unavailable
mappings or failure reason. UTC timestamps are operational metadata, never a
substitute for the model clock.

Each raw record must retain the exact address, PC, rank/PID, event ordinal,
argument/register values, relevant stack bytes, selected-point coordinates,
raw four-byte values, and bounds used for every dereference. Candidate ABI
labels must be marked as such. Do not store decoded nonfinite floats as JSON
NaN/Infinity; retain raw bytes, `finite=false`, and a null decoded value.

The reducer must consume only a complete, hash-valid stage receipt. It must
reject a missing rank, duplicate event, wrong breakpoint/caller PC, changed
binary/helper/selection/input hash, ambiguous point owner, invalid memory
bounds, or incomplete internal bracket without replacing an existing output.

## Ownership and sequence

| Owner | Work |
| --- | --- |
| `thermo_binary127` | Complete binary-only confirmation of the KDM62D call shape, return PC, and whether `(i,j,k)` can be mapped from machine state. No runtime launch. |
| `thermo_capture127` | Maintain this plan; after parent acceptance and the binary gates, implement the minimal GDB helper and raw-record contract. No model launch or source edit. |
| Parent (`/root`) | Approve the capture contract, freeze run/input receipts, and own all model launches and pinned Intel environment decisions. |
| Independent reviewer | Check exact-binary gates, noninterference, raw-byte/hash binding, rank/owner failure paths, and interpretation limits before capture outputs are used. |

Sequence: binary gate review → parent acceptance of this plan → helper
implementation → static helper checks → isolated fixture checks → parent-owned
launch for OFF/HYDRO/LIQUID → receipt and raw-hash audit → independent review
→ reduction only if all three arm stages pass. No compile or model launch is
included in this plan-writing stage.

## Validation strategy for the helper

- Static checks: Python syntax/compilation only; verify all breakpoint and
  caller-return constants, binary hash, selection hash, and output stage ID
  are explicit constants or receipt-checked inputs.
- Fixture checks: decode crafted finite, signed-zero, subnormal, NaN, and
  infinity REAL*4 bytes; verify raw bytes survive unchanged and JSON remains
  strict. Verify KDM62D entry/return events pair by rank/PID/call ordinal.
- Fail-closed checks: reject wrong binary hash, wrong selection hash/count,
  wrong PC/return PC, missing rank, duplicate rank event, invalid bounds,
  absent or ambiguous owner, missing internal return, and modified raw file.
  Each failure must leave a successful receipt absent and preserve any prior
  final artifact byte-for-byte.
- Noninterference review: no inferior calls, memory writes, convenience
  variables that alter model state, or output writes into the model run
  directory. GDB software breakpoints are the only expected text patches.
- Runtime acceptance, owned by the parent: all three arms, all expected ranks,
  exact existing binary, 624 selected points, and complete outer/internal
  event brackets. A controlled debugger stop is diagnostic only; it is not a
  completed forecast.

## Open evidence limits

The binary has no DWARF source/argument metadata. `qci`, `qrs`, their units and
indexing, the proposed avedia/di82 transfer, and every source-line attribution
remain candidate-source labels until independently bound to the compiled
image. The probe can localize changes to call boundaries only if exact runtime
index and owner mapping is established from the binary and captured bounds.
Graph freshness, if later updated, will not establish runtime or scientific
validation.
