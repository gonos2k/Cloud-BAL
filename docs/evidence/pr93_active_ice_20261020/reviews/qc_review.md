# PR93 QC evidence review

**Disposition: scoped approval; no blocker found.** This review checked the report, both generators, and the bound JSON evidence. It did not rerun metgrid, real.exe, or the native model.

## Identity and support counts

- The horizontal replay binds the reproduced `met_em` SHA-256 `5c896259…dda856e02`. `qc_chain.json`, `qc_vertical_composition.json`, and `vertical_probe.json` carry the same full-file hash. The vertical composition and probe also bind the same initialized `wrfinput` SHA-256 `6ed69cbd…060730`.
- The three support counts refer to different grids: 162 source pressure cells are 9 horizontal LAPS cells × 18 pressure levels; 624 native comparison points are 16 metgrid columns × 39 eta levels; 613 native points have nonempty composed QC links, leaving 11 compared levels without QC support. The report keeps these counts distinct.
- The fixed response mask is KJI-shaped `(39,280,232)`. It selects only levels with nonempty `composed_qc_source_links` and totals 613 cells across 16 columns. `load_history` removes the raw mass-grid outer ring with `[1:-1,1:-1]`; the mapping `target_i0,j0 → active indices i0-1,j0-1` matches that slice and array order.

## Runtime window and claim limits

- The receipt-bound OFF and COUPLED C18 history files have matching records at 0, 60, 120, 180, 240, 300, 360, and 420 seconds. Their run receipts identify `INCOMPLETE` runs with final completed step 23; the report limits its history response to the eight common stored timestamps and makes no completed-600-second claim.
- The C14/C18 activity comparison uses timestep indices 1–12 (20–240 seconds) for each arm. It sums the named AUT, G, and NG diagnostic proposed/applied/deferred half-L1 activity and explicitly says this is not total physical throughput or a comparison of 240-second and 460-second aggregates.
- The artifacts do not claim observation skill or mass closure. The report disclaims observational skill and causal QC-only attribution. The response JSON marks `physical_approval` as `FAIL_OPEN`, describes QC as an unweighted fixed-support mixing-ratio response, and reports no QC-weighted carrier inventory.

## Review conclusion

The same `met_em` identity is traceable from horizontal replay through vertical composition and probe. The fixed-support response and activity comparison are bounded to their recorded grids, axes, units, masks, and common times. Keep the incomplete-run and scope limits attached to any downstream summary.
