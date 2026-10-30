# Fresh six-hour forecast comparison

This package evaluates fresh 2026-08-16 12–18 UTC hindcasts with current
Cloud-BAL initialization (`a63a8029fc134e1bab77f0a96757e3b369b8e93d`) and the
same archived CP02 WRF host. It does not certify the latest C2 WRF integration.
See `runtime/README.md` for the distinct ORIGINAL and CURRENT_OFF preparation
lineages, source/runtime pins, failed OFF wrapper attempt and valid rerun.

## Reproduction layers

1. **Native forecast:** the scripts and receipts in `runtime/` identify the
   Intel build, private input copies, preprocessing, model launches and output
   hashes. These commands require the external research-host archive. Large
   NetCDF inputs and histories are retained externally, not embedded in Git.
2. **Scoring:** `score_forecasts.py` reads seven hourly histories per arm and
   six pinned RN1 files. It reuses the archived spatial observation operator,
   checks reset/grid/time contracts, and requires the same 3,688 paired points
   each hour. `ORIGINAL` is the primary baseline; `CURRENT_OFF` is an additional
   matched preparation baseline for CURRENT_HYDRO and CURRENT_LIQUID.
3. **Portable result checking:** `verify_scores_independently.py` recounts the
   committed paired arrays using separate scalar calculations. This checks
   reported arithmetic, not the independently unavailable raw observation
   production chain or model integration.
4. **Figures and paper:** `plot_forecast_scores.py` consumes the paired score
   tables/arrays. `docs/build_current_forecast_paper.py` renders the manuscript
   to DOCX and PDF using Pandoc and LibreOffice. It records source/output hashes
   and checks equations and Korean text.

The final manuscript embeds `figures_publication/`. The earlier wide-panel
figures remain in `figures/`; their exact generating script is preserved and
reconciled in `prior_versions/`. Score inputs are unchanged between layouts.
The exact native scoring command and exit status are recorded in
`validation/fresh_scoring_run.json`; `validation/forecast_score_binding.json`
connects all 28 scored histories to the completed cohort.

From the repository root, with new output directories:

```sh
python docs/evidence/current_forecast_paper_20261029/verify_scores_independently.py \
  docs/evidence/current_forecast_paper_20261029/scores /tmp/independent_scores.json
python docs/evidence/current_forecast_paper_20261029/plot_forecast_scores.py \
  --scores-dir docs/evidence/current_forecast_paper_20261029/scores \
  --output-dir /tmp/current_forecast_figures
python -m pytest -q tests/test_current_forecast_scores.py \
  tests/test_hourly_precip_scores.py tests/test_precipitation_transitions.py
python docs/build_current_forecast_paper.py /tmp/current_forecast_paper \
  --require-figures
```

DOCX/PDF creation metadata can vary between renderings; their individual
build receipt identifies the delivered documents. PNGs and numerical score
tables can be compared separately from document metadata.

The observation is a processed RN1 analysis: the exact canonical files are
pinned, but their upstream freshness and coverage/QC are not fully resolved.
Its 1 km-input 5×5 maximum operation and the model's 5 km-grid bilinear sampling
are different spatial supports. No claim of independent samples, multi-case
skill, closed water/energy budgets or a single-process causal effect follows
from this comparison. Historical capture results remain contextual evidence;
the fresh forecasts and their scores are identified separately.
