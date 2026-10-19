# C7 600-second pair: incomplete at T10

Both 600-second model attempts are **INCOMPLETE**. OFF and COUPLED each returned code 1 after nine completed model calls through 180 seconds; the stage receipts record T10 but no T10 `POST_KDM6`. Both RSL error logs report the host failure:

`PR87 full joint moment candidate infeasible; see source/full diagnostics`

This is the host-side joint-moment candidate failure. It is distinct from the earlier KDM6 rain-store issue. The focused source-failure classification is separately documented in [failure_classification.md](failure_classification.md); its exact source sub-predicate remains open.

## Receipt and build bindings

Exact run receipts and preflight copies are archived per arm:

- OFF run receipt SHA-256 `d1802d60e5263ff5f2c02aee7b38e35bce274eb93e48bf3e40da75d113dd951d`; preflight SHA-256 `12eabb978ecb66430da85074a03b14a468863925a2ff9a63cf82bc5ab7bbb162`.
- COUPLED run receipt SHA-256 `4142a65a5a66e4b9b262c1a239218d60c21cb672a89b737d9f605fc597a66d53`; preflight SHA-256 `5bdc2b4338d38777d40d41a82892372383cb65e9eea6c5aa104600d5d3d69f0d`.

Both attempts use C7 build receipt SHA-256 `7a58ac2ae90eca9ffe0500515282b537e11db25ab9de8175856609bf812bba31` and executable SHA-256 `5f5599e38759a9e2be27a9e7e0977370592c92cab328062d07eb359bddd19572`. The receipts report no changed original/staged inputs, no processing errors, and an unchanged candidate build.

## Completed-prefix check and T10 tail

The independent [runtime comparison](runtime/) verifies run/preflight/build/executable/source/trace receipt bindings and compares the compressed stage traces as streamed data. In each arm the first 7,537,409,380 decompressed bytes match its C7 180-second trace exactly. The reference and candidate-prefix hashes are OFF `59ffbe79d42089f4d15589864977ad693f3f2544f4f6ccab431271cc16b8acb8` and COUPLED `f2e12c5559aafc59c9604aa285aa7dfec6c8b803ac7b56f338b5cac7d653dbeb`. This prefix is the same nine-call interval covered by the archived C7 180-second strict state audit; it does not make the 600-second attempt complete.

The extra 466,955,300-byte tail has five trace records for T10: three state records (`PRE_RK`, `RK_STAGE_END` RK1, and `RK_STAGE_END` RK2) plus two tendency records. There is no RK3, PRE_KDM6, or POST_KDM6. The existing stage reader reports an incomplete T10 sequence and a valid density contract on the three partial states. Its generic diagnostics show 16 negative-Q cells at each partial state and ice 8-ULP outliers of 2, 1, and 1, respectively. These partial-stage findings are not a completed endpoint gate and are not assigned as the host failure cause. T10 strict cloud/rain/graupel endpoint gates are not evaluated because their required endpoint records are absent.

The original generic ice status for the completed 180-second prefix remains whatever the preserved 180-second audit reports; this comparison does not promote or rewrite that result. No full 30-step strict audit was run because only nine steps completed. The runtime bundle includes per-arm prefix/tail JSON, the streaming comparison script, and its own hash manifest.

The full source-call count and global NR-cap / number budget remain open. No source or physics changes were made for this runtime attempt.
