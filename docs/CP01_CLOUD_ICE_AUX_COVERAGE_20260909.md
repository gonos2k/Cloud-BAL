# CP01 cloud/ice auxiliary pair coverage — 2026-09-09

The diagnostic MP37 validator now requires QCLOUD and QICE arrays alongside
QRAIN and QGRAUP. It applies the same shape, real-type, finite, nonnegative
and mask checks to all four mass fields before examining declarations or
evidence. Callers must supply the two new keyword arguments; no missing mass
array is silently interpreted as clear air.

For each cell, positive QCLOUD with zero QNCLOUD returns NO_AUTHORITY with
`QNCLOUD_ZERO_WITH_NONZERO_QCLOUD`; QICE/QNICE has the analogous rule. Existing
rain and graupel rules retain their order and reason strings. A zero mass/zero
moment pair may be structurally valid with complete declarations, but it does
not authorize initialization or native handoff. No input is filled or mutated,
and `accepted` and `promotion_eligible` remain false.

## Actual-input inspection

The read-only probe uses the retained 13 UTC `wrfinput_d01`, SHA-256
`f0ccee31f6f7214c9d7b5ccf19e0ae55d9fe43751e0fcffbcaedfc6080a052e1`.
It finds these positive-mass/zero-moment cells:

| Mass/moment pair | Cells |
|---|---:|
| QCLOUD / QNCLOUD | 962388 |
| QICE / QNICE | 258832 |
| QRAIN / QNRAIN | 219996 |
| QGRAUP / QIB | 817 |

The unmodified input remains NO_AUTHORITY because the required denominator
mapping is absent. The counts are payload observations, not authenticated
denominator or startup-policy conclusions. Separate NaNs introduced only in
memory into QCLOUD and QICE reject before the missing declarations. The file
hash remains unchanged, and the validator receives read-only arrays.

Evidence is retained under
[`scratch/aux_cloud_ice_w6guiaaf`](../scratch/aux_cloud_ice_w6guiaaf/actual_input_probe.json).
This step closes the missing cloud/ice pair checks in the diagnostic API.
Native enforcement, source/binary denominator authority and physical startup
remain open; CP01 stays IN_PROGRESS / NOT_RUN.

## Validation

[The source-bound receipt](../scratch/aux_cloud_ice_w6guiaaf/receipt.json)
records 21 passing tests, including heterogeneous cloud/ice gaps, zero-state
non-mutation, malformed-array precedence and existing rain/graupel behavior.
The current non-scratch callers are tests and now supply both required mass
keywords. This API extension intentionally provides no implicit clear-air
default. No Fortran source was changed or rebuilt in this step.

[Independent review](../scratch/aux_cloud_ice_w6guiaaf/independent_review.md)
confirms the scoped contract and final callsites. The
[graph receipt](../scratch/aux_cloud_ice_w6guiaaf/kg_receipt.json) records
3686 nodes / 7846 edges / 240 communities for the Cloud-BAL AST snapshot.
