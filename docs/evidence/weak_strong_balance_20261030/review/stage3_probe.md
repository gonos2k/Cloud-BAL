# Stage 3: rain number initialization probe

This was a read-only source and provenance inspection. No native source was edited; no build or forecast was run. Exact paths and SHA-256 pins are in [`stage3_probe.json`](stage3_probe.json).

## What the source shows

The base KDM6 source is `/var/tmp/firsthour-runtime-plan-20261030/experiment/build_BASE/module_mp_kdm6.f90` (SHA-256 `c4a7d1e90ea27608ba7efb652cfb79dee2e30db769e076ad1a2e7a7e63d5e52b`). The build receipt records its preprocessed companion (`module_mp_kdm6.F`, SHA-256 `49cf8b0e3905a8d584073fdf3345ddfa64a0b0bac178676584505f7c4d7187ca`) and a BASE rebuild whose executable hash exactly matches the retained `de110a7f…c168` executable. The fixed build differs at the single limiter branch in `candidate.patch`: `else` becomes `else if (prevp(i,k).ne.0.)`.

The driver copies `QRAIN` to internal `qrs` and converts `QNRAIN` to internal `nrs=nr*den`; it later writes `nr=nrs/den`. It does not seed rain number when rain mass is positive and rain number is zero. The rain PSD reconstruction uses both moments and is gated on `qrs>=qcrmin` and `nrs>=nrmin`. The slope routine selects its fallback slope below either threshold, but never creates `nrs`. Since `n0r` is calculated from `nrs` and the slope, a zero `nrs` gives zero `n0r`.

The retained first-inner-call capture provides a direct selected-cell example from the HYDRO arm, with the original executable hash and its own input manifest binding: at `P05_00`, call-entry `qrs=2.84018e-4 kg kg-1` while internal `nrs` is exactly float32 zero. The raw captured rain-rate expression has a negative humidity factor, a positive-zero REAL64 operand at stack offset `0xe8`, and yields float32 negative zero. Source ordering makes `n0r` the likely identity of that operand, but the executable has no debug symbols, so this operand-to-symbol mapping remains an inference. It is not inferred from an unrelated Fortran fixture.

In the baseline branch, signed zero fails `prevp<0`, so the `else` applies `min(prevp,satdt/2)`. With `satdt<0`, this can turn a zero rate into negative evaporation. The fixed `else-if` skips this clamp for either signed zero. In source, `prevp` updates rain and vapor with opposite signs, and enters temperature through the latent-heat term `xl*prevp/cpm`; suppressing an artificial zero-origin rate therefore affects all three coupled fields. The patch changes this rate guard only. It does not provide the missing rain-number moment.

Initial input samples independently show positive `QRAIN` with zero `QNRAIN` in 210 of 624 selected mapped samples in each of three retained input arms. The sample includes the original `wrfinput_d01` hash used by the lower-factor runs. The sample is not a whole-domain census and does not prove every field value passed unchanged into the first physics call.

## Implication for a next experiment

There is no unique way to infer a rain-number moment from rain mass alone: multiple particle size distributions can have the same `QRAIN`. KDM6's existing two-moment slope closure requires both mass and number. Before proposing an initializer, trace the authoritative QRAIN/QNRAIN analysis or initialization writer and identify its intended PSD or observational constraint. Seeding `nrmin` without a distribution rationale would not establish physical consistency. Any proposal should be evaluated with coupled rain, vapor, and temperature budgets.

This probe does not establish a skill improvement, full historical source provenance, a full-host clean build, or a validated rain-number initializer.
