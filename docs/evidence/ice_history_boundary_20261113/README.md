# Ice history boundary evidence

This batch separates the host storage boundary from the initialization acceptance policy. The [report](../../ICE_HISTORY_BOUNDARY_20261113.md) records the final observations and their limits. No new analysis initial condition, admission score, or independent-weather-event result is produced. Current B1 and the 26 criteria remain unchanged.

| Directory | Evidence |
|---|---|
| `source_audit` | Actual executable/archive identities, disassembly, two small retained text sections and portable comparison; source-to-object and masked-link-byte limits remain explicit |
| `science` | Recount of the existing frozen PR167 selection; alpha/density decomposition, continuous REAL64 feasibility and diagnostic cap arrays |
| `native` | Failed initial capture, short calibrated probe, unchanged-executable replay and terminal-state records; no full executable or NetCDF duplication |
| `validation` | Independent review and public-data reproduction, with runtime and offline scopes separated |
| `figures` | Descriptive plot and exact input/output hashes |
| `kg` | Bounded source graph refresh and derived wiki audit; graph freshness is not physical/runtime validation |

From the Cloud-BAL checkout:

```bash
python3 docs/evidence/ice_history_boundary_20261113/source_audit/compare_text.py \
  --receipt /absolute/fresh/scratch/zeroout-comparison.json
python3 docs/evidence/ice_history_boundary_20261113/science/recount.py \
  --diagnostic docs/evidence/prior_cycle_application_20261112/coverage/diagnostic_only.npz \
  --policy docs/evidence/prior_cycle_application_20261112/frozen_application/policy.json \
  --out /absolute/scratch/ice-boundary-recount
python3 docs/evidence/ice_history_boundary_20261113/figures/plot_constraints.py \
  --out /absolute/scratch/ice-boundary-figures
```

The numeric input is the prior PR167 dataset already retained in this repository; this batch does not duplicate it. These commands do not rerun WRF or alter any initializer. The retained executable, weather input files and full output NetCDF remain outside Git and are identified by paths and hashes. The original prior-cycle met_em/GRIB historical-lineage limits from PR167 continue to apply.

Native probe points were chosen from known outcomes to inspect a mechanism: nine cells on rank 3, including five zero-QI/positive-NI cases and four positive pairs. They are not an unbiased sample of the 44,889 stored mismatches. A positive pair is not proof of initializer acceptance. Probe v1 produced no target records and cannot support a transition claim; it is retained separately from the calibrated v2 evidence.
