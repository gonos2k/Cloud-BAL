# PR89 C5 ICE bounded-absence review — 2026-10-19

Read-only review of the C5 shared-core change and source-bound fixtures. No tests or builds were run in this review, and no files were edited.

## Reviewed file identities

- `src/common/cloud_bal_joint_transport.f90`: `aef7f536f85983f4fcb9dd266fafc6c5e900dbf0e1c485b1afd55a8dee56bd51`
- `tests/test_joint_qnb_transport.f90`: `1a1368f6af6e287ad571f7b8c9f482653bcf4789adb04371345a861c189aead8`
- `tools/pr89_ice_consumer_contract.py`: `ad99abedd9fa2580c4533043145414a79e1d3313a13d12e72cb25380b8ea245f`
- `tests/test_pr89_ice_consumer_contract.py`: `ebedd24a25a0c823ca0c3d0fa38ba965c68afdd1e4407717942f757e6b571dcc`

## Review result

No source-level blocker found in the C5 delta. The added fallback remains behind a positive finite inactive-mass cutoff and explicit joint-absence permission; it requires finite positive Q/N, positive finite density and ratio bounds, Q at or below the native cutoff, and a candidate which fails the ordinary canonical validator. It derives the number cap from `REAL64(minimum positive REAL32 subnormal)/minimum_ratio`, then moves that cap one REAL64 ULP downward. It only maps the state to exact `(0,0)` when Q itself casts to zero. The default, cutoff-only, and legacy-canonical-valid paths continue through the original validator/storage path. Positive inactive limits remain incompatible with strict-mass and volume contracts and are restricted to the ICE/QI pair in `joint_qnb_update`.

The new Fortran fixtures cover the exact cap and its next REAL64 value above, exact C5 Q/N payload bits (`0x3383F446E813526C`, `0x36D101F352E66E25`) and their REAL32 endpoints (Q zero, N subnormal value 9), rejection without the explicit permission, C4 T5 both-zero storage, and all 11 printed pair-2 FULL Q/N rows. The FULL-row values were independently matched against the OFF C4 `pr85_joint_source_failure.raw.gz` record (SHA-256 `3e7241c0508676e88cfe3e31a6807b08b608fed50991f762ab92aa6a94b006ef`); the fixture correctly treats the printed values as rounded diagnostics and the fatal candidate's exact payload bits separately. All 11 printed ICE numbers are below the derived cap; the largest printed N is `1.479016056948707e-30`, versus a cap near `5.37805e-30` for the pinned minimum ratio.

The companion `review/c5_full_fixture_check.json` (SHA-256 `b2cdeaa85a00c09fa781597ab7276e187289dd6d1b7abdafaf9b74694e1a93ba`) now verifies the compressed and decompressed OFF C4 ledger hashes, matches all 11 literal Q/N rows to the decoded source rows, and records the exact-rational one-quantum cap and next-above result. The file retains the distinction between rounded list-directed values and exact fatal payload bits. The Fortran test also now sends the exact C5 Q/N payload through `joint_qnb_update`: with manufactured `dt=1` and unit carriers (explicitly a candidate-level transaction fixture, not a native RHS reconstruction), it checks opt-in-off rollback, opt-in commit to `(0,0)`, adjustment count, both signed storage losses, and validation of the absent endpoint. The exact C5 one-zero endpoint is still exercised directly at `joint_moment_store`; the transformed-host integration fixture remains the prior positive T5 ICE endpoint, while the connector pins the new shared-core hash and embeds that exact core before transforming host call sites.

Root's final focused receipt `review/focused_validation.json` (SHA-256 `db85ec83caef05ba2a8415f39c82b1987a08f957f95028c42332512a1bc9e62c`) records 43 focused tests passing with the current ten source/test hashes; the standalone joint test passes pinned Intel O0/O2. Its checked-in log SHA-256 is `ffd23ebdf1efde6a3a8dd25491c57237d22d253e4afe072e2319e6a8b9729955`; focused test log/JUnit hashes are `01068b117c7ca974120ad89d07ffc29e329c912a413aa2d7064e7953f6ebd58d` and `36b21895089ba1000cb2c468aff5de8eb47d90aec5817c7c3e5f681a455a929f`. This reviewer did not rerun those tests. The validation is focused source-form/unit coverage, not a whole canonical or clean WRF build, nor native completion or physical approval.

This review found no basis to relax the graupel QG/QIB upper bound. The separate G diagnosis is in `/var/tmp/pr89_graupel_t5_contract_20261019.md`: C4 already has a strict source-witness fallback, while the captured decimal FULL rows do not contain exact runtime candidate bits or fallback outcome.
