# CP02 two-call KDM6 capture design

`capture_kdm6.gdb` is a read-only GDB helper for the OFF, HYDRO, and LIQUID
control arms. Each arm must pass the same 624-point selection used by the
first-call evidence (`16` horizontal corner points across `39` levels) and use
a fresh `CP02_CAPTURE_DIR`. The parent controller supplies the executable,
selection path, MPI setup, and arm-specific directory.

For each MPI rank, the helper captures two consecutive entries at `0x25df680`
and their returns at `0x20c3722`. Each JSON envelope keeps the raw ABI register,
stack, pointer, scalar, bounds, and selected-array evidence under its own
`calls[]` entry. It records the observed `itimestep` and `delt` bytes/value on
each entry; it does not predict the second call's timestep or require a fixed
`dt`. Entry and return samples are distinct. The selected arrays are read only
when coordinates fall inside validated memory and tile bounds; halo and
out-of-bounds coordinates are recorded without dereferencing their values.

The capture filename is atomically replaced after every entry and return. Once
its second return is saved, each rank waits for all expected ranks' two-call
envelopes in that arm's fresh directory, then exits GDB. It inspects peer
failure markers and records a local failure marker if a peer fails or the wait
times out. GDB exits zero only after all expected ranks complete both calls;
capture failures exit nonzero. A successful controlled debugger stop is
intended to end the MPI launch with its expected nonzero status; it is not a
completed forecast.

The helper uses the binary-backed 77-argument call layout from the prior ABI
inspection, with source-derived names retained only as candidate labels. It
does not decode buffers at the driver entry (`0x20c02a0`), assert a compiled
source identity, or write model state. GDB software breakpoints may patch
instructions as part of normal debugger operation. The pinned historical
executable identity to verify before launch is SHA-256
`de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168`.

Every sampled float keeps its raw four bytes. Finite floats also get a decoded
value; NaN and infinity get `value_f32: null` and `finite: false`, so the JSON
remains strict. Nonfinite samples in core species arrays are validation
failures, while diagnostic buffers must be interpreted with the captured
`diagflag` and `do_radar_ref` values. Raw diagnostic bytes, including inactive
output buffers, are not scientific measurements.
