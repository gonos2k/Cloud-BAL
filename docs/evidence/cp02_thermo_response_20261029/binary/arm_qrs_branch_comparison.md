# First KDM62D QR-buffer write comparison across arms

## Accepted capture scope

This comparison reads the accepted first-inner-call captures under
[`captures/`](../captures/). All three arm receipts record eight ranks and an
intentional first-call stop; each raw rank record reached `all_ranks_settled`.
The executable is the original ELF pinned in
[`binary_identity.txt`](binary_identity.txt). Captured array labels such as
`qrs`, `q`, `qci`, and `t` follow the positional map from adjacent source and
are candidate names; at entry, the selected qrs/qci/q/t words were checked
against the public QR/QC/Q/TH×PII arguments where applicable.

Selected points are P05_00 `(i=163,j=70,k=8)`, rank 1, and P01_00
`(i=163,j=73,k=8)`, rank 3. For each target, hardware write events establish
actual writes. An event PC is the PC after the watched write; the instruction
that performed it is the preceding instruction shown in the saved nearby
instruction sequence and confirmed in
[`kdm62d_qrs_write_context.objdump.txt`](kdm62d_qrs_write_context.objdump.txt).

## QR and Q writes in the shared block

| Target | Arm | First qrs write at `0x25e914f`, before → after | Q write at `0x25f4df9`, ΔQ | qrs write at `0x25f4e58`, before → after |
| --- | --- | ---: | ---: | ---: |
| P05_00 | OFF | 4.6017105e-4 → 4.5700453e-4 | +4.5700371e-4 | 4.5700453e-4 → 0 |
| P05_00 | HYDRO | 2.8401800e-4 → 2.8232281e-4 | +2.8232299e-4 | 2.8232281e-4 → 0 |
| P05_00 | LIQUID | 2.8331656e-4 → 2.8162202e-4 | +8.5085630e-6 | 2.8162202e-4 → 2.7311346e-4 |
| P01_00 | OFF | 1.0422405e-4 → 1.0409940e-4 | +1.0409951e-4 | 1.0409940e-4 → 7.2759576e-12 |
| P01_00 | HYDRO | 7.6536810e-5 → 7.6452219e-5 | +7.6452270e-5 | 7.6452219e-5 → 0 |
| P01_00 | LIQUID | 7.6386044e-5 → 7.6304190e-5 | +7.1303919e-5 | 7.6304190e-5 → 5.0012022e-6 |

The post-write PC values are the same in every arm: the first qrs write reports
`0x25e9155` and the later qrs write reports `0x25f4e5e`. Thus all three arms
reach the same store at `0x25f4e58`; their stored qrs values differ. At that
block, the code computes a scalar in `xmm9`, applies `maxss xmm9,0`, and stores
the result to the watched qrs word. OFF and HYDRO store exact zero at P05_00;
LIQUID stores a positive remainder. At P01_00, HYDRO stores zero, LIQUID stores
a positive remainder, and OFF first stores `7.28e-12` then writes exact zero
at the separate later PC `0x25f7270`.

The store alone does not identify the predecessor: the `je 0x25f4dc0`
at `0x25f4ae3` and the nonzero path via `0x25f4ae9` both converge at
`0x25f4dcd`. The comparison at `0x25f4ac8` and flag setup make the `je`
taken for ordered `xmm15 == 0`. At the convergence, `movaps xmm10,xmm15`
at `0x25f4dd1` retains that operand; the instructions through the watched
store do not modify `xmm10`. All six target watchpoint records have zero in
its low REAL32 lane. Together with that instruction sequence, this supports
the zero comparison and taken `je` for these six samples. The original
same-store-only inference was insufficient. [Independent check](../../cp02_preclamp_20261029/science/independent_check.json).

The event #2 Q increment and event #3 qrs reduction are close in magnitude in
these REAL32 words. For example at P05_00 in LIQUID both have magnitude
`8.5085630e-6`; at P05_00 in HYDRO they are `2.8232299e-4` and
`2.8232281e-4`. These are paired storage deltas only. They are not a water-mass
closure, a per-column conservation result, or a complete process budget.

## Temperature buffer writes

Event #4 follows the shared qrs block and writes the candidate local `t`
buffer at PC-after `0x25f4293`; the writing instruction at `0x25f428d` is `movss DWORD PTR [rdi+r8*4],xmm0`, following `subss xmm0,xmm6`. Its raw REAL32 changes are:

| Target | OFF Δt | HYDRO Δt | LIQUID Δt |
| --- | ---: | ---: | ---: |
| P05_00 | −1.1006165 | −0.6799316 | −0.0205078 |
| P01_00 | −0.2510376 | −0.1843567 | −0.1719971 |

These are observed buffer differences. The source candidate computes `t=th*pii`,
but the linked executable has no DWARF to verify that source identity or attach
physical units to this local buffer. No conversion to public TH or Kelvin is
made here.

## Later Q/QC exchanges

Subsequent write events are distinct stores and are listed in each rank JSON.
At P05_00, the later HYDRO event #5 increases Q by `1.3723411e-4` while event #6
decreases qci by `1.3723486e-4`; event #7 changes t by `−0.3305054`. At the
same P05_00 sites in OFF and LIQUID, the later event pairs instead decrease Q
and increase qci, with positive t changes. These are additional captured local
buffer changes; the different store PCs do not provide a process name by
themselves. The complete sequence, including all selected-corner events, stays
in the accepted per-rank records.

## Provenance

Compressed rank records and their SHA-256 values:

- OFF P05_00/rank 1: `captures/OFF/raw_off_first_inner_rank1_pid30347.json.gz`, `edef45811030ea45efecfe7fdc8008f7f5ec0f89e1d96ed7e06afaa5c6f5319f`.
- OFF P01_00/rank 3: `captures/OFF/raw_off_first_inner_rank3_pid30341.json.gz`, `ed4a83bc0fcb3ec1d7b826872b3dc4b72094fc2d59bcb2ef958725f4362dbfcf`.
- HYDRO P05_00/rank 1: `captures/HYDRO/raw_hydro_first_inner_rank1_pid29198.json.gz`, `3ed97a67219678070776352c65cb6029e2df566cca3380a5e95902e46d8d6c85`.
- HYDRO P01_00/rank 3: `captures/HYDRO/raw_hydro_first_inner_rank3_pid29187.json.gz`, `474c8dc204c3d2a95b8a84643529cff8a3170d02b8a54ae80d94bdd9bdd8e637`.
- LIQUID P05_00/rank 1: `captures/LIQUID/raw_liquid_first_inner_rank1_pid32018.json.gz`, `7db8bab378cb4f9a898efd3e653945d1c330b3f3d21f6b732965a19ced679330`.
- LIQUID P01_00/rank 3: `captures/LIQUID/raw_liquid_first_inner_rank3_pid32015.json.gz`, `0a7f941a3e9a1c92026bcbfb4741e204d6fd39d27b09b1c2120901ee38338e47`.

This comparison does not identify the compiled source-level process that formed
the clamp input, establish a whole-column water/energy budget, or prove a
forecast-level cause.

## Reproduction

Run `python compare_write_events.py` from the repository root. The script
validates each compressed capture hash, all-ranks-settled status, arm/rank,
binary/helper/selection hashes, and selected point coordinates before
recomputing every event delta from its raw REAL32 bytes. It writes
[`arm_qrs_branch_comparison.json`](arm_qrs_branch_comparison.json) and
[`arm_qrs_branch_comparison.csv`](arm_qrs_branch_comparison.csv).

- Script SHA-256: `ccf3438973645f63fe48bfdaa3a4ccc142db360b7889e683aaa753f8b2bf3f21`.
- JSON SHA-256: `041a0617d32bb5496ea13e157abe36897eaa91e7b398d12dc34fc4d66bda0f2c`.
- CSV SHA-256: `943006253c811b441b568ef52c19466cc5000b361a3868a2f2c6d3e60539bcca`.
