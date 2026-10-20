# D1 Graupel source and store replay

## Scope and inputs

The replay uses the hash-pinned D1 `module_em.F`, the archived pre-policy common core, and the reviewed bulk-volume policy core. The source module SHA-256 is `1d6538e3e1aeb59a2f0f38b2ec8de8aef11c4991e2d6ae0c8d4641b065c821ef`; the archived baseline core is `cf1384a06a82e2f3d03b4ca61db8fbfb8ad2e61d889e4290d790d7aa4d3be466`; the reviewed policy core is `8ce23e675a23283fb047a88f6ca0d26444ed2f56a9e7dfdc872a1602a6f1d6bf`.

Replay input gzip captures and native run receipts are preserved under [input](input/). The two receipts are **INCOMPLETE** (`returncode=1`, 14 completed timesteps, no processing errors). The fixture replays only the captured T15/RK1 records; these results do not establish a complete model run.

The fixture extracts the original D1 `graupel_diffusion_point` and `strict_graupel_pair` helpers, then compiles the baseline and reviewed policy modules with pinned Intel O0 and O2 profiles. Every replay record matched between O0 and O2. The generated sources, raw compiler output, runtime rows, and hashes are in [replay_off](replay_off/) and [replay_cpl](replay_cpl/).

## Scoped result

The combined report is [combined.json](combined.json). Both arms close the captured source chain and the stage 6 bulk-absence path. Overall status remains `LEGACY_REPLAY_PENDING`; all store cases are not closed.

- The 19 FULL T15/RK1 records comprise 7 OFF and 12 CPL cases. The other 13 selected records are CERTIFIER retries and are retained separately.
- All 17 FULL stage 2 source pairs match the corresponding producer D64 bits exactly: 6/6 OFF and 11/11 CPL for both QG channel 7 and QIB channel 8. The reviewed policy leaves these at stage 2 with no acceptance. Each is classified as an unresolved legacy policy preview.
- Four stage 6 records (one FULL and one CERTIFIER per arm) replay to policy adjustment 5, with strict-valid stored Q/B equal to zero.
- Earlier CERTIFIER failures are summarized by step, RK, and context in each arm report. They were not sent through the reviewed policy store.

For the first T15/RK1 consumer identity in each arm, both Q and B source expressions using the original grouping `FINAL + ((BEFORE_D + D64) - AFTER_D)` match the captured source values. The source cache delta also matches. Producer and consumer metrics, scales, and diffusion operator stencils match bit-for-bit. Their Q1/N1 state stencils differ, and the producer D64 values do not equal the fallback diffusion computed from Q1/N1. The fallback helper itself exactly reproduces the captured D64 values and REAL128 face coefficients. This records the state difference without treating producer and fallback diffusion as interchangeable.

## Reproduction

From the Cloud-BAL root:

```sh
python3 tools/pr92_source_store_fixture.py \
  --producer docs/evidence/pr92_source_store_20261020/graupel_store/input/off_producer.raw.gz \
  --consumer docs/evidence/pr92_source_store_20261020/graupel_store/input/off_consumer.raw.gz \
  --receipt docs/evidence/pr92_source_store_20261020/graupel_store/input/off_receipt.json \
  --output /var/tmp/pr92_store_replay_OFF --arm OFF

python3 tools/pr92_source_store_fixture.py \
  --producer docs/evidence/pr92_source_store_20261020/graupel_store/input/cpl_producer.raw.gz \
  --consumer docs/evidence/pr92_source_store_20261020/graupel_store/input/cpl_consumer.raw.gz \
  --receipt docs/evidence/pr92_source_store_20261020/graupel_store/input/cpl_receipt.json \
  --output /var/tmp/pr92_store_replay_CPL --arm CPL
```

`tests.test_pr92_source_store_fixture` passes all 5 tests, including pinned Intel O0 compilation of the generated replay harness.
