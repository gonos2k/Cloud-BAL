# RK-stage diffusion geometry lineage review

## Scope and pins

This is a read-only source-lineage review for the V49 candidate inputs, not a finding that the later native failure has been fixed.

- `solve_em.F`: `/var/tmp/pr87_followup_sources_20261019_v49/solve_em.F`, SHA-256 `9819ecab5e329cde214995bd192b1d6fee847809d8629498a3e5fe1c5b1de76f`
- `module_em_pr85.F`: `/var/tmp/pr87_followup_sources_20261019_v49/module_em_pr85.F`, SHA-256 `4d07170e68699e62276eb3ec800c123b6993e91cdaa9aae2411b4909c34a14c0`
- Build-preprocessed `module_first_rk_step_part2.f90`: `/var/tmp/pr87_followup_build_20261019_v49/preprocessed/module_first_rk_step_part2.f90`, SHA-256 `d5b3eca8b6aeecd2d13c03407c16361743aa1f0f264ad154f1dd77c1c35a0fbd`

## Geometry producer and consumer path

`solve_em.F` calls `small_step_prep` with `grid%muts` as an output at lines 1134–1152, then calls `advance_mu_t` with `grid%muts` at lines 1436–1453. These operations are in the RK acoustic small-step sequence, which is repeated as the main RK loop advances. This establishes `muts` as live stage mass geometry, not an invariant grid map. The source bundle does not include the implementation of `small_step_prep` or `advance_mu_t`; this conclusion uses their caller interfaces and observed in-call placement, rather than asserting implementation details absent from the pinned bundle.

The moist tendency call at `solve_em.F:2268–2284` passes `grid%muts` and the horizontal geometry/coefficient fields (`c1h/c2h`, `msfux/msfuy/msfvx/msfvx_inv/msfvy`, `msftx/msfty`, `rdx/rdy`, and `xkhh`). The joint replay call at `solve_em.F:3076–3094` also passes the then-live `grid%muts`, `grid%xkhh`, and `msf*` factors on every RK stage. In `module_em_pr85.F:2241–2247`, the rain diffusion capture invokes `horizontal_diffusion64` with the `mut` and geometry actual arguments supplied to `rk_scalar_tend`. Thus an RK1-captured diffusion source replayed with RK3's live `muts` can evaluate a different operator geometry.

The capture snapshot location proposed for `muts`—immediately before entering `moist_scalar_advance` on RK1—is appropriately late: it is after the RK1 small-step mass updates, and before the moisture and scalar `rk_scalar_tend` calls that capture diffusion. The field is passed through as `mut`; the helper interface does not update the caller's mass field. Capturing in the earlier first-RK physics section would precede the small-step mass state used by diffusion and would bind the wrong geometry epoch.

The other passed geometry fields do not show a comparable stage producer in this caller path. `xkhh` is computed by `calculate_km_kh` in the first-RK path (`preprocessed/solve_em.f90:762–774, 1080`; `preprocessed/module_first_rk_step_part2.f90:835–844`) and then passed to later RK calls. The map metrics/coefficient arrays are passed through the solve path but are not assigned there in the inspected call sequence. This is a scoped caller-lineage observation, not a repository-wide immutability proof.

## Limitation

This geometry review does not prove source identity. The scalar fields supplied to diffusion also evolve by RK stage, so replay against the RK1 field and RK1 `muts` must be established independently. Keep the existing exact field/source identity gate; a saved geometry snapshot alone is not evidence that the native RK3 failure has been resolved.
