# C14 cold-process alpha constraint audit

## Source pins

- C14 host source: `docs/evidence/pr91_source_store_contract_20261020/c14/module_em.F`, SHA-256 `6a7a97c23c84f05837a3bb5e384ce944ecd2df220ea1889d990349cd509094b1`.
- C7 KDM6 source used by the current overlay: `/var/tmp/pr90_sources_c7_20261019/module_mp_kdm6.F`, SHA-256 `983095a0aa0c76eab4efdda27f9435e61634e08e542ef9bd096aa4cf8004eca4`.

## What existing diagnostics establish

`kdm6_rain_process_fraction` searches a REAL32 fraction and validates the joint trial state in `validate_trial` (source lines 521–1037). `kdm6_rain_process_state_valid` checks donor finiteness/nonnegativity, temperature, cloud/ice/rain moment pairs and PSD bounds, the ice transient exception, and graupel bulk-density pairing (1161–1321). A separately computed vapor check is applied by the caller. The selected G fraction is after NG and AUT have already modified the fixed state.

`PR87_ADMISSION` records the first failed reason for the full-proposal endpoint and explicitly documents that it is not a unique active-bound certificate (header at 2514; calls around 5401). It does not capture the trial state or test competing predicates at the selected alpha. The detailed `PR85_KDM6_COLD` record schema would include proposal, approved, withheld, and stored residual values, but its writer is guarded by `.false.` (around 5912); current runs therefore have a header without detail rows. `PR89_KDM6_COLD_SUMMARY` and `PR90_KDM6_COLD_COLUMN` retain only weighted aggregate signed/half-L1 request activity by process group and proposed/applied/deferred stage (2488, 6746, 6755). They omit the local state, alpha, predicate outcomes, and per-loop process candidate. Neither those compact summaries nor the first-call endpoint reason identify the predicate that limits the selected alpha.

## Minimum diagnostic to identify the active constraint

At the actual G search, capture the cell/loop/timestep and exact REAL32 bits for selected `alpha` and `alpha_hi=nearest(alpha,1.0)`. Record the fixed state after admitted NG/AUT (`Q(5),N(3),BG,T,QV`), the requested G process deltas for those fields, and all validator parameters (`rho`, `pidnr/pidnc/pidni`, mass powers, lambda bounds, cutoffs, pending/cleanup flags, and the ice transient limit). Also record whether volume-rate conversion was feasible, search status, composite gamma/retry, and whether a post-fraction REAL32 storage/public-store gate is actually applied.

For both `alpha` and `alpha_hi`, emit a predicate bitmask with separate checks for finite/nonnegative donors, temperature, cloud PSD, ice PSD/exception, rain PSD/zero-pair rule, graupel nonnegativity and bulk-density, vapor, and each actual storage/public-store check. Record composite-rate feasibility and gamma/retry as proposal context, not as an alpha constraint unless the source actually uses them as one. The selected alpha passes the conjunction; the next representable alpha should fail at least one predicate for a locally maximal result. Keep the full-proposal endpoint reason as a separate field: its first-failure ordering is not the active-alpha result. If alpha is nonpositive or search status is not feasible, record the corresponding base/unsupported-rate/search-failure path instead of assigning an active physical bound.

This is a source-derived diagnostic requirement, not a diagnosis of any particular runtime event.
