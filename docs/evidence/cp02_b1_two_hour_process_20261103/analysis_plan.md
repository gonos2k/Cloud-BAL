# B1 OLD/FIX first-two-hour diagnostic analysis plan

Status: analysis plan only. No native trace was parsed or run while the strict-prefix gate is pending. This plan does not change the frozen cohort, any rain-number policy, model source, or production behavior.

## Frozen comparison and locations

Use the same B1 input for both arms: OLD `ORIGINAL_B1_100` and FIX `IMPROVED_BG_FIXED` (`wrfinput_d01` SHA-256 `9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5`). The fixed arm's retained histories are from `/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED`; runtime receipts bind its input and 12Z–14Z outputs. Do not substitute `FIXED_ORIGINAL_100`, which uses the ORIGINAL input.

The four points are the frozen posthoc diagnostic cohorts. Each has four native mass-grid corners and interpolation weights in `cohorts/corners.csv`; this is a point remap stencil, not a conservative area budget.

| Point | Cohort | RN1 +1 h | RN1 +2 h | OLD +1 / +2 h | FIX +1 / +2 h |
|---|---|---:|---:|---:|---:|
| P01 | Weak hit lost | 0.0 mm | 0.2 mm | 0.000064 / 0.333770 mm | 0.00000009 / 0.080582 mm |
| P02 | Weak new false alarm | 0.0 mm | 0.0 mm | 0.000096 / 0.023862 mm | 0.013398 / 0.829999 mm |
| P03 | Weak stable hit | 0.0 mm | 0.5 mm | 0.005684 / 0.693336 mm | 0.00000028 / 0.427701 mm |
| P04 | Strong stable-hit fallback | 1.6 mm | 9.4 mm | 13.511116 / 60.446189 mm | 13.322853 / 62.837957 mm |

The table reports separate one-hour windows ending 13Z and 14Z. Keep each hour and point distinct; do not average cases, points, leads, or thresholds. P04 is the explicit fallback because the +5 mm hit-gain cohort is empty.

## Gate and chronology

1. Wait for the native runner's strict-prefix validation. Do not open, decode, or interpret trace records before it passes.
2. After the gate, bind all analysis to the candidate patch SHA-256 `94f109e624aa0b3b25689db20b1ac1acb4122920288d3765499147ed385fea3e`, the OLD/FIX executable and input receipts, and the runtime's exact `Times`/timestep metadata.
3. Candidate logging is gated to `1 <= itimestep <= 360`. Establish from the run's actual WRF `time_step`, start time, and 12Z/13Z/14Z `Times` whether that prefix covers both forecast hours. Do not assume 360 steps equals two hours. Keep the trace key `(rank, call_id, itimestep, loop, j, i, k)` intact; call IDs can repeat across ranks and each cell may have multiple internal loops/calls.
4. Check that each selected corner has the expected 39 levels and chronology. Treat missing, duplicate, reordered, or rank-inconsistent rows as coverage failures; do not silently fill or interpolate absent trace records.

## Decode and source-equation audit

The patch records `ENTRY_RAW` and `ENTRY_CLAMPED` states (`q`, `t`, `den`, cloud/rain/snow/graupel mass and number moments, and `brs`), followed by `SATURATION`, `SATDT`, `PREVP_FORMULA`, `PREVP_RAW`, optional `PREVP_QR_CAP`, `PREVP_SAT_CAP`, `PROCESS_RATES`, `PRE_UPDATE`, `LATENT_INPUT`, and `POST_STEP`. Wrapper records are `SURFACE_RETURN` (`rainncv`, `rain`, `sr`) plus optional snow/graupel returns. Decode the ordinary `transfer(value,0)` fields as their recorded REAL32 bit patterns. `n0r` is declared `double precision` in the pinned KDM6 source and is emitted with `transfer(n0r,0_8)`; preserve/decode it as a REAL64 bit pattern, not a REAL32 value.

The source conversion is `nrs = nr * den` on entry and `nr = nrs / den` on return. With `nr` in number per kg and `den` in kg m⁻³, internal `nrs` is number per m³. Do not substitute dry density for the captured runtime `den`; compare captured `den` at the same corner, level, call, and step to the two source-derived diagnostics `1/(AL+ALB)` and `(1+QVAPOR)/(AL+ALB)`, clearly labeled as comparisons only. `AL`/`ALB` are available from the common B1 initial file, not the hourly WRF histories; `QVAPOR` is available in the histories. The existing lineage says the caller/solver source copies are not build-bound to this executable, so no density identity is presumed.

`n0r` is a double-precision state reconstructed from both rain mass and number. In the exact source, `mur=1`; the baseline expression is `n0r = nrs/(rslope*rslopemu*g1pmr)`, with the guarded lambda reconstruction when `qrs >= qcrmin` and `nrs >= nrmin`. A zero `nrs` does not itself define a finite mean drop mass or demonstrate a number seed. Do not import the Thompson-only initializer into KDM6 or change `nrmin` policy.

For evaporation, preserve the phases separately:

- `PREVP_FORMULA`: source expression before `fac_evap`, proportional to `(RH−1)*n0r` and the source's slope/work factors.
- `PREVP_RAW`: after multiplication by `fac_evap`, before the rain-inventory and saturation bounds.
- `PREVP_QR_CAP`: after the source's `−qrs/dtcld` lower bound, when that branch is taken.
- `PREVP_SAT_CAP`: after the subsequent saturation-rate bound.

The current patch logs `PREVP_FORMULA`, `nrs`, `qrs`, `den`, `RH`, REAL64 `n0r`, and `fac_evap`, but omits several formula operands (`work1`, `work2`, `coeres`, `rslope2`, `rslopemu`, `precr1`, `precr2`). Thus the staged records can locate the raw-to-capped change and compare arms, but cannot by themselves replay the complete uncapped expression bit-for-bit. Keep this limitation in the report; do not reconstruct missing operands from assumptions.

## Per-step scalar checks

Use source order and the actual recorded branch. For each cell and `dtcld`, report:

- Vapor update residual: `r_qv = (q_post − q_pre) − work2*dtcld`.
- Temperature update residual: `r_T = (t_post − t_pre) + (xlwork2/cpm)*dtcld`.
- Rain-evaporation pair: `Δqv_PREVP = −PREVP*dtcld`, `Δqr_PREVP = +PREVP*dtcld`; this pair cancels before floors and other species transfers.
- Number update: compare `nrs_post` with the source's `max(0, nrs_pre + (nraut−nrcol+nseml+ngeml)*dtcld)` when that branch applies, then verify the host conversion `nr=nrs/den`.

The source latent expression to audit is `xlf = xls − xl`, `xlwork2 = −xl*(prevp+psevp+pgevp) − xlf*(pseml+pgeml)`, and `Δt = −xlwork2/cpm*dtcld`. Report the signed operands and residual; do not label a heating/cooling mechanism until signs and the applicable branch are observed. Check positivity floors separately from source tendencies so clipping is not counted as a process.

For surface precipitation, reconstruct each hour from native histories as `H13−H12` and `H14−H13`, where `H = RAINC + RAINNC`; the two-hour total is `H14−H12`. Compare that independently reconstructed amount at each frozen RN1 point with the canonical saved arrays and the trace's `SURFACE_RETURN` fields. Keep `rainncv`, `rain`, and `sr` as returned components until their units and accumulator role are bound; the saved forecast verification excludes the separately checked zero `RAINSH` component.

These are local tendency and remapping checks. Four points × four corners do not establish a full column or domain water/energy budget.

## Suggested core figures

1. **Four-point map and stencils:** RN1 targets, four native WRF corners, and weights; label the three weak groups and P04 fallback.
2. **Hourly precipitation comparison:** for each point, separate +1 h and +2 h RN1/OLD/FIX amounts, with a separate +0–2 h cumulative total. Use consistent units and keep near-zero amounts readable; no pooled or averaged score.
3. **Microphysics phase timeline:** point-specific OLD/FIX curves or distributions for `PREVP_FORMULA`, `PREVP_RAW`, and each cap result across actual timesteps, with call/loop chronology. Pair these with `q`, `qr`, `den`, `nrs`, `n0r` and latent residual panels; show four points separately. Annotate absent/missing terms and do not present the plot as causal attribution.

A compact scalar table can carry the remainder: hourly/cumulative surface totals, maximum absolute `r_qv`/`r_T`, PREVP raw-to-capped change, number conversion consistency, and exact retained coverage by point/hour/level. Report OLD and FIX as separate columns and retain unrounded values in CSV.

## Identity pins and limits

- Frozen cohort receipt SHA-256: `1858711adc90579ffebb0990d8de7721ced46eeadbbe0499b764dbda3af4f107`.
- Frozen cohort selection SHA-256: `f5cfbedce388ab3ccb852aa78837eca26ae5f2056cede9fa2a5d3b1aefd51fbc`.
- `candidate.patch` SHA-256: `94f109e624aa0b3b25689db20b1ac1acb4122920288d3765499147ed385fea3e`.
- KDM6 source SHA-256: `c4a7d1e90ea27608ba7efb652cfb79dee2e30db769e076ad1a2e7a7e63d5e52b`.
- Rain-number lineage note SHA-256: `6e8b34c4f52a4c06f988a9e0c705094a5f745fc5633c03fa4c7755a4314583c6`.

The lineage note explicitly says the exact B1 initializer and runtime density basis are not established. Results from the forthcoming selected-point trace can establish what these pinned OLD/FIX runs recorded at these points; they do not alone establish upstream initialization policy, process causality, complete budget closure, independent-event performance, or production approval.
