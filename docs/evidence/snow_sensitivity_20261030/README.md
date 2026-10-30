# Initial QSNOW sensitivity evidence

This experiment extends initial snow sensitivity to both the actual **규준 실험**
(`ORIGINAL`) and the existing improved B1 experiment (`IMPROVED_BG_FIXED`).
Each family has six new multipliers: 0, 0.25, 0.5, 0.75, 1.25, and 1.5.
The completed factor-1 forecasts are reused with their recorded input/output
identities. `CURRENT_HYDRO` is a contextual comparison, not a selection candidate.

- `selection_plan.json`: ranking and guardrails fixed before candidate outputs.
- `runtime/`: input preparation, isolated execution, completion receipts and
  input/output hashes. The failed pre-execution `/tmp` attempt is preserved
  separately under `runtime/attempts/initial_noexec/`.
- `analysis/`: six common-point hourly NPZ files; all categorical and continuous
  scores; transitions against both controls; all 14 eligible cases and the
  selected overall/improved-family cases.
- `figures/`: dose response, hourly/threshold scores, hourly errors and paired
  precipitation maps. PNG, PDF and SVG are derived from the sealed arrays.
- `build_report.py`: generates the scientific report from sealed score tables.
- `review/`, `validation/`: team review and independent replay records.
- `kg/`: scoped structural extraction, limitations, separately dated snapshots
  and preservation of previous graph evidence.

The intervention changes only native `QSNOW`, using double-precision
multiplication followed by a native single-precision cast. The other 207
variables and metadata remain unchanged. It intentionally changes initial water
without compensating vapor, temperature or auxiliary fields; it is a diagnostic
ablation, not a conservative initialization policy.

Scores verify **total ground precipitation for each preceding one-hour window**,
not snowfall alone or the 0-to-lead accumulated precipitation. Selection and
evaluation use the same weather event, so the selected case is not independently
validated and is not an operational recommendation. The frozen rule can retain
B1 when no sensitivity setting improves its rank while meeting all four guards.

Runtime records distinguish successful six-hour completion from the initial
launch failure. Structural graph freshness does not establish forecast skill,
physical conservation, or runtime validity.
