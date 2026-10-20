# PR91 host storage and repeated consumption — 2026-10-20

## Preserved reference

The reference is merged PR90 (`3a896be3d381909f0cc61d1c0896b329b98d5aea`), C7. OFF and COUPLED each completed 180 seconds and nine KDM6 calls. Their 600-second requests stopped at T10 RK3 with six host `FULL` rejections: cloud `(130,182,2)` and graupel `(194,80,22)`, `(132,201,19)`, `(196,211,16)`, `(168,225,20)`, `(231,240,20)`. Those rounded, recomputed records do not identify the actual store failure stage.

C7 remains the reference. Its initial inputs, physical sources, FP policy, receipts, and failed longer requests are preserved. New source, build, and run identities are separate.

## Current status

C7 remains the accepted 180-second research reference. D3 reproduced its T10 rejection with an exact prefix. C9 and C10 are failed repair candidates, not replacements for C7. C11d is an OFF-only diagnostic replay of C10 and reproduces the same fourteen state records through its T2 failure. C12 passed two completed timesteps (40 seconds) but both 240-second requests stopped at the T3/RK3 physical-source checkpoint. C13 is the frozen follow-up candidate, with paired 240-second requests running. No new 240-second or 600-second completion is claimed.

## Exact diagnostic path

`tools/pr91_host_store_trace.py` transforms the hash-pinned C7 embedded host and shared core. It captures the existing store's `failure_stage`, attempted scale, exact candidate and source/transport words, density/carriers, bounds, options, and stored sentinels at the actual failing call. The six-coordinate capture is diagnostic selection, not a cell-specific state correction. The old recomputed `FULL` records remain distinct.

The existing graupel-only probe also reports its rejection reason. When the existing donor-mixture store rejects, the diagnostic records its original weights and donor terms rather than manufacturing a different proposal. Baseline and source-first attempts are distinguished. Failed trials retain the existing all-pair rollback behavior.

The host trace uses public dry-air-specific moments: Q is kg/kg dry air; cloud/rain/ice N is number/kg dry air; graupel B is m³/kg dry air. Dry density is kg/m³ and dt is seconds. `oldcarrier`/`newcarrier` are the native hybrid dry-pressure carriers `C1*(MU+MUB)+C2`, not kilograms. Their source/transport rates carry that pressure weight per second. The minimum/maximum Q/N ratios are particle mass for numbered categories and bulk density for Q/B. These host operands must not be read as KDM6's internal number/m³ or summed directly as a global kg budget.

This diagnostic configuration requires an explicit `PR91_RUN_ID` and writable run directory. Missing identity or diagnostic I/O failure is fail-closed; no claim is made that these new diagnostic-error paths match the uninstrumented host. Under the declared configuration, the diagnostic does not change physical equations, candidate operands, input priors, or FP policy. Prefix identity must be checked from actual runtime data.

The final diagnostic build is PR91-D3, executable SHA-256 `89812febe43ac6afb7388e5aed7395614527c46ffee8c9eb3dcbad1ba807f97a`. It is a pinned Intel selected-object partial-host build, not a full clean WRF build. See [diagnostic validation](evidence/pr91_host_store_20261020/validation/README.md).

## Runtime and repair gates

The OFF 200-second diagnostic request closed `INCOMPLETE`, return code 1, after nine completed steps and the same T10 RK3 fatal. Its first 73 complete trace records (7,537,409,380 bytes) are byte-identical to the preserved C7 OFF 180-second reference. See [the closed diagnostic binding](evidence/pr91_host_store_20261020/diagnostic_d3/closed_run.json).

The six selected coordinates produced 17 failed-store records across T10 RK1/RK2/RK3 and baseline/source-first attempts. Pinned Intel O0/O2 reconstructed every candidate from its exact operands and reproduced every failure stage, adjustment, and stored sentinel. Fifteen graupel records fail the continuous strict mass-ratio gate (stage 2); the two cloud records fail the continuous volume-number gate (stage 3). The pre-existing certified graupel-mixture fallback allows earlier T10 RK stages to proceed. These targeted records are not a count of every store failure in the whole domain.

The source-first cloud endpoint itself passes both the old mean-mass policy and the existing mean-mass-plus-volume policy unchanged. Adding the recorded later non-air source already moves its virtual donor outside the strict PSD domain, before air transport. Thus connecting the two endpoint store calls aligns their contracts but is not an established repair for the observed state sequence.

The C8 endpoint-contract candidate compiled as a separate partial overlay (executable SHA-256 `e9b1f40ed01a1c9072f142524a167d475690329eaa9a13248e4f429afc18cd80`); no C8 native run has been started. Source inspection identifies an old-state horizontal diffusion contribution being combined with the prepared physical-source endpoint. A follow-up candidate will reuse the existing diffusion operator and RK1 geometry on the complete prepared field, replacing the captured old diffusion contribution exactly once while retaining other later terms. This changes transport evaluation order and must be accounted separately from storage rounding. A common cause repair, paired 240-second completion, and subsequent same-executable 600-second requests remain pending.

### Source-first diffusion candidate C9

The actual RK1 producer now retains its existing REAL64 horizontal diffusion contribution for QC/NC and QI/NI, with timestep/RK/bounds identity and per-channel capture flags. The source-first consumer first completes the physical-source REAL32 endpoint field and keeps the specified boundary donor ring unchanged. It applies the same existing horizontal diffusion operator to that complete field using the saved RK1 `muts` geometry, then adds `D(prepared) - D(old)` once to the existing later-source residual and precision correction. Other later terms remain once; scalar `advect_tend` is separate from that residual.

This changes the state on which the existing transport operator is evaluated. It does not add a new precision, tolerance, PSD prior, particle-number floor, or graupel correction. The added old-diffusion cache holds four REAL64 channels (32 bytes per memory-grid point); temporary prepared fields are limited to the existing source-first path. A per-pair signed `dt * [D(prepared)-D(old)]` summary has pressure-coordinate units and must be distinguished from pure storage rounding and from physical phase/source transfer. It is written while forming the candidate, before the all-pair transaction gate: it reports a proposed evaluation delta, not an independently committed change. Only a matching successful timestep/RK transaction establishes that candidate was applied; failed attempts remain separate. Boundary flux is required before claiming a global conservation result.

A pinned Intel O0/O2 closed shared-face fixture uses different Q and N values, executes the copied donor formula, and checks that replacing stale old-state diffusion restores the prepared pair without changing the boundary donor ring. That manufactured fixture compiles the maintained REAL64-internal stencil with exact dyadic coefficients; it is not a bit replay of the native C9 module’s embedded `pr87_horizontal_diffusion64` stencil, which uses REAL128-internal arithmetic with the same REAL32/REAL64 API. The separate `pr90_cycle_support.f90` observer remains separately hash-bound and unchanged; it is not the embedded diffusion stencil. The native C9 partial overlay compiled and passed its source review, but both 240-second requests closed INCOMPLETE after T20, at T2 RK3 before the diffusion replacement. C8 had applied the final continuous volume condition too early at the temporary physical-source endpoint. The exact-decimal T2 fixture passes the original strict mean-mass source store but fails C8 at volume stage 3. Its temporary stored output also fails the final dual-product volume predicate. The existing final store can represent that temporary pair with its existing directed-Q adjustment: `34784CDA/4C529864` becomes `34784CDB/4C529864`, stage 0, adjustment 2, in pinned O0/O2. This is a store-level regression result, not a completed native source/diffusion/air-consumer proof. The temporary field must not be presented as a complete internal-number consumer state.

C10 retains the existing source-endpoint mean-mass policy and the diffusion state/order repair, without C8's premature final-volume gate. The temporary public Q/N field is consumed by public-moment diffusion; the complete host commit and subsequent KDM6 consumption still require the existing strict volume/storage contract. This distinction changes no tolerance. C9 remains a failed candidate. C10's four focused tests and fresh partial-host build passed, but both 240-second requests closed INCOMPLETE after T20 at T2 RK3: `PR87 unsafe complete source-prepared virtual donor`. The premature endpoint volume gate was passed, then the proposed prepared-diffusion path failed its later donor guard before a successful transaction. The recorded diffusion delta is proposed, not applied. At that point the generic message did not identify a negative, orphan, or underflow cause. The later C11d replay below supplies the exact guard operands. No paired 240-second or 600-second completion has been obtained by this repair yet. C11d adds only failed-guard operand/stencil capture to C10, with a pinned Intel O0/O2 17-record writer fixture and an instrumentation-only source comparison. The OFF 40-second diagnostic closed INCOMPLETE, return code 1 after T20, with exact T2 RK3 pair-1 failure operands at `(233,62,1)`. Its fourteen state records are byte-identical to C10 OFF. The native embedded REAL128 kernel and captured stencil reproduce positive prepared diffusion Q `3B39C82BC6F72E40` and N `3DEEDC08DA77C3AC`. The C10 expression cancels Q to zero while retaining a positive N rate (`3DF0000000000000`), yielding the captured orphan donor `0 / 3D2B7A7AA1B95EA2`. These are normal-range R64/R32 values; no underflow or negative-input cause is inferred. The diagnostic applies only to OFF, not an observed COUPLED coordinate.

### C12: separate the producer contributions before cancellation

C12 retains the REAL32 tendency immediately before and after the original horizontal-diffusion call. At the existing RK1 final capture, before the original coupled tendency is overwritten, it computes

```text
nonD64 = (REAL64(final32) - REAL64(afterD32))
       + (REAL64(beforeD32) - REAL64(original_coupled32))
source_first_rate64 = nonD64 + D(prepared)
```

Both parenthesized differences are evaluated separately. The source-first physical arithmetic no longer subtracts the large old diffusion contribution. The original normal candidate path and its later/precision caches remain unchanged; `D(prepared)-D(old)` remains only a proposed evaluation-delta ledger. Four before/after REAL32 pairs and four REAL64 non-diffusion channels add 64 bytes per memory-grid point, in addition to the earlier four-channel REAL64 old-diffusion cache. No precision or particle-state tolerance is added.

The prepared field covers the active interior. The existing outer donor ring remains explicit old-time boundary data for this restricted one-domain, one-tile operator; it is not a claim that physical sources have been applied to unused halos. Boundary-flux and global conservation evaluation remain open. Producer finite checks cover the captured active footprint, and consumers require the same timestep, producer RK, bounds, and all four ready channels.

The C12 source-form regressions passed. Both paired 240-second requests closed INCOMPLETE after T40, at the T3/RK3 temporary source checkpoint, not at the repaired virtual-donor arithmetic. The completed two-step prefix passes the scoped state audit. The existing 600-second request was not repeated with this known failure.

A repair must distinguish continuous-domain failure, representable storage, unit roundtrip, and source/donor/geometry identity. It must validate all pairs before committing a host state. No density tolerance expansion, isolated number clipping, new moment prior, or precision expansion is authorized by the diagnostic result alone.

## Parallel physical interpretation

- [Preserved C5/C7 history response](PR91_HISTORY_RESPONSE_20261020.md): C7 pressure/Phi/native-face W maps and fixed-location trajectories through 180 seconds, with C5–C7 interaction at common 0/60/120 seconds.
- [Science source audit](PR91_SCIENCE_SOURCE_GAPS_20261020.md): current area-weighted first-failure-associated AUT/G proxies and the remaining original-support mapping requirements.

These diagnostics do not establish water/energy closure, observation skill, native continuity/momentum closure, or reduced initial shock. The fixed 27-column difference support is descriptive. Graph freshness is separate from runtime and scientific validation.

## C12 build and runtime identity

The fresh pinned Intel selected-object partial-host build succeeded. Its executed candidate SHA-256 is `53b13b18931bcc8b3244574df8b0296d7db6550078ab75682de1587a53140123`; module source is `fcdc8f34b523aa83adcf7f60a049e27aba5f1975c264bb7118bb7efe62120a5f` and solve source is `d0ff9110811811c01ad13709bf5b538f7b92a49739211b0519aac55a81bc04a6`. The paired 240-second requests used the same candidate and unchanged arm-specific inputs. Both closed INCOMPLETE (return code 1), with two completed KDM6 calls and a T3/RK3 pair-1 source-stage rejection at `(162,132,3)`. See [the closed prefix audit](evidence/pr91_source_store_contract_20261020/c12/runtime/closed_runtime_audit.json). See the [frozen source/test bundle](evidence/pr91_source_store_contract_20261020/c12/README.md).


### C13: FogDES must use the actual source consumer

The C12 failure occurs before prepared diffusion, in the strict mean-mass-only temporary source store. That call has no volume-number bounds. FogDES's source-present trial instead tests `q >= m_min * n`; the host store tests `q/n >= m_min`. In the serialized failure operands, the binary64 product rounds to equality while the quotient is one representational step below the minimum. A trial and its actual consumer therefore disagree without any tolerance in either comparison.

The focused follow-up will call the existing host `joint_moment_store` from the FogDES source-present trial with the same strict mean-mass and representation options. The original column-wide shared flux factor, paired Q/N transfer, ground sink, source corrections, and rollback remain responsible for the accepted packet. It will not add a PSD floor, change a density limit, or apply the final KDM6 volume constraint prematurely. C12 host/solve source remains frozen; C13 changes only the FogDES trial predicate. Independent source review and pinned Intel O0/O2 fixtures passed. The positive-flux fixture uses the source-present interface and checks nonzero common Q/N transfer, ground accounting, and strict-store validity; the captured marginal packet is an expected-rejection predicate replay. A fresh selected-object build passed and the paired 240-second requests are running. The frozen FogDES source SHA-256 is `bd983a8c1d65b007e6e9d0b07b4ec63efadd33a606a9692d3dd52ba990ee88f7`, and executable SHA-256 is `69c0f5fb394917aab999e073fc05671ba208502fc58c6bd17b2e860bf5cf0c87`. The original C12 host/solve sources and arm-specific inputs remain unchanged. Closed run receipts are required before acceptance.
