# Fine-factor QSNOW sensitivity experiment

Eight additional experiments apply initial QSNOW factors 1.1, 1.2, 1.3 and 1.4
to both the control and improved families. The existing 22 eligible experiments and
contextual HYDRO experiment are preserved; completed fine experiments bring the comparison
to 31 experiments and 30 eligible candidates. Each forecast runs from 2026-08-16
12 UTC to 18 UTC, using the family's pinned executable and unchanged boundary.

Only initial native QSNOW is changed: double-precision multiplication followed
by native REAL32 storage. Other 207 variables and metadata are unchanged.
This is a same-event diagnostic initial-water perturbation, not a balanced or
conservative initialization or an independent operational validation.

The selection plan is frozen before new forecasts, with the earlier results
already known. Selection prioritizes +1-hour CSI at 10 mm, then CSI at 5 mm,
FAR at 10 mm, RMSE, factor distance from one and case ID, lexicographically.
There is no average across thresholds, hours or experiments. Total surface
precipitation is verified, not snow precipitation alone. Each lead denotes the
preceding one-hour accumulation at 3,688 common points.

- [Frozen selection plan](selection_plan.json)
- [Runtime plan](runtime/common_plan.json) and [completed runtime receipt](runtime/final_receipt.json)
- [Full score appendix](../../SNOW_FINE_FULL_SCORES_20261030.md)
- [Report](../../SNOW_FINE_SENSITIVITY_20261030.md)
- [All experiment figures](../../SNOW_FINE_FIGURES_20261030.md)
- [Improved-family figures only](../../SNOW_FINE_IMPROVED_FIGURES_20261030.md)
- [Categorical score CSV](analysis/categorical_scores.csv)
- [Continuous score CSV](analysis/continuous_scores.csv)
- [Single selection](analysis/selection.json)
- [Analysis receipt](analysis/receipt.json)
- [Independent review](review/)
- [Validation manifest](validation.json)

Native histories remain in the separately pinned research scratch directory.
Committed paired arrays support portable score/figure replay; rerunning WRF
requires the original native inputs, boundary and pinned Intel runtime. The
structural graph and dated wiki mirrors do not establish forecast validity.
