# CP02 first KDM6 ABI evidence

This directory records the static call-boundary inspection for the historical
CP02 WRF executable. It does not claim that the adjacent source files produced
this executable. Runtime facts must come from the per-rank capture files created
by `capture_first_call.gdb`.

## Executable and symbols

- Executable: `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_host_unit_contract_x3bcr8ui/host/main/wrf.exe`
- SHA-256: `de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168`
- ELF BuildID: `8baf18e56c6a582ccc7a27fb4d1653ad18fb8810`
- Driver symbol: `module_microphysics_driver_mp_microphysics_driver_` at `0x20c02a0`
- KDM6 symbol: `module_mp_kdm6_mp_kdm6_` at `0x25df680`
- First direct KDM6 call in the driver: `0x20c371d`
- `readelf -S` reports `.symtab` but no `.debug_*` section. The executable is not stripped, but it has no DWARF source/argument metadata.

## ABI map from the binary

The linked x86-64 executable follows the System V register/stack call convention
for this Fortran procedure. The driver loads arguments 1–6 into `rdi`, `rsi`,
`rdx`, `rcx`, `r8`, and `r9`, then pushes arguments 77 down through 7. Each
argument is passed by address. The 8-byte `sub rsp,8` is call alignment padding,
not an extra argument. At callee entry, the return address is at `rsp`, argument
7 is at `rsp+8`, and argument 77 is at `rsp+568`; alignment padding follows at
`rsp+576`.

| ABI position | Candidate name | Evidence basis |
| --- | --- | --- |
| 1–6 | `th, q, qc, qr, qi, qs` | Register loads plus the co-located procedure signature |
| 7–13 | `qg, nn, nc, ni, nr, bg, diag_rhog` | Stack setup plus the co-located procedure signature |
| 14–17 | `den, pii, p, delz` | Stack setup plus the co-located procedure signature |
| 18–41 | scalar thermodynamic/constants `delt` through `psat` | Stack setup plus the co-located procedure signature |
| 42–52 | `xland, rain, rainncv, snow, snowncv, sr, refl_10cm, diagflag, do_radar_ref, graupel, graupelncv` | Stack setup plus the co-located procedure signature |
| 53–59 | `itimestep, has_reqc, has_reqi, has_reqs, re_cloud, re_ice, re_snow` | Stack setup plus the co-located procedure signature |
| 60–77 | WRF domain/memory/tile bounds | Stack setup plus the co-located procedure signature |

Names are candidate labels only. The capture records the raw call-boundary
pointers and scalar bytes so they can be checked against runtime value ranges.
It intentionally keeps `diagflag` as its raw logical word and `do_radar_ref`
as an integer word.

The real arrays have 4-byte elements. For the candidate declared dimensions
`(ims:ime,kms:kme,jms:jme)`, element `(i,k,j)` has zero-based offset
`(i-ims) + (k-kms)*(ime-ims+1) + (j-jms)*(ime-ims+1)*(kme-kms+1)`.
The 2-D fields use `(i-ims) + (j-jms)*(ime-ims+1)`. The capture script checks
the requested global coordinates against each rank's live `ims:ime`, `jms:jme`,
and `kms:kme` before reading; out-of-rank points are recorded as bounds misses.
The helper also reads tile bounds `its:ite`, `jts:jte`, and `kts:kte`; a point
inside memory bounds but outside tile bounds is labeled `halo_or_not_owned` and
is not sampled. This keeps replicated halo values from being mistaken for the
owner rank's values.

## Running the capture

The parent run controller should set `CP02_CAPTURE_DIR` to a fresh per-run
directory and `CP02_SELECTION_JSON` to JSON like:

```json
{"points":[{"label":"P01","i":124,"j":457,"k":1}]}
```

Coordinates are WRF 1-based global `i,j,k`. Add one to any zero-based NetCDF
`x,y` coordinate; the helper records the supplied values without conversion.

It can then load this GDB command file for each rank's debugger. The script
breaks at the exact function address `0x25df680`, verifies the entry PC and
caller return address `0x20c3722`, and records per-rank argument/scalar/bounds/
maps data. It sets a one-shot breakpoint at the dereferenced return PC, preserves
entry and return samples separately in one JSON envelope, then exits GDB. It
does not call inferior functions or write scientific state. GDB software
breakpoints may patch executable instructions as part of ordinary debugger
operation. The default fail-stop gates require memory extents no larger than
1000 in each dimension, valid tile bounds, `itimestep=1`, and `delt=20`; set
`CP02_EXPECT_ITIMESTEP` or `CP02_EXPECT_DT` only when the run receipt documents
different expected values. The helper waits up to 60 seconds for all expected
rank captures (default 8) or explicit failure markers before exiting. Set
`CP02_EXPECT_RANKS` and `CP02_PEER_WAIT_SECONDS` to match the launch if needed.
The run receipt must confirm `num_tiles=1`, because the helper stops after each
rank's first KDM6 call and a selected point may be owned by a later tile
otherwise. The model must be launched by the parent controller with the
intended WRF command, namelist, MPI setup, and environment.

The script captures both PRE and POST values for arguments 1–17, 42–48, 51–52,
and 57–59 at every selected point. This includes potential input fields and
diagnostics; it does not assert that any entry value must exactly match a
particular initial file. In particular, equality with a WRF input file is not
expected automatically. Interpret values against the run receipt and the
confirmed call chronology.

## Source limits and chronology

The co-located `host/phys/module_microphysics_driver.F` and
`host/phys/module_mp_kdm6.F` were consulted only to label the positional ABI.
Their identity with the linked objects is unverified. The executable itself is
the authority for symbol addresses, call count, register/stack placement, and
the number of explicit arguments.

The co-located `solve_em.F` suggests that `itimestep` advances and the RK loop
precedes `microphysics_driver`; the source build identity is unverified, so this
does not establish the exact loop/stage chronology of the linked executable.
The binary has no line table. RK stage is not an explicit KDM6 argument. Treat
the call as step 1 and `dt=20` only if the runtime capture and run receipt confirm
those values; do not assign a valid timestamp without that receipt.

## Captured command outputs

- `binary_identity.txt`: executable type/hash/build ID and debug-section check.
- `symbols.txt`: linked driver and KDM6 symbol addresses.
- `call_setup.objdump.txt`: exact caller instruction range leading into KDM6.
- `tool_versions.txt`: tool versions used to create this static evidence.
- `commands.txt`: static inspection command lines.
- `source_candidates.txt`: hashes for co-located source files used only as ABI
  labeling leads, not as proof of the linked source revision.
- `readelf_sections.txt` and `readelf_program_headers.txt`: full ELF section
  and program header tables from the hash-pinned executable.
- `nm_relevant_symbols.txt`: driver, KDM6, and KDM62D symbol rows.
- `metadata_commands.json`: exact metadata commands, stdout file names, and
  return codes.
- `hash_manifest.json`: binary and runtime GDB helper hashes plus the archived
  ABI and plot evidence hashes.
- `capture_first_call.gdb`: runtime entry/return capture helper; no model was
  launched during this static investigation.

The captured plot is `../first_call_weighted_profiles.png`; its script,
four-corner weight source, capture receipt, and capture-file hashes are listed
in `../first_call_weighted_profiles.metadata.json`. It displays PRE/POST weighted
profiles for candidate `qr`, `qs`, `qc`, and `qi` arrays at P01/P05/P09/P13,
with WRF native `k=1..39`. It is a first-call state comparison, not an
integrated mass analysis or completed forecast.
