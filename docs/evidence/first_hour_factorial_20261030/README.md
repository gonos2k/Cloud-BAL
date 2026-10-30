# First-hour factorial experiment and updated paper

This follows PR #134, commit `8871aeef7734d34636f44430f175d43a5b8b60ad`.
The new run completes the previously missing producer-background initialization
with the original executable. The other four forecasts are explicitly reused
from the pinned experiments; this batch does not claim five new forecasts.
All scores use the same 3,688 paired processed RN1 values for 12–13 UTC on
2026-08-16. There is no new six-hour forecast.

| Paper ID | Analysis key | Initialization | WRF executable |
|---|---|---|---|
| H0 | BASE_H | historical HYDRO | original |
| H1 | FIX_H | historical HYDRO | zero-rate guard |
| B0 | BG_BASE | producer background precipitation preserved | original |
| B1 | POLICY_BG | producer background precipitation preserved | zero-rate guard |
| O0 | BASE_ORIGINAL | actual original OFF | original |

At 5 mm, B0 CSI is 0.278810 versus H0 0.214008. The guard changes CSI to
0.204724 in H1 and 0.283582 in B1. The resulting difference of differences is
0.014055 on the CSI scale. It is not a water-mass contribution or a physical
causal percentage. The initialization intervention includes eight coupled native
fields and removes radar precipitation retrieval, transport and loading; it is
not the earlier direct QR/QS swap diagnostic.

- [Completed new run and raw/normalized receipt mapping](runtime/README.md)
- [Paired arrays and score identities](analysis/receipt.json)
- [Threshold scores](analysis/categorical_scores.csv),
  [continuous scores](analysis/continuous_scores.csv),
  [contrasts](analysis/score_contrasts.csv),
  [paired transitions](analysis/transitions.csv)
- [Figure inputs, renderer and output hashes](figures/figure_manifest.json)
- [Paper source](../../FIRST_HOUR_FACTORIAL_PAPER_20261030.md),
  [PDF](paper/FIRST_HOUR_FACTORIAL_PAPER_20261030.pdf),
  [DOCX](paper/FIRST_HOUR_FACTORIAL_PAPER_20261030.docx)

Archived-figure replay uses only the sealed analysis arrays, tables and receipt:

```sh
python tools/plot_first_hour_factorial.py \
  --analysis-dir docs/evidence/first_hour_factorial_20261030/analysis \
  --output-dir /var/tmp/first-hour-factorial-figure-replay
```

It checks the source-record format but does not reopen original host artifacts.
Runtime/source revalidation belongs to the scorer, which requires the pinned
original inputs and histories. Plotting independently recomputes displayed
scores and rejects changed tables before publishing output. All nine PNG/PDF/SVG
assets reproduce byte-for-byte. The paper builder is
`tools/build_first_hour_factorial_paper.py`; it refuses an existing paper output
directory and publishes a complete conversion from temporary storage. A paper
rebuild therefore belongs in an isolated export with that output directory
omitted. DOCX/PDF container metadata are not claimed to be byte-reproducible.

The single-case and first-hour limits remain. RN1 upstream timing and coverage,
process attribution, full water/energy budgets and operational acceptance are
open. The three existing current graph files in the PR #134 manifest are checked
through their exact dated snapshot when the new structural graph advances;
[the prior-evidence audit](validation/prior_evidence.json) records this mapping.
