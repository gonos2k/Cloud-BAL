# PR102 frozen source and design review

Read-only review recorded 2026-10-25. The 640-second run remains open. No live
model fields were read, no tests were run, and no frozen source or preflight-
bound file was changed.

## Frozen source pins

| Artifact | SHA-256 |
|---|---|
| `tools/pr102_native_uv_smoother.py` | `0ad9b38485b5d25f6fd70b3150688449e994665ffc6e16c5feb371c4ff3a35f5` |
| `tools/pr102_native_wind_candidate.py` | `f044c57605942504a0c8ece22b915e8bd64bc2ddacb46a9cecd6920081f15b85` |
| `tools/pr102_native_ww_bound.py` | `97fc385f47ae8d6c02d1cc43e6d2a02c9974effcf2d26f78f759bfc111ac825c` |
| Frozen policy JSON | `9ab0d468b9d46cce00fb9cc66162fa995beeda714f93cedba8c65d6e1891200d` |
| Successful candidate proposal receipt | `451e4e9110d3b921507e311be56328ad05e13ee20e1fedd2d9c60ce8ef94eeb8` |

The current producer, core, and policy file hashes match the successful
proposal's recorded pins. Its status remains
`PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_SOURCE_CAPTURE`; physical approval is
`FAIL_OPEN` and observation skill is `NOT_EVALUATED`.

## Concrete documentation blockers

1. `docs/PR102_EXECUTION_20261025.md` still says “No N20 run has launched”
   and later says neither N20 run has started. This conflicts with
   `docs/PR102_WIND_STRUCTURE_20261025.md`, which records the closed candidate
   BASELINE20/STRUCTURED_CAPTURE comparison and pins its noninterference report
   and launch-identity evidence. Update the stale execution status before
   publication.
2. The design doc says the `sqrt(2)*Delta` projection-distance bound holds
   “after REAL32 storage.” Orthogonality proves that bound for the continuous
   exactly feasible increment. REAL32 readback has a separately bounded flux
   residual, so the same theorem does not follow for the stored increment.
   Qualify the statement as a continuous-solve bound, or report a direct
   stored-input source-distance check if that stored claim is intended.

## Math, policy, and scope consistency

The policy's single global equal-face L2 trust radius, nearest-projection
center, zero-exclusion condition, globally reserved REAL32 margin, fixed
homogeneous dry-flux equality, and geometric grid-component roughness are
consistent with the producer and solver. The solver uses the projected sparse
KKT system and a dual root for the stated radius; no forecast-selected weight
or second candidate appears in the frozen receipt. Geometry and roughness
claims are correctly labeled as grid-component proxies, not covariance,
kinetic energy, or a full physical momentum operator.

The stored-input readback values in the wind-structure and response docs agree
with the archived readback and proposal receipt. The first-native response doc
keeps raw RU/RV in native staggered source-coordinate units, reports the dry
column rates separately in kg/s per native support column, and states N is
6.69% above P and 8.94% below nonzero H without claiming benefit, closure, or
physical approval. Its scope is one completed 20-second step. No 640-second
result is assessed here.
