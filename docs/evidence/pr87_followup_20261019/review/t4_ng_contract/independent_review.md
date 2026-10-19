# Independent PR88 T4 NG diagnosis review

## Result

The corrected diagnosis is supported by the pinned source, the T4 runtime state, and a fresh pinned-Intel replay. The earlier cloud-PSD interpretation is explicitly superseded in the README and is not supported by this replay. No physics or tolerance change is recommended by this review.

## Pins and reproduction

- Diagnosis README SHA-256: `85a3fc54fbe5ef933cf988f21e1ff0ccd0d5ca74e50b9d2938510eb02c2a3e38`
- Replay source SHA-256: `56659c0e58e351de339808e63a90320b9e501bddea43d2d12b9bb196086f7b30`
- Supplied replay log SHA-256: `9d2518f9c84664aff8fe06de945df0d1fa495355c8ea735b47bf702426d06d50`
- Actual KDM6 source SHA-256: `769cf33f7e6d59d46e2b31ec973a7d44cecce0b505fc18b0890b5b2a4ef2464f`
- OFF600 runtime log SHA-256: `3c53784ea0cd2071421f900f4594d82421f18d81d636cd41b09353e457b773b3`
- Rain-freezing ledger SHA-256: `b08e5104e51d0f5ecb21e94f39086093005b5f90f2266a5f2baea4ab8b935cb8`
- Pinned Intel profile SHA-256: `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`

The two replay procedures (`kdm6_progb_density_pair_valid` and `kdm6_rain_process_state_valid`) normalize identically to the corresponding actual-source procedures. I rebuilt `replay.F90` in fresh `/var/tmp` scratch with `tests/intel_toolchain.sh` and `CLOUD_BAL_FREE_FLAGS`; its output matches the retained log:

```
STATE_VALID_REASON F 6
RAIN_N_OVER_MAX 1.00000064509326
```

The replay call order puts the rain parameters (`pidnr`, q-minima, `dmr`, and rain lambda limits) before the cloud and ice coefficients, as in the source signature. The pinned KDM6 identity guard requires `pidnr=12566.37109375`, `dmr=3`, `lamdarmin=961`, and `lamdarmax=35000` (`module_mp_kdm6.F:1402–1404`). The replay supplies the corresponding REAL32 values. The source predicate raises reason 6 at `module_mp_kdm6.F:1192–1194` when `REAL(n(3),8) > rain_max*q(3)`.

The corrected diagnosis table labels `Nr` in m^-3. This is the internal KDM6 volume number concentration: source conversion multiplies public number-per-kg by dry density (`specific_number_to_volume`, lines 468–481), and output converts it back (lines 1568 ff). The earlier kg^-1 label was incorrect and is superseded.

## T4 transition evidence

The OFF600 receipt is `INCOMPLETE`, return code 128, with maximum seen timestep 4 and final completed step 3. The T1–T3 60-second rain-freezing ledger decompresses to an exact byte prefix of the 600-second ledger (55,549,849 bytes), and it does not contain the matching packet row. The 600-second ledger contains exactly one `PR85_RAIN_FREEZE` row for `(i,lat,k,loop)=(26,115,18,1)`, in the new suffix. The ledger does not itself carry a timestep column, so this suffix comparison is what binds the row to T4 rather than earlier completed timesteps.

That row has `accepted=T`, `base_valid=T`, and fraction `1.0`. Its post-packet Qr/Nr/Qg/BG/T values, converted back to REAL32, match the T4 NG failure hex fields exactly: `2EA445FC`, `3E2702A7`, `300669B5`, `2B19B507`, and `4384C1BD`. The runtime's failed state uses those same Qr/Nr values. The preceding packet state is just inside the strict rain-number maximum (`Nr/(rain_max*Qr) ≈ 0.999999993365`); the post-packet state is outside (`≈ 1.000000645093`, 6.45e-7 relative over).

At the freeze call, source lines 3739–3746 pass the rain bounds in the intended order: `pidnr/lambda_r_max**dmr` as the minimum mean mass and `pidnr/lambda_r_min**dmr` as the maximum. The packet's `rain_cone` applies eight REAL32 spacings at each mean-mass bound (`8730–8743`). Here the lower mean-mass bound is `2.9309320335276967e-10 kg`; the stored post-packet value is `2.93093014280442e-10`, below it by `1.8907232766387847e-16`, within the source allowance `2.2204460492503131e-16`. The next NG base check is strict and rejects the endpoint. This explains the actual reason-6 failure without attributing it to cloud PSD; it does not decide whether the packet tolerance is scientifically intended.

The packet ledger labels `lat=115` and the runtime base-failure record reports timestep 4, latitude index 115, i=26, k=18. The `NG_BASE_FAIL_META` line itself does not expose the loop field in this log; loop 1 is supplied by the unique matching packet row. Do not describe 115 as a geographic latitude.

## Scope and reporting note

The runtime receipt confirms only steps 1–3 completed (through the 60-second output); timestep 4 was seen but did not complete. There is no completed 80-second output. The README phrase “after 60 s” is potentially ambiguous beside the T4 diagnosis; a precise summary is “three steps completed through 60 seconds; T4 failed before its POST_KDM6 state.” Keep the 60-second PASS_SCOPED result and the later T4 failure as distinct scopes.

No separate replay recipe file is present in the diagnosis directory. This review records the independent compile profile and result above. No model execution, source edit, tolerance relaxation, or scientific-approval claim was made.
