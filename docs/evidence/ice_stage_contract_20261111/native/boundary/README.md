# Manufactured ice boundary checks

`run.sh` verifies the pinned CONTROL source hash, extracts its first-slope ice branch, all three ice PSD blocks, the main ice lambda limiter and source coefficient initialization, and compiles the generated unit with the pinned Intel O0 and O2 profiles in a fresh scratch directory. Both runs pass all 33 checks with identical output. `receipt.json` binds the source, generator, generated Fortran, compiler profile and logs to their hashes. `boundary.f90` exposes all extracted statements and added test instrumentation for review.

The tests use REAL32 `nearest` values immediately below and above each REAL32 threshold, as well as equality. They check the first-slope QI <= QMIN default and zero-NI fallback just above QMIN; PSD1 and PSD2 activation at QI >= 1e-14 with zero NI and its resulting number reconstruction; and the independent QI >= QMIN and NI >= NCMIN gates of PSD3. Here QMIN=1e-15 and NCMIN=10 are supplied test parameters.

The lower and upper lambda limiter tests pass a lambda directly to the exact extracted conditional; they check branch selection and the resulting lambda at each bound and its adjacent representable values. They deliberately do not assume that the preceding exp(log()) calculation can produce a bound exactly. These are manufactured operator tests, not a full routine or forecast replay.
