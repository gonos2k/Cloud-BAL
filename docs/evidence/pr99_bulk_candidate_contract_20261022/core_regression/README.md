# Shared-core regression

`validation.json` binds the frozen v2 core, the existing
`tests/test_joint_qnb_transport.f90` source hash, pinned Intel profile, and
FREE/O0 and REPRO/O2 runs. Per-profile `commands.txt` and `stdout.log` preserve
the exact commands and outputs. Both runs returned 0. Executables and module
files are excluded; their hashes remain in the validation record.

This is a local shared-core regression, not a full host build or native
three-arm validation.
