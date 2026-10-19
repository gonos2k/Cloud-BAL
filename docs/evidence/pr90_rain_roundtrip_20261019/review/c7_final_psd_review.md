# PR90 C7 final PSD source review

Read-only review of the C7 transform, its regression and the preparation CLI. No maintained code was edited and no duplicate tests or model runs were launched.

## Findings

No remaining blocker found. The direct exact-bound correction is placed after the existing final `NR > nrmax` cap, under the original active-rain `QR >= qcrmin` and `NR >= nrmin` cutoffs. It calls the existing `pr85_kdm6_psd_bound_number` helper, sets `lamdr_tmp` to the matching endpoint, and adjusts only rain number/slope state. Both legacy lambda-slope triggers are retained. No arbitrary NR floor or mass/heat edit is introduced.

The PSD unit now opens/closes for every KDM6 call. Direct-bound helper invocations trace to this valid unit; rows contain the source timestep and lat context plus stage, i, lat, k, side, inputs, and exact bound fields. The preparation API/CLI exposes final bounds, forces the warm output overlay, labels the result C7, and marks `physics_changed`. Its `scope` now expressly names exact final rain PSD reconstruction after the final number cap.

The updated regression binds the seven T8 words to C6 `OFF_t8_failure_replay.json` by its pinned SHA-256 and checks replay event/capture provenance. It covers both the T8 lower-bound miss and a forced upper-bound miss through the final NR cap, including cache values and public store → restore → shared NG acceptance. The test's T8 R32 slope is `44704006`, interior to both lambda limits, so the old slope trigger misses. The rain agent reports Intel O0/O2 passes; I inspected the current source/test but did not rerun them.

C6's closed event was the paired-store internal-volume precheck, before public store/restore/NG. The regression proves the captured pair is repairable at the final source gate, but does not identify where the full model first produced it. The resulting NR delta is a PSD-bound reconstruction adjustment, not evidence of physical nucleation or a physical water budget. No C7 model outcome is available yet.

## Bindings at review

- `tools/pr90_rain_final_psd.py` SHA-256: `8365262081cf8f9f0ff777da247de0715f7858f8cc7a8233c8980496e7b3cdd0`
- `tests/test_pr90_rain_final_psd.py` SHA-256: `aee6b84e2b86067693bb6c419ebf2473201dbdce886d76558804bee85832374a`
- `tools/pr90_prepare_native_roundtrip.py` SHA-256: `dd587eaa2151fe93c8745abc03c615ebcdd62ff833731bfc4c25694947412c9f`
- C6 OFF replay SHA-256: `e084d1738cc14a5efe1c581975502f967ecb7464602fa011295e5626c61196b4`
- C7 build receipt SHA-256: `7a58ac2ae90eca9ffe0500515282b537e11db25ab9de8175856609bf812bba31`
- C7 executable SHA-256: `5f5599e38759a9e2be27a9e7e0977370592c92cab328062d07eb359bddd19572`
- C7 KDM source SHA-256: `983095a0aa0c76eab4efdda27f9435e61634e08e542ef9bd096aa4cf8004eca4`

At report time both 180-second arm runners were active; their preflights passed, and no closed C7 receipts were present. C7 remains an incomplete research experiment pending closed receipts and scientific review.
