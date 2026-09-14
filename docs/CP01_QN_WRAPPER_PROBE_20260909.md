# CP01 nonzero number wrapper probe — 2026-09-09

This bounded test exercises the nonzero cloud, ice and rain number paths that
the earlier CCN-only wrapper probe did not cover. The reference is a private
copy of the research KDM6 implementation, with diagnostic initialization
stabilized; the candidate additionally applies `kdm6_number_basis.patch`.
Neither copy changes the shared host.

## Comparison contract

At each density, the candidate receives public number mixing ratios `Nkg`.
The reference receives `Nkg*rho`, so both enter the microphysics kernel with
the same volume concentration. Reference number outputs are divided by rho
before comparison with candidate outputs. Hydrometeor masses and other
diagnostics are compared directly. This permits real microphysical tendencies;
it does not assume that numbers are conserved or that different densities
produce identical physical tendencies.

The reference cloud/ice effective-radius expression uses
`Nref_out/(qref*rho)`; the candidate uses
`(Ncand_out*rho)/(qcand*rho)`. The output comparison expects
`Nref_out = Ncand_out*rho`, so these expressions should agree for matched
internal states, including any microphysical tendencies. All three effective-radius flags must be enabled
to enter the actual wrapper's diagnostic branch. Radar remains disabled.

The test uses timestep 2 to exclude the separate CCN startup reset. The common
diagnostic initialization patch removes an undefined `rhox` read and is
explicitly part of the reference, rather than evidence of pristine-source
stability. Source hashes, compiler profiles and executable results belong to
the execution receipt.

## Scope

Successful agreement establishes conditional wrapper conversion consistency
for the tested states. It cannot select the authoritative active-host number
denominator, certify startup number/volume initialization, validate radar,
or promote the candidate into the host. The shared Registry-versus-source
contract conflict remains open. CP01 remains IN_PROGRESS / NOT_RUN.

## Execution result

[Receipt](../scratch/kdm6_number_wrapper_internal.E5am33/receipt.json):
PASS_SCOPED with pinned Intel O0/O2, six fresh build directories and three
density cases per executable. All 23 serialized outputs agree exactly between
the candidate and the scaled reference. Candidate O0/O2 outputs also agree
exactly. All cloud, ice and rain number outputs remain positive. The unscaled
negative control changes each of NC, NI and NR at rho 0.5 and 2, while rho 1
agrees. Both number-field halos remain unchanged; the identical interior
columns return identical NC/NI/NR values.

The final manufactured state uses T=250 K, QV=0.01, QC=0.0002, QI=0.00002,
QR=0.0001 kg/kg, NC=5e8, NI=4e3 and NR=1e7 on the candidate public basis,
with a one-second timestep. Positive BG=1e-12 avoids the separate zero-volume
path. These values are an algebraic wrapper fixture, not a balanced atmospheric
column or authorized startup initialization.

Cloud radius is away from its bounds. Ice radius reaches the 10.01 micrometre
floor at rho 0.5 and 1; equality there does not independently validate ice
radius scaling. The positive ice-number outputs and their sensitive negative
controls carry the ice conversion result. CCN also reaches its internal floor;
this is not new CCN validation. The earlier standalone radius oracle retains
its separate scope.

## Directory isolation

The user authorized bringing the required host material into the project.
The final test builds from the five-source internal dependency snapshot in
[`tests/fixtures/kdm6_wrapper`](../tests/fixtures/kdm6_wrapper/README.md), whose
`origin.json` records original paths and hashes. The original `libmassv.F`
supplies reciprocal/square-root operations. The fail-on-call `wrf_debug` stub
only replaces the unused diagnostic entry. No host archive, module file,
NetCDF, MPI or ESMF dependency is linked. The pinned Intel compiler/runtime remains an environment
dependency; independence from the host source directory is not a claim of a
portable compiler toolchain.

An initial development attempt compiled outside its scratch working directory.
That attempt is excluded from accepted runtime evidence; its generated module
is preserved under `scratch/kdm6_number_wrapper.IZ2drk/`. The first internal
link attempt exposed the missing `libmassv` dependency. Short-timestep fixture
attempts depleted the ice number and failed the positive-number assertion;
they are also excluded and listed in the receipt. The final corrected builds
record their actual fresh scratch working directories. Host source hashes
remained unchanged at final review.

[Independent review](../scratch/kdm6_number_wrapper_internal.E5am33/independent_review.md)
returns PASS_SCOPED. The paired
[graph receipt](../scratch/kdm6_number_wrapper_internal.E5am33/kg_receipt.json)
records the Cloud-BAL AST refresh (99 added nodes, no removed IDs); graph
structure is not runtime or native-host acceptance evidence.
