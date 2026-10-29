# CP02 thermodynamic trace and historical binary boundaries

Read-only static binary/source inspection and source-input extraction, 2026-10-29.
No executable was launched, no inferior was run, no GDB capture was performed,
and no binary was built. The raw input extraction covers the 624 selected
P01/P05/P09/P13 corner-level keys for each historical OFF/HYDRO/LIQUID arm.

## Evidence and identity limits

The inspected executable is the retained historical file
`Cloud-BAL/scratch/cp02_host_unit_contract_x3bcr8ui/host/main/wrf.exe` with
SHA-256 `de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168`,
BuildID `8baf18e56c6a582ccc7a27fb4d1653ad18fb8810`, 71,834,200 bytes, and an
x86-64 ELF `.symtab`. The SHA-256 matches PR125/PR126 run receipts. The ELF has
no `.debug_*` section and no DWARF argument or source-line records.

Co-located source candidates are hash-pinned in `source_binary_sha256.txt`:
`module_microphysics_driver.F` (`bcac9818…c03f4`) and `module_mp_kdm6.F`
(`49cf8b0e…7187ca`). Their hashes establish which files were read, not that
they produced this executable. Machine addresses, PCs, register/stack placement,
and symbol targets below come from the executable; parameter names and process
labels from adjacent source remain candidates.

## Initial inputs to observed public KDM6 arguments

`initial_thermo.csv` records direct `wrfinput_d01` samples for every point,
corner, and native level retained by PR126's `selected_initial_fields.csv`.
`initial_thermo_receipt.json` binds all three input files to the exact
PR126 `copy_manifest.json` hashes and checks selected QVAPOR/QCLOUD/QRAIN
values against the PR126 extraction. Before/after source-file hashes agree.
The CSV includes raw `T`, `THM`, perturbation pressure `P`, base pressure `PB`,
and `T00` as a separate metadata column. The WRF attributes describe `T` as
“perturbation potential temperature theta-t0”; `THM` is described as either
perturbation moist potential temperature or perturbation dry potential
temperature. `T00=290 K` is retained separately and is not added to either
field.

At P05 corner 11 (`i=164,j=71,k=8`), the initial arrays and first public KDM6
call were:

| Arm | Initial QVAPOR | Initial QCLOUD | Initial QRAIN | Initial T | Initial THM | Initial P / PB | KDM6 entry q / qc / qr / th | KDM6 return q / qc / qr / th |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| OFF | 0.014976509 | 0.0006143855 | 0.0003779881 | 2.687408 | 9.978455 | 419.547 / 89296.93 | 0.015007119 / 0.0006124734 / 0.0003968264 / 302.6768 | 0.015570743 / 0.0004437023 / 0 / 301.2756 |
| HYDRO | 0.014976509 | 0.0006143855 | 0.0002384547 | 2.687408 | 9.978455 | 410.086 / 89296.93 | 0.015006704 / 0.0006125246 / 0.0002487532 / 302.6774 | 0.015565231 / 0.0003016735 / 0 / 301.2888 |
| LIQUID | 0.015528822 | 0.0000620464 | 0.0002375708 | 1.245819 | 8.769745 | 400.578 / 89296.93 | 0.015564177 / 0.0000589619 / 0.0002478432 / 301.2266 | 0.015545548 / 0.0000775910 / 0.0002467751 / 301.2730 |

The initial NetCDF metadata gives QVAPOR/QCLOUD/QRAIN units `kg kg-1`, T/THM
units `K`, and P/PB units `Pa`. `P` and `PB` are kept as separate input fields.
The numeric KDM6 `q/qc/qr/th/p` candidates are copied from public-call capture
records without assigning units from the input metadata. The runtime KDM6 `p`
values in PR126 are captured independently; this report does not assert a
compiled transformation from initial `P/PB` to that argument. Likewise, runtime
`th` is captured independently; its observed value is not explained by adding
`T00` to raw input `T` or `THM`.

The input and public-call rows are coordinate-matched observations, not a
continuous pointer trace. The driver entry itself was not captured, and the
historical ELF has no DWARF. Although the adjacent source candidate passes
`TH=th`, `Q=qv_curr`, and `QC=qc_curr`, exact historical aliasing and the
upstream transformation from `wrfinput_d01:T` to the KDM6 `th` argument remain
open. Similar numeric values do not close that lineage.

The KDM6 PRE/POST states are exact selected raw REAL*4 values from PR126's
`analysis/selected_profiles.csv` for the first call. At this key, OFF/HYDRO
return with QR zero and LIQUID retains nearly all entry QR. HYDRO/OFF also
return with higher QVAPOR, lower QCLOUD, and lower `th`. This is an observed
whole-call response, not proof of a specific evaporation, condensation, or
conversion process. Initial state differences between LIQUID and OFF/HYDRO are
already present at the input and KDM6 entry boundaries. The distinct arm
trajectories and setup therefore preclude interpreting their difference as a
single-process effect.

## Caller and internal call boundaries

The driver-to-KDM6 public call instruction is `0x20c371d`, with return PC
`0x20c3722`. The driver places six argument pointers in `rdi,rsi,rdx,rcx,r8,r9`
and 71 additional pointers on the stack. The prior PR125 evidence at
`../../cp02_wrf_first_call_20261029/abi/README.md` documents the full 77-position
candidate map and public call capture. PR126 captured the same public KDM6
entry/return boundary twice per rank at timesteps 1 and 2, with `dt=20 s`.

The executable's KDM6 body calls KDM62D at `0x25e0fe4`; its immediate return
PC is `0x25e0fe9`. At the call site, the first six KDM62D pointers are loaded
into `rdi,rsi,rdx,rcx,r8,r9`. Their candidate roles from the adjacent source
signature are `(t,q,qci,qrs,nci,nrs)`. Therefore, at callee entry, `rdx` is the
candidate local cloud/ice mass buffer `qci`, while `rcx` is the candidate local
rain/snow/graupel mass buffer `qrs`. The array buffers are passed by address.
This is the smallest actionable boundary for determining whether QR is first
changed inside KDM62D and which local field is written. The existing PR126
captures do not contain these inner pointers or inner states.

For a future authorized capture, retain the public entry at `0x25df680`, stop
at KDM62D entry `0x25e2490`, and stop at its call-site return PC `0x25e0fe9`.
At KDM62D entry, first save `rdi,rsi,rdx,rcx,r8,r9`, the raw 56 stack pointer
slots, pointed-to scalars/bounds, PC, and call frame. Verify memory/tile bounds
and identify the selected current column from its captured pointer/index
mapping before adding hardware write watchpoints to the computed species-1
`qrs` and `qci` words. Watch the direct `q` and local `t` addresses as paired
context. A write watchpoint should record old/new REAL*4 bytes and the write
PC, then continue to `0x25e0fe9` to capture all candidate buffers after the
internal routine returns. Do not call inferior functions to decode values.
The point selection condition may use the candidate `lat` pointer at stack
argument 32 only after the captured pointed-to integer and `q` slice are
cross-checked against live bounds; no source symbol or C-style name is assumed.

The candidate KDM62D signature has 62 arguments. Its positional map is recorded
in `kdm62d_candidate_abi.csv`. Before the call, stack argument 7 is at
`$rsp+0`; at callee entry, stack argument 7 is at `$rsp+8`. Thus candidate
tile bounds are positions 51–56: `(its,ite,jts,jte,kts,kte)`, and memory bounds
are positions 45–50: `(ims,ime,jms,jme,kms,kme)`. Domain bounds are positions
39–44: `(ids,ide,jds,jde,kds,kde)`. These names are source candidates, not DWARF
names embedded in the executable.

Candidate array indexing at KDM62D entry:

- `q` is passed as the current-column slice beginning at `q(ims,kms,j)`, so
  `q(i,k)` uses offset `(i-ims)+(k-kms)*(ime-ims+1)`.
- Local `t` uses `(i-its)+(k-kts)*(ite-its+1)`.
- Local `qci/qrs` species planes are Fortran ordered `(i,k,species)`. For
  species 1, offset is `(i-its)+(k-kts)*(ite-its+1)`; other species add one
  or two complete tile planes.

The candidate source loops over `j`, copies full vertical columns into local
arrays, calls KDM62D, then copies `qci/qrs/t` back into public KDM6 arrays.
The machine-code call site and register order support the internal boundary;
the exact source-level loop index, local array shapes, and named copyback remain
unverified against the linked build. Keep the raw PC, pointer values, bounds,
and call frames in any next capture and verify the point/column ownership from
runtime evidence. The public KDM6 return at `0x20c3722` is an established
post-call boundary; this inspection does not claim a distinct internal
post-copyback PC for the selected column.

## Process-path hypothesis to test, not a conclusion

The co-located KDM6 source candidate contains two relevant rain paths:

1. `prevp` at source lines 1718–1733 labels rain evaporation/condensation
   (`QV -> QR`).
2. `Prevp_s` at lines 2823–2835 transfers rain mass into cloud water and sets
   rain mass to zero when candidate mean-volume diameter `avedia <= di82`;
   later cloud condensation/evaporation at lines 2860–2890 changes `q`, `qc`,
   and `t`.

In the same candidate file, lines 315–334 copy `th*pii`, `qc`, and `qr` into
local column arrays and invoke `kdm62D`; lines 356–360 copy local thermodynamic
and hydrometeor arrays back. The co-located driver candidate around line 2535
calls `kdm6` with `TH=th`, `Q=qv_curr`, and `QC=qc_curr`. These exact source
locations help name a future capture but do not establish compiled-source
identity or the upstream initial `T` transformation.

The observed public entry/return deltas do not distinguish either path from
other KDM62D processes or thresholds. In particular, the binary/source identity
gap means neither source block can be claimed as the historical executable's
cause. The capture agent's proposed inner KDM62D bracket plus writes to local
`qrs/qci/q/t` at P01/P05 k8 is appropriate evidence to resolve the first-write
location. No process rate or closure follows from the current endpoint records.

## Commands, versions, and limitations

`commands.txt` lists the exact read-only binary and source commands. Disassembly
snippets and symbol rows are preserved alongside this README. Versions and
source/binary hashes are in `tool_versions.txt` and `source_binary_sha256.txt`.
The extraction scripts are hash-recorded in their JSON receipts; generated CSV
hashes are recorded there as well. `p05_k8_public_kdm6.csv` contains the exact
twelve PR126 first/second-call entry/return samples supporting the P05 table.

Graphify was queried read-only from the branch's 1,499-node `graphify-out/graph.json`.
The broad query returned 59 nodes, mostly generic Cloud-BAL topics, and did not
surface CP02 capture relationships. This snapshot was not updated; the direct
PR125/PR126 source, receipts, selected-value CSVs, and exact executable were
checked instead. This graph result is an extraction limitation, not a runtime
or scientific validation.
