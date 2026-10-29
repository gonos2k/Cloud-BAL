# Instruction-level candidate producers

The disassembly was taken from the original historical executable identified by `docs/evidence/cp02_preclamp_20261029/runtime/prepare_v2.json`, SHA-256 `de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168`. No rebuild was used. The continuous [instruction listing](disassembly_25f4300_25f4e60.txt) begins at `0x25f42ee`: `0x25f4300` is inside the instruction beginning at `0x25f42ff`. It covers the previously omitted `0x25f4680–0x25f49ef` interval. Listing SHA-256: `c30fa2f00ca1e16078be1b48a3e7ed186012e28f91e4c4230a4f52a01ba801ee`.

For the route through `0x25f4a59` to the observed `0x25f4e24` sum, the possible most recent writes to the low 32 bits of `xmm6` are:

* `0x25f4492`: `movss xmm6,[rax+r8*4]`, with `rax` loaded from `[rbx+0xc0]` at `0x25f448b`.
* `0x25f44be`: `mulss xmm6,xmm3`, executed only when the `jbe` at `0x25f44a7` is not taken. The instruction following it is `0x25f44c2`; otherwise control reaches `0x25f44f7` with the load value unchanged.

The `0x25f434d` branch to `0x25f4400` leads to that load and subsequently `0x25f481e`, which reaches `0x25f4a59` by either the `0x25f487e` taken branch or the `0x25f48bd` jump. From `0x25f4a59` through the `0x25f4ae3` branch and `0x25f4dcd` join to `0x25f4e24`, no instruction writes `xmm6`. Both the multiplier and the branch outcome must be captured per event to establish the actual writer; this listing alone does not establish which arm takes which branch. The load address denotes a binary frame slot and indexed buffer, not an identified source-level physical process.

The separate block beginning at `0x25f4689` has candidate writes `0x25f4364`, `0x25f43e3`, `0x25f47c5`, `0x25f4962` and `0x25f49f4`; it reaches `0x25f4b31`, rather than `0x25f4a59`, and cannot be attributed to a target event without control-flow evidence. An additional `xmm6` write at `0x25f4fc0` lies outside the requested listing and is included in the [supplement](disassembly_25f4fb0_25f4fc7.txt). Static alternatives must not be mistaken for observations of a target event.

At early capture points `r12` is not a stable qrs base; it is repeatedly repurposed and its low byte is modified at `0x25f4a92`. The later sum path loads `r12` from `[rbx+0x18]` at `0x25f4dcd`. A candidate-cell condition before that load is therefore `*(uint64_t *)(rbx+0x18) + 4*r8 == target_address`; validate that frame-derived address against the observed qrs target at the later store for each capture. This is an instruction-level address association, not proof of source-variable identity outside that observed event.

[Extraction receipt](extraction_receipt.json) records a read-only repeat of both commands, tool version, exit codes, executable hash and Build ID before and after, and byte-for-byte equality with both saved listings.
