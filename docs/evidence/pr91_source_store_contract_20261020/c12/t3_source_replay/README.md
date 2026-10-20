# C12 T3 source-stage store replay

This source-form replay uses the exact C12 `SOURCE_STAGE` record for OFF T3/RK3, cloud pair 1, `(i,j,k)=(162,132,3)`. The record is 593 bytes and is bound to the C12 OFF runtime receipt in `/var/tmp/pr91_OFF_240s_c12_20261020/`. The replay compiles the pinned `cloud_bal_joint_transport` module with `tests/intel_toolchain.sh` at O0 and O2.

The actual temporary source-stage call uses `strict_mass_ratio=.TRUE.`, normal-Q adjustment and joint-quantum absence enabled, and no volume bounds. Replaying the captured R64 Q/N with those options returns `valid=F`, stage 2. The raw physical source rates without the source-correction sidecar (PBL-origin, updated by FogDES during the callback) pass the same store. The producer's integrated REAL32 endpoint is Q=`320245B8`, N=`49DCFAFB`; casting those words back to R64 also passes at stage 0.

The captured corrected R64 candidate is exactly at the cross-product boundary after multiplication rounding (`Q - R64(minimum_ratio*N) = 0`), but `Q/N` rounds one REAL64 step below the strict minimum. FogDES used the cross-product predicate for this source-present trial, so it accepted a candidate that the host's division-based strict store rejects. This is a predicate mismatch at the representation boundary; the evidence does not show a materially invalid raw physical packet. The C13 correction makes the FogDES trial call the existing host store with the same strict options. No tolerance or clipping is introduced.

Run from the repository root with `bash docs/evidence/pr91_source_store_contract_20261020/c12/t3_source_replay/run.sh`. The script builds only in `/var/tmp/pr91_c12_t3_source_replay_20261020` and emits O0/O2 outputs.
