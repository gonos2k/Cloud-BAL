# V39 ice sublimation cap-order regression

This evidence covers only the cap-order correction in `tools/pr87_ice_sublimation.py`.
The source preimage is the archived V39 `module_mp_kdm6.F`; its SHA-256 is
`6a7f6e154390ad6d5da8ca18ea4115ad66effa5b1dbdbf73754edd357b6b4293`. The
transformed full source SHA-256 is
`faa81931252f6f28cc74ca3367a5c721668fe9ca0f01225641fb495a93ca6959`.

The transformed block saves the raw sublimation rate, executes both original
REAL32 caps unchanged, then records a pending full-sublimation event only when
the capped rate exactly equals `-qci/dtcld`. It preserves the pre-cap Q/N and
raw rate for the existing ledger. The existing endpoint commit clears number
only when the stored ice mass is zero.

`source_extracted_driver.F90` inserts the actual transformed cap and endpoint
commit blocks into a compact Fortran driver. The fixture uses the captured V41
pre-state values QI `4.2936549e-15` and NI `8.823875`, and checks overlarge raw
removal, exact full removal, a thermodynamic cap that reduces removal, and a
partial rate. It also checks that the cap rate matches the legacy cap
expression bitwise, positive-mass number is retained, and a zero-mass full
endpoint clears number. This is a source-fragment regression, not a full KDM6
runtime reproduction.

Intel O0 and O2 compiler/run outputs are in their respective subdirectories.
Both print `PR87 V39 capped sublimation cases PASS`. No binaries are archived.
The maintained pytest file reports four passing cases including these two
compiler profiles.
