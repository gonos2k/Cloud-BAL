# B1 first-two-hour KDM6 report skeleton

**Status:** equations and interpretation plan only. No native trace was read. Populate result fields only after both runs pass the strict 12Z/13Z/14Z prefix comparison for every shared history variable and metadata item.

## Decision context

The experiment is same-initial-condition OLD (`ORIGINAL_B1_100`) versus FIX (`IMPROVED_BG_FIXED`) with the common B1 input (`wrfinput_d01` SHA-256 `9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5`). No new `Nr` seed is inserted; whether the original B1 state had a seed remains unresolved. The phase-2 question is whether FIX offers weak-event CSI recovery while retaining the current B1 first-hour six-hit result and every lead at the 5 mm gate. No score change or forecast improvement is asserted here.

Keep the four frozen points separate: weak hit lost (P01), weak new false alarm (P02), weak stable hit (P03), and the strong stable-hit fallback (P04; the +5 mm hit-gain cohort was empty). Each uses four native mass-grid corners; this is not an area budget. Report +1 h and +2 h windows separately, then 0–2 h total separately.

## Source basis: density and water increments

Pinned archived BASE source: `module_mp_kdm6.f90`, SHA-256 `c4a7d1e90ea27608ba7efb652cfb79dee2e30db769e076ad1a2e7a7e63d5e52b`.

The wrapper copies `qr` into `qrs(:,:,1)` and passes vapor `q` directly to `kdm62D`; on return it copies `qrs(:,:,1)` back to `qr` (source lines 304–317, 327, 346–355). It does **not** multiply/divide either mass field by `den`. It does multiply number: `nrs = nr * den` on entry and `nr = nrs / den` on return (lines 314–317, 355–358). Under the analysis plan's bookkeeping (`nr` number/kg; `den` kg m⁻³), internal `nrs` is number/m³. That number conversion does not imply a density conversion for `q` or `qr`. Runtime `den` basis remains unresolved; retain captured `den` and do not relabel it dry-air density.

At the source update, rain evaporation `prevp` enters vapor and rain with opposite signs:

- `work2 = -(prevp + other vapor terms)` and `q_post = q_pre + work2*dtcld`.
- `qrs_rain_post = max(qrs_rain_pre + (other rain terms + prevp)*dtcld, 0)`.

Thus the isolated pre-floor pair is `Δqv_PREVP = -prevp*dtcld`, `Δqr_PREVP = +prevp*dtcld` on the same source mass-variable basis; it cancels algebraically. There is no `/den` in these state increments. If WRF `q`/`qr` are interpreted as kg kg⁻¹ mixing ratios, `prevp` is kg kg⁻¹ s⁻¹ and the pair is per unit air mass. Keep that unit label conditional on the WRF field convention; the KDM6 wrapper establishes the shared basis and lack of a `den` factor.

Sign convention: `prevp < 0` depletes rain and adds vapor (evaporation); `prevp > 0` removes vapor and adds rain. The formula is evaluated only when rain is positive (`qrs(:,:,1)>0`; source lines 1714–1736):

`prevp = (RH_liquid - 1) * n0r * (precr1*rslope2*rslopemu + precr2*work2*coeres) / work1`,

then multiplied by `fac_evap`, exactly `1.0` in this pinned source (lines 677, 1714–1720). `n0r` is double precision (line 590). Do not infer a seed or a mean-mass initialization from `nrs=0`.

Limits apply in source order: for negative `prevp`, `max(prevp, -qrs_rain/dtcld)` then `max(prevp, satdt/2)`; if it equals the inventory bound, rain number transfers into `nci(:,:,3)` and rain `nrs` is zeroed. For nonnegative `prevp`, apply `min(prevp, satdt/2)` (lines 1722–1735). A later rain-budget limiter can multiply `prevp` by `factor` (cold branch lines 2430–2443; warm branch 2605–2616). Distinguish `PREVP_FORMULA`, post-factor `PREVP_RAW`, cap checkpoints, and the final rate at `PROCESS_RATES`/`PRE_UPDATE`; a cap checkpoint is not necessarily the applied rate. The name `work2` is reused: before PREVP it is `venfac(p,t,den)` (source line 1616); it is later overwritten with the branch vapor tendency immediately before the q update (lines 2534 and 2666). Do not substitute that later value into the earlier PREVP formula. The trace omits formula operands, so it cannot replay the uncapped expression bit-for-bit (analysis plan, lines 35–42).

## Temperature response

Both temperature branches use `t_post = t_pre - xlwork2/cpm*dtcld`. The rain term in `xlwork2` is `-xl*prevp`, so its isolated contribution is `Δt_PREVP = +xl*prevp/cpm*dtcld`. For positive `xl`, negative `prevp` cools and positive `prevp` warms before other latent terms and branch coupling. Do not equate this isolated term with total `Δt`.

The cold (`t <= t0c`) branch uses `xlwork2 = -xls*(psdep+pgdep+pidep+pinud) - xl*prevp - xlf*(...)` (source lines 2582–2587). The warm branch uses `xlwork2 = -xl*(prevp+psevp+pgevp) - xlf*(pseml+pgeml)` (lines 2688–2691). Preserve these branch-specific signs. Residuals: `r_q = (q_post-q_pre)-work2*dtcld`; `r_T = (t_post-t_pre)+(xlwork2/cpm)*dtcld`. Check floors separately from process tendencies.

## Evidence to fill after the prefix gate

- Coverage: `[actual start/time_step/Times]`; `[selected corner × level × timestep × call/loop completeness]`.
- Same-input differences: `[per point/hour OLD and FIX surface totals]`; `[PREVP formula/raw/cap/final rate by trace chronology]`.
- Local checks: `[maximum |r_q|]`, `[maximum |r_T|]`, `[applied rain/vapor pair residual before floors]`, `[rain-number return conversion]`.
- Limits: four-point remap and selected levels/calls only; caller/solver source copies are not runtime-bound to the archived executable; no full-column/domain closure or process-causality claim.

This report skeleton uses `analysis_plan.md` SHA-256 `47969beffe57df39bf3e21be74041aa83ec2012d7c82fd3707032c309855ebf5` and the exact pinned source above. Graphify lookup surfaced a test fixture, not this archived source; the equations above come from direct source lines. No raw trace has been opened.
