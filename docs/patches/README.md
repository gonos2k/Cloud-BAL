# Research host patches

## KDM6 zero-volume quotient

`kdm6-zero-volume.patch` is a reviewable numerical repair for the accessible
KIM host `phys/module_mp_kdm6.F`. It has not been applied to the shared host or
an operational executable. The base source SHA256 is
`02c9dc1f6711c9785d3c5841cbf2c14ebc454fa4628466407ae7f8879e965c5a`.
A read-only `git apply --check` against that source succeeds.

When graupel mass exceeds the source threshold and its volume is exactly zero,
`ProgB_param` divides before bounding density. The patch directly selects the
existing masked-exception bounded result for positive and negative zero, then
retains the original clamp and volume reconstruction. Explicit IEEE sign
inspection is required: the pinned compiler's `SIGN` expression did not
preserve the negative-zero case under the tested flags.

Pinned Intel O0/O2 tests compare the original with `-fpe3` to the repair with
`-fpe0`: 817 actual candidate inputs and 10 boundary cases produce byte-identical
values for all 19 output arrays. Original division-by-zero flags are set;
repaired flags are clear, and all outputs are finite. Test coefficients are
fixed common helper inputs; this is not a full `kdm6init` or first-call driver.
Evidence: `scratch/kdm6_zero_guard.hu0w47hl/receipt.json`. The reproduction recipe
there (`reproduce.sh`) writes only a new scratch directory; it was added after
the recorded equivalent compiler commands and syntax-checked separately.

This patch does not establish a scientific volume/number initialization policy,
repair nonzero subnormal-denominator overflow, validate the entire KDM6 call,
or authenticate an operational build. Full source-bound host integration and
those contracts remain necessary before CP01 or native acceptance can close.

A concurrent `tests/test_kdm6_graupel_startup.f90` experiment expects the source's
named default density of 400 kg/m3 for missing QIB. That is a different startup
policy from preserving the old masked positive-zero limit of 900 kg/m3. The
same graupel mass gives 2.25 times as much QIB at 400; density-dependent fall
parameters also change. Do not combine the patches or treat the two probe
results as interchangeable. This directory's patch demonstrates numerical
legacy equivalence only; choosing the physical startup policy requires the
complete initialization and downstream validation evidence.

## KDM6 number-domain and unit contract — 2026-09-14

`kdm6_number_mass_domains.patch` adds seven existing-mass activation
predicates to the cold conversion, cloud-water accretion, and rain accretion
branches. Each guarded process now requires its participating mixing-ratio
mass and number operands to be above the existing thresholds before the
number-rate expression is evaluated. The patch does not initialize missing
number moments or add a microphysical prior. Its SHA256 is
`bee1e1a126123437706356f44eda79a89fdf322dab4f04cf5b96820b9c01d574`.

The paired unit patches are required together. `kdm6_number_basis.patch`
converts public number fields on the `#/kg dry air` basis to the KDM6
internal `#/m3` basis with the cell dry-air density, converts them back on
return, and uses the internal density-scaled numbers in the radius
diagnostics. `kdm6_ccn_initialization.patch` keeps KDM6 CCN initialization in
the `start_em` path on its declared density basis instead of reinitializing it
inside the microphysics call. Their SHA256 values are respectively
`f0f449648049f936a0724f36935a5c31120cfa5f360a4e856aa15769cb9ee37d` and
`0a3b5c36d9e8b51cdac566bbdf57af230904fff748f24e59aaf57d0ab6b9d2ae`.

The bounded paired-host checks in
[`scratch/cp02_host_unit_contract_x3bcr8ui/RESULT_UNIT.json`](../scratch/cp02_host_unit_contract_x3bcr8ui/RESULT_UNIT.json)
pass with pinned Intel O0/O2 builds: 20 full-module domain cases at each
optimization level, CCN-entry density checks at 0.5/1.0/2.0, and
specific-number radius invariance. The existing 23-field scaled metamorphic
oracle also matches at those densities while its unscaled negative control
remains sensitive. The corresponding three-run native diagnostic is recorded
in [`scratch/cp02_unit12_runs/RESULT_RUNTIME.json`](../scratch/cp02_unit12_runs/RESULT_RUNTIME.json).
Those trajectories are unit-corrected runtime evidence only; finite output and
exit 0 do not establish a physical cloud-omega driver, full budget closure,
or CP02 acceptance.
