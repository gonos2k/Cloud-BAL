# KDM62D optional argument setup at the caller

## Artifact identity

This is a read-only disassembly of the same no-DWARF executable recorded in
[`binary_identity.txt`](binary_identity.txt): SHA-256
`de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168`, BuildID
`8baf18e56c6a582ccc7a27fb4d1653ad18fb8810`. The exact captured range is in
[`kdm6_kdm62d_argument_setup.objdump.txt`](kdm6_kdm62d_argument_setup.objdump.txt).
Command: `objdump -d -Mintel --start-address=0x25e0d10 --stop-address=0x25e1008 <wrf.exe>`;
GNU objdump 2.42.

## Findings

The KDM6 caller reserves `0x1c0` bytes before the KDM62D call at `0x25e0fe4`.
At the call instruction, stack argument 7 is at caller `$rsp+0`; arguments 59
through 62 occupy caller `$rsp+416,+424,+432,+440` (frame offsets
`0x1a0..0x1b8`). At callee entry, add 8 bytes for the return address, so the
same arguments are at `$rsp+424,+432,+440,+448`.

Immediately before storing these four values to the outgoing stack slots, the
caller forms pointers with null-preserving conditional moves:

- `0x25e0d6d..0x25e0d74`: base from `[rbp+0x140]`, offset only if nonzero;
- `0x25e0d7b..0x25e0d82`: base from `[rbp+0x148]`, offset only if nonzero;
- `0x25e0d86..0x25e0d94`: base from `[rbp+0x170]`, offset only if nonzero;
- `0x25e0d98..0x25e0da5`: base from `[rbp+0x178]`, offset only if nonzero.

The resulting values are placed into caller stack slots `0x1a0`, `0x1a8`,
`0x1b0`, and `0x1b8` at `0x25e0fa5..0x25e0fbc`, then passed as KDM62D
arguments 59–62. The adjacent KDM6 candidate source names those positions
`snow`, `snowncv`, `graupel`, and `graupelncv`, and declares those KDM6 fields
optional. This makes 59–62 the statically supported nullable candidate slots.

## Limitation

The failed HYDRO capture rejected the internal call before recording any raw
argument pointers. It therefore does not establish which argument was zero, or
that the actual zero was one of 59–62. Runtime receipts must preserve all 62
raw pointer values before applying null checks. Any pointer used for mapping or
sampling (including arguments 1–6 and 32, 39–56) must be checked nonzero before
dereference. No scientific state or process attribution follows from this
static caller setup.

## Correction from the v2 HYDRO entry receipt and callee audit

The second capture recorded a broader null-position set on ranks 0, 2–7:
`14,17,18,21,32,39,40,41,42,43,44,47,48`. Those positions do not include
59–62. Therefore the four optional-pointer guards above do not explain the
observed null set; the earlier inference that they were the only nullable
candidate slots was incorrect. The exact v2 receipts are in the root-owned
HYDRO capture directory; the failure was at KDM62D entry before any watchpoint
was armed.

The caller's stack setup at `0x25e0d10..0x25e1008` leaves outgoing slots for
those zero positions unwritten, and the callee disassembly has no references to
the corresponding entry stack locations. The arguments therefore appear
unused by this linked routine. This is an instruction-level observation, not a
source-level identification of their semantics.

The bounds needed for selected `i,k` mapping remain present and are consumed by
the callee. With the candidate positional names from the adjacent source, these
are `ims,ime` at args 45–46, `kms,kme` at 49–50, `its,ite` at 51–52, and
`kts,kte` at 55–56. At the KDM62D entry frame pointer, the loaded pointer slots
are respectively `[rbp+0x140]`, `[rbp+0x148]`, `[rbp+0x160]`, `[rbp+0x168]`,
`[rbp+0x170]`, `[rbp+0x178]`, `[rbp+0x190]`, and `[rbp+0x198]`; each is then
dereferenced for a 32-bit bound. These nonnull positions agree with the v2
raw pointer vectors.

Candidate arg32 (`lat`) is null in the v2 receipts and has no corresponding
callee stack-slot reference. Do not use it to identify j. The current-column
`q` pointer can instead be mapped against public `q` using the candidate
Fortran layout: subtract the outer `q` base, require exact divisibility by
`4*Nxmem*NkMem`, and add the resulting j offset to outer `jms`. Then validate
that j against outer memory and tile bounds. This still depends on validating
that the observed inner `q` pointer aliases the expected public Q row; runtime
capture must retain both addresses and the calculation inputs.

The callee-entry excerpt is
[`kdm62d_entry_bounds.objdump.txt`](kdm62d_entry_bounds.objdump.txt), from
`objdump -d -Mintel --start-address=0x25e2490 --stop-address=0x25e2660 <wrf.exe>`.

The v2 failure receipts supporting the recorded null-position vector are
external to this binary evidence subdirectory and were observed at
`/var/tmp/cp02-thermo-response-20261029-1xnf2120/HYDRO/capture/`:

- rank 0 receipt SHA-256 `a0fb957b0e099653933018610e6952cf788c9167fb6780a14e7a4818cd270b76`;
- rank 3 receipt SHA-256 `13fc6dc6fc9734a52204039fb465b463d7cd1316ce7d7546fefe78106d4ef7e2`.

Both show null positions `14,17,18,21,32,39,40,41,42,43,44,47,48` and no
null among 59–62. They are failed instrumentation receipts, not a successful
QR-write capture.
