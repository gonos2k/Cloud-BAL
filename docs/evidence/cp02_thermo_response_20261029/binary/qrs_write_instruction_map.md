# KDM62D QR write instruction map

## Binary and static disassembly

The mapping below is for the no-DWARF executable pinned in
[`binary_identity.txt`](binary_identity.txt), SHA-256
`de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168`, BuildID
`8baf18e56c6a582ccc7a27fb4d1653ad18fb8810`. Exact Intel-syntax excerpts are in
[`kdm62d_qrs_write_context.objdump.txt`](kdm62d_qrs_write_context.objdump.txt),
produced with GNU objdump 2.42. The sequence remains machine-code evidence;
there are no source-line or variable DIEs in this executable.

## Watchpoint observations from the incomplete v5 HYDRO attempt

The root-owned v5 run was not accepted as a completed capture because its
rank-acknowledgement barrier did not settle all rank receipts. Its rank 1 and
rank 3 records nevertheless contained the same two QR writes at P05_00 and
P01_00 respectively. Treat these only as provisional event-to-instruction
corroboration, not as the final runtime finding. Raw records:

- rank 1: `/var/tmp/cp02-thermo-response-20261029-r_7ikeaw/HYDRO/capture/raw_hydro_first_inner_rank1_pid23165.json`, SHA-256 `d7f639e92100de67c8fd05b9f651f61d8e2ecc19d6bf49339a9b60ecbdabbadd`;
- rank 3: `/var/tmp/cp02-thermo-response-20261029-r_7ikeaw/HYDRO/capture/raw_hydro_first_inner_rank3_pid23158.json`, SHA-256 `cb1d2a83bb6697fd6b668e1f33c89bc2a600bf062247cdba8b4bceda85a04114`.

The first qrs write event at each target had a positive decrease:

- P05_00: raw REAL32 `40e89439` (0.00028401799499988556) to `ba049439` (0.00028232281329110265).
- P01_00: raw REAL32 `6382a038` (7.653680950170383e-05) to `f954a038` (7.645221921848133e-05).

Both events report PC after the write `0x25e9155`; the preceding instruction at
`0x25e914f` is `movss DWORD PTR [r11+r10*4],xmm4`. Immediately before it, the
machine code calculates `xmm4` by subtracting a value loaded through `[rax+r10*4]`
from an existing scalar, adding `xmm7`, and clamping with `maxss xmm4,xmm10`.
The watchpoint confirms this store changes the selected local `qrs` address.
No register-to-source map identifies the `rax` value or the physical process
term, so the instruction is not assigned a process name here.

The first exact-zero qrs write was also consistent in both targets. The event
PC after write was `0x25f4e5e`; the writing instruction at `0x25f4e58` is
`movss DWORD PTR [r12+r8*4],xmm9`. The immediately preceding instructions zero
`xmm5`, apply `maxss xmm9,xmm5`, and store that result to the watched qrs word.
The branch at `0x25f4ae3` reaches this block at `0x25f4dc0` when the preceding
`comiss xmm15,0` and `setp`/`setne`/`or` sequence establishes ordered equality:
`xmm15` is exactly zero on that path. This identifies the machine-code clamp
and branch condition; it does not identify a physical tendency or named
microphysics process.

A static register trace shows that one incoming path loads `xmm15` at
`0x25f4476` from `[r10+r8*4]`, where `r10` comes from `[rbx+0x160]` and that
frame pointer is formed as `[rbx+0x850]+rcx` at `0x25f3c52`. The `[rbx+0x850]`
slot is a compiler-managed local allocation pointer. The value may be scaled
and written along earlier branches before the equality test. No DWARF or linked
symbol maps that scratch array to a physical species or process term; that
mapping remains open.

The complete v6 receipt supersedes these v5 observations for accepted runtime
claims. It should be checked for the same target, old/new bytes, and PCs before
promoting this map beyond provisional corroboration.

## Accepted v6 HYDRO confirmation

The root accepted v6 capture only after all eight rank receipts reached
`all_ranks_settled`; there were no failures. The accepted raw records are:

- rank 1, P05_00: `/var/tmp/cp02-thermo-response-20261029-tnj1g3a6/HYDRO/capture/raw_hydro_first_inner_rank1_pid29198.json`, SHA-256 `7a0c8e079e99ed0f1495ff58158b827d45b68e6bf1674888dae0966a83488189`;
- rank 3, P01_00: `/var/tmp/cp02-thermo-response-20261029-tnj1g3a6/HYDRO/capture/raw_hydro_first_inner_rank3_pid29187.json`, SHA-256 `d4f50329068a48c65c1d25bbcf41e8ff90b02778bbc22473c6a636bc951a6918`.

The accepted v6 records confirm the same first decreases and subsequent zero
stores at the same PC-after values and with identical raw REAL32 before/after
bytes as the v5 provisional observations above. Therefore the instruction map
is now tied to an accepted, settled HYDRO capture. The v5 note remains only as
history of the acknowledgement-race attempt.

This confirms the captured QR writes at these two sampled targets. It does not
identify why the upstream computation generated its values, establish a named
physical process, or prove a whole-column conservation result.

Archived compressed accepted records are in
[`captures/HYDRO/`](../captures/HYDRO/): rank 1 gzip SHA-256
`3ed97a67219678070776352c65cb6029e2df566cca3380a5e95902e46d8d6c85`, rank 3
gzip SHA-256 `474c8dc204c3d2a95b8a84643529cff8a3170d02b8a54ae80d94bdd9bdd8e637`.
The uncompressed hashes above pin the underlying JSON payloads.
