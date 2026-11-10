# Validation and precision boundaries

The broad unit entry was run from a frozen source export. Its receipt explicitly
lists the new boundary/test-tier paths tested separately on their final bytes.
The focused receipt covers the final eleven boundary cases, the six composed
physical cases at O0 and O2, the extracted rain sign proof and exact figure data.

Water and mixture-enthalpy checks in the composed cases apply to the REAL64 local
phase/saturation solution. The solution is then converted to the canonical
REAL32 fields, and moment completion is required to preserve those stored fields
exactly. This does not close a separate water/enthalpy ledger across the REAL64
to REAL32 conversion, regridding, or the subsequent WRF initialization/dynamics.

The KDM6 policy guard is an analytical source-derived envelope, not a bitwise
replay of REAL32 coefficient construction or PSD branches. A file-state density
proxy is not a measured first-advection or first-microphysics density.

The real-producer replay produced the same historical B1 file. Its fixed prior
was rejected, no initialized candidate was published, and no WRF forecast or
first-use run followed. Producer/source/build identities include caller
attestations; they do not establish an independent build closure.

Earlier mutable-source compilation and incomplete-export dependency attempts
are retained under attempts/ and were not counted as passing validation.
