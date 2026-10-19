# PR89-C1 T5 ice consumer-contract replay — 2026-10-19

## Finding

The paired 120-second C1 run failed in the T5 RK1 joint-moment candidate at `PR87_GRAUPEL_TRIAL_REJECT reason=1 pair=2 i=151 j=187 k=37`. The log label names the graupel mixture certifier, but `pair=2` maps through the bound caller's `qindex=(QC,QI,QR,QG)` and `nindex=(QNC,QNI,QNR,QIB)` to the ICE pair.

The six logged binary64 fields decode in order as `(value_q,value_n,source_q,source_n,transport_q,transport_n)`:

- `value_q = 4.246248455315979e-22`
- `value_n = 1.9903235415769328e-6`
- `source_q = 6.050904193090068e-18`
- `source_n = 2.836211114367672e-2`
- `transport_q = -0.0`
- `transport_n = -0.0`

The accompanying full-candidate diagnostic reports old/new carrier `95000`, dry density `0.1140736`, and `dt=6.666667`. With zero old pair and zero transport, `(old*base + dt*source)/new` reproduces the logged candidate. Its `Q/N` is `2.133446330013098e-16`; the ICE minimum particle-mass ratio from the bound source constants is `2.6055879053180625e-16`. This is about 18% below that strict PSD bound, not an 8-ULP boundary case.

The C1 KDM6 full NG state validator accepts the same positive stored ice Q/N because `Q=4.246e-22` is below its existing `PR85_ICE_NATIVE_INACTIVE_MAX` (`9.99999898e-15` in REAL32); the validator skips the ice ratio test in that transient-mass branch and requires positive number. The joint `joint_moment_store` call used by the certifier has no matching ice transient exception and returns invalid. This identifies a source-stage contract mismatch; it does not claim that all ice states below the transient limit are physically accurate.

## Exact-source replay

A small standalone driver was composed from the exact `cloud_bal_joint_transport` module in the V50 `module_em_pr85.F` and actual C1 NG consumer procedures extracted from the packaged C1 KDM6 source. Intel `ifx` compiled it in a fresh `/var/tmp` directory using `tests/intel_toolchain.sh` `CLOUD_BAL_FREE_FLAGS` (`-check all -fpe0`). The program passes only when the actual full NG validator accepts with reason 0 and the unchanged `joint_moment_store` rejects:

```text
T5_ICE_CANDIDATE_Q_N   4.2462486737519638E-22   1.9903236534446478E-06
T5_ICE_Q_OVER_N   2.1334463300130980E-16
T5_ICE_MINMAX_MASS_RATIO   2.6055879053180625E-16   2.0982747187893314E-09
T5_ICE_TRANSIENT_LIMIT   9.9999989774837532E-15
ACTUAL_KDM6_FULL_NG_VALIDT 0
JOINT_STORE_VALIDF 0 BF800000 BF800000
```

Replay source: `/var/tmp/pr89_t5_ice_contract_HvjX3Y/t5_ice_contract.F90`, SHA-256 `fd7fef41879fab1ffd1677ae20c3f8ea89086b3ca0b9cf26837950e047d69379`.
Replay output: `/var/tmp/pr89_t5_ice_contract_HvjX3Y/replay.log`, SHA-256 `743af75e2e738d992c1f122f9a092598f8e4d3c4096712589a7a044af6b37f7`.

## Source and runtime provenance

- C1 KDM6 source `/var/tmp/pr89_sources_20261019_c1/module_mp_kdm6.F`: SHA-256 `14c6145df549541fae2aab84e98ee480ba6ac8a7c769dd926a6d44f22451c35d`.
- V50 source with joint pair certifier `/var/tmp/pr87_followup_sources_20261019_v50/module_em_pr85.F`: SHA-256 `4d07170e68699e62276eb3ec800c123b6993e91cdaa9aae2411b4909c34a14c0`.
- C1 source-failure ledger gzip: SHA-256 `cb7fe3614ca3e8fe5c1a6c27a9ca3d14ca2e43a98cb21d43b85ff8629b1dbc7f`.
- C1 joint-transport ledger gzip: SHA-256 `f2a35e60c46ad1e5855b852d400e547826f858af1d2d0a3327826c4107930b81`.
- C1 paired runner receipt: SHA-256 `25ce190e04cc5011485bf1c63bb33f5a5515e6f7a8fe727f6345be4526881139`.

## Scope

This is a source-derived local predicate replay plus read-only diagnosis of the captured C1 failure. It is not a full native reproduction, a test of a proposed fix, or scientific validation. No source, tolerance, precision, or prior was changed. No WRF model was launched.

A possible narrowly scoped correction is to thread the already-existing ICE transient-mass semantics into both shared joint candidate storage and the subsequent all-pair certifier, preserving finite/nonnegative and the actual consumer's zero-number/pending rules while storing representable positive transient Q/N unchanged. This is a proposal for review, not implemented or validated here.
