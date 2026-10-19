# PR89 C3 ICE storage delta review — 2026-10-19

## Reviewed identities

- `src/common/cloud_bal_joint_transport.f90`: SHA-256 `e8cb1f233e158334e4c15c2deec2983e67bb3ff0ff6d33d31e19a1d5ee940e17`
- `tests/test_joint_qnb_transport.f90`: SHA-256 `4d346429e7a208a4219b6774a2d534f70d7c1bd76855af050c086857a75dfaab`
- `tools/pr89_ice_consumer_contract.py`: SHA-256 `899d6edc68fb4a37807d7201b9c9298aab6b3f37cc34c3fd82ccc5df3882795f`
- `tests/test_pr89_ice_consumer_contract.py`: SHA-256 `ebedd24a25a0c823ca0c3d0fa38ba965c68afdd1e4407717942f757e6b571dcc`

This is a targeted source/test review only; no compiler, native model, or test command was run.

## Findings

The C3 delta fixes the legacy regression by applying the original continuous PSD validator before considering the optional inactive-mass contract. `joint_moment_store` sets `use_inactive_exact_store` only after the default `joint_moment_is_valid64` rejects the pair and the positive, finite inactive limit accepts it. Thus the relaxed threshold admits PSD-invalid pairs only within the existing native inactive-mass contract: q must be at or below the limit, both stored moments must remain positive, and stored N times dry density must be representable by the native consumer. A pair already valid under the legacy predicate stays on the original R32 rounding/repair/quantum-absence path, even when the optional threshold is supplied.

The new inactive exact-storage path requires positive rounded Q and N, rechecks the rounded pair against the inactive limit and native product-mass PSD representability, then preserves both R32 values with adjustment count zero. It does not repair the endpoint or erase it to joint absence. The limit is inclusive at `q == limit`; a value at the next representable number above the limit is rejected. Zero limits retain strict/volume behavior, and non-finite or negative optional limits fail closed.

`joint_qnb_update` accepts positive inactive limits only for pair 2 (the documented QI/QNI pair), only with constrained joint storage, and not for pairs with strict-mass or volume-number bounds. The candidate feasibility check applies the same inactive limit to the rounded stored endpoint. Other pairs continue through their ordinary validators. This matches the intended pair-2-only scope.

The regression includes the exact T2 legacy-valid underflow fixture (Q bits `3650F39CB3992608`, N bits `384661B65DB0026E`): it confirms the base validator accepts it, the legacy store produces joint absence with adjustment 1, and adding the inactive limit leaves stored values and adjustment unchanged. A separate PSD-invalid subnormal is rejected despite quantum absence being enabled. Threshold/inclusive boundary, above-limit, orphan moment, unrepresentable `N*rho`, strict/volume zero-limit compatibility, and T5 positive exact-R32 storage cases are also covered. The updated T5 fixtures derive their REAL64 candidate from transferred source Q/N and rate bit patterns and `dt=40D55555`, then assert the calculated Q/N candidate bit patterns before R32 storage. The Q/N input bits are the actual T5 captured candidate; the source-rate bits are retained T5 source rates. The joint call uses `drydensity=0.1140736_real32`, explicitly documented as a positive adapter converted from the rounded full-state record, not the captured exact RK1 density bits. The T5 PRE_RK DEN value `0x3DE99F6C` is not used as an RK1 density. Thus candidate arithmetic is source-bound to the retained rates/time/carrier, while the test does not claim an exact captured RK1 density. The host output still has a full actual KDM6 consumer fixture; the tool pins the source/core hashes and verifies that the prepared native module embeds the exact reviewed core prefix.

## Review result

No source-level blocker found in the requested C3 delta. This review does not substitute for the root-owned pinned Intel O0/O2 runs or focused suite, which were not run here. The C3 core and consumer-tool hashes remain unchanged from the prior review; only the Fortran and Python test fixtures and the T5 fixture provenance annotation changed.
