# Retained actual-data recount

`recount.py` reads the retained diagnostic NPZ and frozen policy supplied as arguments, emits `recount.json` and `representative_cells.csv`, and performs no policy, mask, prior or production change. Inputs are the same byte identities as the PR167 public diagnostic (`6eb1f566…`) and frozen policy (`647126e5…`). The counts concern the previously frozen selected cells; observations are not exclusive causal assignments.

For the computed cap observation, the script reproduces the existing audit order: REAL64 fraction times target, round QI to REAL32, divide by REAL64 background mean, round NI to REAL32, then multiply by REAL32 analysis density proxy. Background-density substitution holds that proposed NI fixed; it does not identify a causal mechanism or perform a forecast. Density is the file-derived `1/(AL+ALB)` proxy, not new first-use density.

The 20,332-cell feasibility group excludes the 41 cap-flagged cells whose background mean already violates policy. For fixed stored REAL32 QI and analysis density, a continuous REAL64 mean satisfying the frozen mean range and number cap exists if `max(lower, QI*density/cap) <= upper`. Eight fail that inequality. This is neither a claim that an altered mean is physically justified nor an exact search of discrete REAL32 outputs or a native replay.

From the repository workspace, for example:

```sh
python scratch/ice_history_boundary_20261113/science/recount.py \
  --diagnostic scratch/actual_prior_first_use_20261112/coverage/actual_12utc/diagnostic_only.npz \
  --policy scratch/actual_prior_first_use_20261112/fixed_application/policy.json \
  --out /absolute/scratch/recount-output
```
