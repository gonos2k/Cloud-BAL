# Hourly precipitation report attachments

This follow-up to PR #132 presents the physics and verification of the existing
2026-08-16 12–18 UTC hindcast, with six hourly spatial comparisons. The status
cutoff is 2026-10-30. No new model integration or physics change is included.

- `report/`: Korean core report in Markdown, DOCX and PDF, plus build receipt.
  Two conceptual diagrams and six maps are embedded in the DOCX and PDF.
- `../../HOURLY_PRECIPITATION_PROGRESS_APPENDIX_20261030.md`: editable
  progress table, provenance and limitations. `progress_status.csv` provides
  the same status table in an editable CSV.
- `concepts/`: two diagrams in PNG, PDF and SVG, with their figure manifest.
- `figures/`: PNG and PDF for each lead +1 through +6 h, a combined six-page
  PDF, and the figure manifest. Panels share 3,688 paired points, extent, color
  boundaries and experiment IDs.
- `clean_export.json`, `clean_tests.txt`: four focused tests from tracked files.
  The test is registered in the Linux tier because atomic publication uses
  Linux `renameat2`.
- `reproduction.json`: the 13 map figure files reproduced byte-for-byte.
  Concept diagram output hashes are recorded separately in `concepts/figure_manifest.json`.
- `review/`, `kg/`: scoped team review and separate structural graph maintenance.

RN1 is an analysis reference; model fields are **1-h accumulated precipitation
(mm)**. Lead time is elapsed time since 2026-08-16 12 UTC; the accumulation
window is printed on every map. ORIGINAL, CURRENT_OFF, CURRENT_HYDRO and
CURRENT_LIQUID retain the definitions in PR #132. Maps show paired evaluation
points rather than a full-domain field or an observation-coverage mask.

From the repository root, with new output directories:

```sh
python tools/plot_hourly_forecast_distribution.py \
  --scores-dir docs/evidence/current_forecast_paper_20261029/scores \
  --output-dir /tmp/hourly-precipitation-figures
python tools/plot_precipitation_concept_diagrams.py \
  --scores docs/evidence/current_forecast_paper_20261029/scores/categorical_scores.csv \
  --output-dir /tmp/hourly-precipitation-concepts
python docs/build_hourly_progress_report.py /tmp/hourly-precipitation-report
python -m pytest -q tests/test_hourly_forecast_distribution.py
```

Report rendering requires Pandoc, LibreOffice, python-docx, and the NanumMyeongjo
font. Creation metadata can vary; the build receipt identifies the delivered
PDF and DOCX. Existing output directories and symlinks are refused.
