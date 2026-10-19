# PR89 packet contract independent review — 2026-10-19

## Result

No blocker found in the frozen `connect_freezing_consumer` transform. It factors the existing NG rain-pair predicate into a shared helper and calls it from both `kdm6_rain_process_state_valid` and the rain-freezing admission path. The freeze path also reuses `kdm6_progb_density_pair_valid` with the existing 100–900 kg/m³ bounds and checks finite, positive stored temperature. It validates only the affected rain pair, graupel pair, and temperature; the full NG validator retains the cloud and ice PSD checks after their later PSD reconstruction.

The shared helper returns its own validity result, so it cannot set the enclosing full-state validator's `valid` output true before later checks. Failed rain, graupel, or temperature checks leave the packet uncommitted. The invalid graupel path reports reason 9.

## Source and artifact hashes

- Pinned ActualV50KDM6 source: `769cf33f7e6d59d46e2b31ec973a7d44cecce0b505fc18b0890b5b2a4ef2464f`
- Rain-freezing packet helper: `04f6d2859702521ee33ea679dd7a6f92ad14e341ba87307bd10387f26456b186`
- Transform and regression generator, `tools/pr89_process_consumer_contract.py`: `be2c82f0d1cffd6966d1ac8f1d6cedde7f0873898643dee403df7b5ff8d986f7`
- Regression test, `tests/test_pr89_process_consumer_contract.py`: `c3018d6c89ded65e14e912353a2885dcdf7cd7c62332ae6abbfb733f8b395e83`
- Generated transformed Fortran test source: `8b06aef50abc5e0ed943ea31fbe18c21512e803643eecfe935e32cee5eff8b93` (30,245 bytes)

## Validation

Ran `python3 tests/test_pr89_process_consumer_contract.py`. It compiled and ran in fresh `/var/tmp` scratch directories using the pinned Intel `ifx` 2026.0.0 profile from `tests/intel_toolchain.sh`, at both audit O0 (`CLOUD_BAL_FREE_FLAGS`, including `-check all -fpe0`) and reproduction O2 (`CLOUD_BAL_REPRO_FLAGS`). Both passed.

Covered cases: the actual T4 integrated rain-freezing request is deferred with strict NG rain reason 6 and all packet endpoints rolled back; zero and valid nonzero packets; invalid cloud state remains rejected by the full NG predicate (reason 5); valid rain plus invalid graupel density is rejected with reason 9; invalid and nonfinite temperature bases are rejected with reason 8. Compiler output contained only unused test ledger-unit warnings.

## Evidence scope

The T4 inputs are the stored integrated, donor-capped `pfrzdtr` and `nfrzdtr` proposals. The ledger does not retain uncapped source rates before multiplication by `dtcld` and the donor `MIN`; those primitive rates remain unavailable from this record. The test supports the transformed source-block contract against the pinned helper and predicate. It does not establish full-model runtime or scientific closure.
