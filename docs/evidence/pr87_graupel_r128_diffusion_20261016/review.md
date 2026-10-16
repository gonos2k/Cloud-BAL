# Graupel diffusion precision experiment

This record binds the V41 captured stencil replay to an isolated REAL128
intermediate experiment. It is a numerical diagnosis and a scoped stencil
cost measurement; it does not establish whole-run scientific validation.

## Captured V41 stencil

The source failure occurred at step 3, RK1, QG/BG, `(i,j,k)=(154,77,17)`.
The nonzero donor was the **i+** cell `(155,77,17)`; all other direct stencil
donors were zero. The donor was exactly on the upper density bound:

```text
QG = 2.274890675835195e-6
BG = 2.52765630648355e-9
QG/BG = 900
```

The pinned REAL64 helper returned `dQG=8.212150880350765e-6` and
`dBG=9.124612089278627e-9`, giving `dQG-900*dBG=1.6940658945086007e-21`.
The base and air rates were zero. Independent pinned Intel O0/O2 replay
reproduced the same increments and crossing. The full candidate using the
REAL64 increments failed the unchanged strict joint store. The same candidate
using REAL128-intermediate increments passed that store. In the full-candidate
replay, the REAL64 candidate had `QG-900*BG=+1.0339757656912846e-25`; the
REAL128 candidate had `QG-900*BG=-1.0339757656912846e-25`. This is one captured
case, not evidence of a universal cone guarantee.

The helper-only REAL128 outputs were `dQG=8.212150880350764e-6` and
`dBG=9.124612089278627e-9`; their REAL64 difference `dQG-900*dBG` was zero.

## REAL128 experiment

The experiment promotes only the stencil's local geometry, face weights,
differences, and accumulation to REAL128. Inputs remain REAL32, the helper
arguments and REAL64 output remain unchanged, and each completed cell result
is converted back to REAL64. A scalar REAL128 temporary holds one cell's
accumulation; it does not allocate a second three-dimensional REAL128 output
array. Thirteen manufactured exact-boundary single-face cases also stayed at
or below `QG=900*BG` after conversion.

On a closed-face variable-metric fixture, the weighted residuals were:

| Evaluation | Q residual | Q absolute weighted sum | BG residual | BG absolute weighted sum |
|---|---:|---:|---:|---:|
| REAL64 intermediates | `-5.9105928965990612e-22` | `2.21560524064468e-5` | `-1.1953840143433578e-24` | `2.46178319796127e-8` |
| REAL128 intermediates, REAL64 output | `+2.4752569925571560e-22` | `2.21560524064468e-5` | `-2.7623465272346624e-25` | `2.46178319796127e-8` |

Both residuals were within the fixture's roundoff envelope; the REAL128
residual magnitude was smaller for this fixture. Conversion to REAL64 means
conservation is not exact, and the measured improvement is not a general
bound.

## Scoped O2 timing

Pinned Intel ifx 2026.0.0, `CLOUD_BAL_REPRO_FLAGS`, 64x64x39 active cells,
12 calls per implementation, same REAL32 fixture inputs, helper only:

```text
REAL64:  0.01320 s
REAL128: 1.7916 s
ratio:   135.7x
```

This measures the isolated stencil routine only. It is not a full-model
runtime estimate. The cost is substantial for this path and should be weighed
before enabling the variant broadly.

## Bindings

| Artifact | SHA-256 |
|---|---|
| Captured V41 replay review JSON | `027df0edf37e3bd81a6f2af8f7018afe52306210712a20456d269463d9ab76ae` |
| V41 diagnostic source failure gzip | `c2289610a3a3fdb5ff273b83801c98ce71798213c06e2b8e2dd45d76c5876e34` |
| V39 `module_em_pr85.F` input | `e48607da8943caaf86f53c5fc04ff5ba2a2c75e32706142c97c3f9b8fdb70c70` |
| Embedded REAL64 helper | `0a8b2865fff3d7ad6592e0d1bc1d3f7b51970de13ac9ea128066b7cba655bfe3` |
| REAL128 transform | `90732185626f1ec04655924ef16872d5be12617ca2cc2a149447db83aaf960eb` |
| Intel regression wrapper | `b8edf146a580ca2005f11cde44e0be9c0d41d72fe2986eadf6355cd666e11af7` |
| Intel regression source | `46447737eee2f2601391a4152eca9a8702b7542d04db77e6692418d19e4aedf0` |
| V39 fixture gzip | `b297ca4f2ece7563acf289f6f6dbec44ad9ddbd563cb74dc6021dbdf4868e1c5` |
| O2 REAL64 benchmark helper | `da22fc9c0947aa37b2374297adb12597c6df1d7dc20d484dbbf6696805994345` |
| O2 REAL128 benchmark helper | `af9a54b9f3e51d085ef3a11b2dd52c6b5a9a6f755a8720866e34c740415f79de` |
| O2 benchmark source | `97652d45d121a4c642124a6ba9fe4cf18c9aeeb9b7ac8fa6698c86b937078880` |

The source fixture, tests, transform, and benchmark were compiled in fresh
scratch directories with the pinned Intel profile. The focused pytest wrapper
reported 2 passed, including O0/O2 compile and runtime checks. No full model
was launched for this experiment.
