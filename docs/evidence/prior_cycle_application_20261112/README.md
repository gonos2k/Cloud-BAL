# Actual prior-cycle application evidence

The 2026-08-16 06→12 UTC CONTROL forecast completed. The unchanged PR166 producer rejects the frozen analysis domain: **129,878 / 294,792 selected cells**, with first header `[-10,150,228,11,2]`. No proposal or new analysis input was published and no new 12 UTC analysis forecast was started. Current B1 and the 26 criteria remain unchanged. See the [report](../../PRIOR_CYCLE_APPLICATION_20261112.md).

| Directory | Scope |
|---|---|
| `frozen_application` | Rule/mask/policy frozen before inspecting the prior output |
| `native` | Actual REAL and eight-rank forecast receipts, configuration, logs, hashes; metadata correction explicitly retained |
| `production_attempt` | Actual public producer invocation manifest and rejection; no proposal file |
| `coverage` | Exact actual-data auditor, full compressed numeric input stream, diagnostic arrays, compiler build evidence |
| `validation` | Portable fresh external pinned-Intel replay and receipt: replay PASS, application REJECTED |
| `science` | Independent lineage and actual-data recount; overlapping observations are not exclusive causal contributions |
| `figures` | Reproducible plots with input/output hashes |
| `kg` | Bounded structural graph maintenance; no implication of scientific or runtime validation |

The raw background NetCDF and executables remain outside Git; original paths and hashes are retained. `coverage/fixed.bin.gz` reproduces every input to the common initialization kernel, not WRF itself. `diagnostic_only.npz` is not a model input; success-only parity is diagnostic, never an applied mask. File-derived context is not the new initialization's native first-use state.

Run from a repository checkout:

```bash
python3 docs/evidence/prior_cycle_application_20261112/validation/replay.py \
  --repo-root "$PWD" --work-root /absolute/fresh/scratch/prior-replay
python3 docs/evidence/prior_cycle_application_20261112/figures/plot.py \
  --out /absolute/scratch/prior-figures
```

Replay uses the pinned Intel profile and requires an initially nonexistent working directory outside the source tree. The actual-data run is O0; prior synthetic O0/O2 evidence remains separate. The large original NetCDF extraction and forecast are not reproduced by this small replay. A prior cycle is not an independent weather event; historical archive provenance has explicit limits in the lineage notes.
