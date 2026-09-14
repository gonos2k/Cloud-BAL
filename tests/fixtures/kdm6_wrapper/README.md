# Isolated KDM6 wrapper fixture

The five `.F` files are unchanged copies from the named research host;
`origin.json` records their original paths, byte counts and SHA-256 hashes.
They are a test snapshot, not a new authoritative host implementation.

The runner copies this fixture into fresh scratch build directories and
applies the candidate patches there. Compile `module_wrf_error.F` to provide
its module interface, but do not link its object: that object would introduce
the full WRF runtime. The serial wrapper needs only the external `wrf_debug`
symbol from that runtime. `wrf_debug_stub.f90` fails immediately if called;
radar is disabled in this test, so no diagnostic call is expected.

The original `libmassv.F` supplies the reciprocal and square-root routines
called by KDM6; it is compiled and linked without substituting a math implementation.
The actual radar and model-constants sources are retained and compiled with
the KDM6 source. No host `.mod`, object, archive, NetCDF or MPI library is
required. `tests/intel_toolchain.sh` remains the required pinned compiler and
runtime profile. This is host-directory independence, not a portable compiler
distribution or native forecast validation.

Run from any working directory using the absolute path to
`Cloud-BAL/tests/run_kdm6_number_wrapper.sh`. Build artifacts are retained in
`Cloud-BAL/scratch/`; the fixture itself is never patched or compiled in place.
