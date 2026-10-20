# C14 independent source review

**Reviewed inputs**

- Maintained core `src/common/cloud_bal_joint_transport.f90`: SHA-256 `cf1384a06a82e2f3d03b4ca61db8fbfb8ad2e61d889e4290d790d7aa4d3be466`.
- Frozen generated host `module_em.F`: SHA-256 `6a7a97c23c84f05837a3bb5e384ce944ecd2df220ea1889d990349cd509094b1`.
- Shared host trace instrumenter `tools/pr91_host_store_trace.py`: SHA-256 `d8ccd13acdf8d000570558646f947b23b1cd7e3bf6811b5e5f479cb32af2bafd`.
- C14 source transform `tools/pr91_inactive_ice_store_c14.py`: SHA-256 `3b990456d61b7e3b9a4c0ed75f03074d3eb1c979b6661bcd2bb9612ec873cda8` (also recorded in [the canonical source pins](../../../pr91_host_store_20261020/final_c14/source_pins.json)).
- Maintained grouped store test `tests/test_joint_qnb_transport.f90`: SHA-256 `cd77f51722a5e2612aad674056ad5cf3643339b9c3b3b3cf5b31c34ba33148bc`.
- C14 integration test `tests/test_pr91_inactive_ice_store_c14.py`: SHA-256 `1bed3043396637d0d10e5442df80543a0bd46603989efc6e158423206d8f22f2`.

**Review result**

No source-policy or transaction-rollback blocker was found. The new positive-Q-quantum representation is opt-in and defaults off. It requires subnormal storage, the existing joint-quantum option, and an explicit positive inactive cutoff; it rejects the active strict-mass and volume-contract combinations. It stores the exact binary32 minimum subnormal only for positive Q below that quantum and cutoff, retains rounded N, checks the stored pair against the inactive predicate, and checks that N times dry density remains a positive representable REAL32. It does not expand the paired-zero N cap. Adjustment code 4 has a distinct grouped count and signed Q/N storage residual.

The grouped candidate stores values and ledgers in local arrays and commits only after the full candidate succeeds. Each candidate evaluation resets local counters and deltas. The graupel fallback certifies private trial arrays and commits candidate state, signed deltas, adjustment counts, and inactive-Q counts together only on success; a rejected trial returns without modifying the model arrays or caller ledgers. The opt-in mask is pair 2 only. Cloud/rain volume-bounded storage and graupel strict bulk-density storage remain outside it.

Source-first producer endpoint representation changes are included in the existing `SOURCE_REPRESENTATION` signed pressure-coordinate aggregate with source-sidecar and operator changes. That aggregate does not isolate a source endpoint quantum count and is not a complete process or mass budget. The separate adjustment-4 count and signed Q/N deltas describe grouped storage only.

An earlier uncontrolled cast-to-zero observation was not reproduced under the pinned Intel O0/O2 profile. The REAL64 `2^-149` constant and REAL32 bit construction agree with the former `NEAREST(REAL32)->REAL64` quantum under that profile. This is an explicit representation construction; no compiler defect or numerical threshold change is claimed.

This source review and focused regression do not establish paired C14 model runtime success, conservation closure, or science approval.
