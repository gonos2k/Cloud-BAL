# PR94 frozen-C4 water-budget review

Reviewed `tools/pr94_water_budget.py`, `docs/PR94_WATER_BUDGET_20261021.md`, `docs/evidence/pr94_water_budget_20261021/c4_absolute_water_budget.json`, and `tests/test_pr94_water_budget.py`. No source edits; no large runtime reread.

## Correctness checks

- Sign convention is internally consistent: `available_column_residual = vertically summed Δ atmospheric water + precipitation outflow`. A closed precipitation-only column has negative atmospheric Δ and positive outflow. Recomputed from artifact totals: OFF `-13,448,713,801.309 + 159,736,274,940.948 = 146,287,561,139.639 kg`; COUPLED `-13,352,195,793.062 + 159,638,965,602.716 = 146,286,769,809.653 kg`, matching the evidence. Residual is correctly labeled open/incomplete and not presented as a conservation closure or physical source term.
- Hybrid dry carrier is implemented as `-(C1H*(MU+MUB)+C2H)*DNW/g`, area as `DX*DY/(MAPFAC_MX*MAPFAC_MY)`, and mixing-ratio inventories multiply those native kg dry-air layer masses. This matches the existing `pr87_native_history._dry_mass` and the stated per-area units. Fields stay on complete 39×282×234 mass-grid support; no silent boundary crop. C4 OFF/COUPLED DX/DY, timestamps, and mass map factors are verified exact.
- Precipitation increments telescope `RAINC+RAINNC` from the 0-s baseline, validate mm units, and convert mm to kg m-2 before the same cell area. RAINSH is not added; SNOWNC/GRAUPELNC/HAILNC are correctly treated as phase subsets of total grid-scale precipitation, avoiding double counting. Six water mass mixing ratios are included; QIB and number moments are correctly excluded as non-water-mass diagnostics.
- Surface exchange, boundary water flux, relaxation/nudging, incomplete non-microphysics sources, numerical transport/diffusion/roundoff, and phase boundary attribution are all explicitly marked missing. Report also correctly notes the FDDA block is empty and specified lateral boundary exchange is active. No unsupported H(X)-y or per-call closure is claimed.

## Remaining claim limits

No correctness blocker found in the examined accounting. Existing tests exercise residual sign, 3-D/2-D shape rejection, and cell/column L1 distinctions, but do not independently pin the dry hybrid mass formula, mm precipitation conversion, or exclusion of phase subsets. Those are test-coverage opportunities; the source implementation and saved evidence are internally consistent on inspection. Per-call geometry only exists at timestep 3, so the report appropriately leaves same-call water-plus-precipitation residual uncomputed.
