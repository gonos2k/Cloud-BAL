# Strong-precipitation QSNOW sensitivity extension

The extension evaluates eight additional six-hour forecasts: native initial QSNOW
multipliers 1.75, 2, 2.5 and 3 in both the control and improved families. It reuses
the 14 sealed family experiments from the earlier sensitivity sweep. Existing
HYDRO is a contextual case, giving 23 scored cases and 22 eligible candidates.

The user changed the selection objective from an across-threshold mean to a
single experiment prioritizing strong-precipitation CSI. The
[selection plan](selection_plan.json) was frozen before the eight new forecasts,
but after the earlier 14 results were known. The old plan and all its results
remain unchanged. Selection uses +1-hour CSI at 10 mm, then CSI at 5 mm; FAR,
RMSE and deterministic factor/case tie-breaks follow only when earlier criteria
tie. There is no RMSE veto or averaging across thresholds or lead times.

Each score uses the preceding one-hour accumulation, 3,688 common RN1/WRF
points, and thresholds 0.1, 0.5, 1, 2.5, 5 and 10 mm. Here 10 mm per hour is a
study threshold, not a weather-warning classification. QSNOW is atmospheric
snow mixing ratio; the verification target is total surface precipitation,
not surface snowfall alone. The perturbation deliberately changes initial
water without compensating vapor, temperature or auxiliary states. This is a
same-event diagnostic parameter experiment, not a conservative initialization
or independent operational validation.

- [Paper-style report](../../SNOW_HEAVY_EXTENSION_20261030.md)
- [Runtime plan](runtime/common_plan.json) and [final runtime receipt](runtime/final_receipt.json)
- [Complete threshold-by-lead tables](../../SNOW_EXTENSION_FULL_SCORES_20261030.md)
- [All hourly/threshold scores](analysis/categorical_scores.csv)
- [Hourly precipitation errors](analysis/continuous_scores.csv)
- [All candidate ranks](analysis/selection_scores.csv) and [single selected case](analysis/selection.json)
- [Preserved paired arrays and analysis receipt](analysis/receipt.json)
- [Figures and input bindings](figures/figure_manifest.json)
- [Independent review](review/) and [validation](validation.json)

Native model files remain in the separately pinned research scratch directory.
Portable replay of tables/figures uses the committed paired arrays. Full forecast
re-execution additionally requires the recorded Intel runtime, original native
inputs and boundary files. KG snapshots are structural bookkeeping, not runtime
or scientific validation.
