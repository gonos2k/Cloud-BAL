# Independent typed-input Fraction oracle

`prepare_v2.py` creates the 40 typed IEEE input cases, derives the
operational REAL64 candidate reference, and computes an exact rational oracle
with Python `Fraction`. `bulk_absence_harness.f90` submits the same bit-encoded
cases to the public Fortran predicate. `check_results.py` rejects any helper
acceptance outside the exact oracle-valid set and requires acceptance of the
captured fatal input. `pinned_inputs.json` binds this work to the final v2 core,
host transform, source validation, Intel profile, and all oracle inputs.

FREE/O0 and REPRO/O2 each evaluated 40 cases: 17 accepted and 23 rejected,
with zero false accepts. Both accepted the actual captured fatal input and
rejected four exact-valid cases conservatively (`interior_ratio_100`,
`interior_ratio_900`, and the equal min/max boundary cases). Their 40 Boolean
outputs match exactly. These are manufactured typed-input cases plus the one
captured candidate; they do not validate upstream producer precision or a
full forecast.

The short build inputs, harness outputs, oracle-check JSON, and executable
hashes are preserved for each profile. Compiled executables, object/module
files, full model stdout, and native capture arrays are excluded. The source
manifest is included as `source_SHA256SUMS.txt`; the parent package
`SHA256SUMS` covers the copied subset.
