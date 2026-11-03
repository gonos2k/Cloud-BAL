# Source and archived build review

Graphify was queried first for KDM6 caller/callee relationships. It identifies `kdm6()` in `module_mp_kdm6.F` and `kdm62D()` as the inner 2-D step, with existing prior capture proposals around the KDM62D call. Direct source inspection confirms the relevant facts below; graph results are navigation only.

- `kdm6` is called per microphysics step and receives `itimestep`; its `j` loop converts `nr` to number concentration `nrs = nr * den`, invokes `kdm62D` once per row, and converts the result back to `nr = nrs / den`.
- `kdm62D` performs nonnegative clamps at entry, computes liquid/ice `qs` and `rh` at the start of each microstep loop, computes `satdt`, computes `prevp` from `rh`, `n0r`, `rslope`, and `work1`, multiplies by `fac_evap`, then applies the condensate and saturation caps. The limiter's associated process rates are further scaled in `source` / `factor` blocks before state update.
- The BASE→FIX source delta is exactly one branch guard at the positive `prevp` side: `else` becomes `else if (prevp(i,k).ne.0.) then`. Source equations and all remaining state updates match.
- Archived BASE/FIX WRF executables are exactly the pinned native hashes and linked with the same adjacent host tree/libraries. BASE/FIX source hashes are in `pins.json`.
- The existing `producer_pair/forecast/run_POLICY_BG` stage is a verified 89-file 8-rank 1-hour FIX case using the B1 initial input. `inputs.json` pins it, the exact initial input, common boundary and namelist. `receipt.json` records success, exact history times, and unchanged staged inputs.

## Extraction limitations

Graphify extraction is a navigation aid; its very large graph (43,201 nodes) returned a broad 331-node query and truncated most matches at the initial token budget. The native source/build receipts are authoritative for the statements above. No Graphify incremental update was run because this scratch-only preparation changes no maintained corpus. KLAPS50's maintained graph snapshot remains the separate 2026-10-30 dated snapshot; Cloud-BAL evidence remains separate. No runtime/scientific validation is inferred from those snapshots.
