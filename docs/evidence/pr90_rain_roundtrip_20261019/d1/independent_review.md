# D1 independent read-only review

## Result

D1 OFF 140 s is bound to the recorded native candidate, profile, inputs, and source receipt. It is **INCOMPLETE**: steps 1–6 completed (120 s), timestep 7 failed with return code 128. The OFF 120 s C5 receipt is COMPLETE. Both runs show no changed staged/original inputs or processing errors.

## Trace prefix

I streamed both compressed `pr85_joint_moment_stages` traces, parsing record metadata and hashing payload chunks without loading the arrays. All 49 records through timestep 6 compare bitwise equal: timestep 1 has 9 records and each timestep 2–6 has 8. This covers the recorded physical-state and PBL tendency records through 120 s. The compressed-file hashes match their respective receipts.

## Binding

The source receipt SHA-256 matches in both preflight receipts and the file on disk: `65fe21132d20292d9a6e20209e42fa63d96e7680b9ed1e29d0b1b6ee1a187a3e`. Both runs bind `wrfinput_d01` `23a948df…39440200`, `wrfbdy_d01` `885591e6…706b25d7`, and 101 source inputs whose post-run hashes equal the preflight inventory. The D1 overlay build receipt hashes to `4e2715cc…d21475f2f4e`; its executable actual SHA matches both the build receipt and executed-executable receipt (`f74f4c5f…f5a77dca`). The compiler profile actual SHA matches its pinned SHA (`5439fa3a…817111b4`). All nine source override requested/staged hashes match.

C5 binds a different executable (`beb2da67…f5de5a2d6`) and module_em override, as expected for the preserved candidate. D1 and C5 candidate namelists differ because the requested run durations are 140 s and 120 s; both use the same WRF input and boundary files.

## T7 failure

The native RSL diagnostic records `helper_stage=4`, `core_stage=-1`, reason `internal_volume_precheck`. The replay record pins the T7 caller at j=222, i=193, k=4 and its input/derived hex. O0 and O2 replays both match the native failure. The KDM wrapper’s `volume_number_to_specific` scalar conversion had already completed successfully before it called the paired-store helper. The failed precheck is inside that helper and precedes its own Nspec64 division, `joint_moment_store`, restore, and consumer; it does not indicate that the wrapper’s earlier scalar conversion was skipped.

## Limits

The diagnostic candidate adds probes on accepted paths. Exact prefix equality is observed for the captured fields; it does not establish IEEE floating-point flag neutrality. This is a 120 s prefix comparison, not a completed 140 s run or a scientific acceptance result.

Full hashes and machine-readable evidence are in [`pr90_d1_independent_review_20261019.json`](/var/tmp/pr90_d1_independent_review_20261019.json).

## Reproduce the trace comparison

The archived streaming comparator is [`independent_review.py`](independent_review.py) (SHA-256 `263ad1c6aa2d4e63a5d1f8f24f30fa445ea4228b60623e42e34ba4e8a24c8579`). Run:

```sh
python3 docs/evidence/pr90_rain_roundtrip_20261019/d1/independent_review.py /var/tmp/pr90_OFF_140s_diag_20261019/run/pr85_joint_moment_stages.raw.gz /var/tmp/pr89_OFF_120s_c5_20261019/run/pr85_joint_moment_stages.raw.gz
```
