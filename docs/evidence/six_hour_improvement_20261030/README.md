# Six-hour extension of the first-hour improvement

This evidence extends PR135's combined B1 candidate to 2026-08-16 18 UTC.
There is one new six-hour forecast, `IMPROVED_BG_FIXED`. The original OFF and
current HYDRO controls are reused from the sealed PR132 six-hour arrays.
The executable, producer input and boundary match the one-hour B1 experiment;
only the integration/output ending times change. No native rebuild is made.

Each lead +1 through +6 scores the preceding **one-hour accumulation** on the
same 3,688 paired RN1 points, at thresholds 0.1, 0.5, 1, 2.5, 5 and 10 mm.
The sixth lead is 17–18 UTC, not the six-hour total. The report keeps this
combined intervention distinct from the PR135 first-hour factorial design.

- [Time/threshold report and all metric tables](../../SIX_HOUR_IMPROVEMENT_20261030.md)
- [Categorical scores: 108 rows](analysis/categorical_scores.csv)
- [Continuous scores: 18 rows](analysis/continuous_scores.csv)
- [Paired transitions: 72 rows](analysis/transitions.csv)
- [Analysis provenance](analysis/receipt.json)
- [Actual runtime and first-hour prefix check](runtime/README.md)
- [Figures](figures/figure_manifest.json)

## Replay from archived artifacts

From the repository root, the figures need only the sealed local analysis
bundle; external model histories are not required:

```bash
python tools/plot_six_hour_improvement.py \
  --analysis-dir docs/evidence/six_hour_improvement_20261030/analysis \
  --output-dir /var/tmp/six-hour-improvement-figure-replay
```

`build_report.py` renders the Korean report from the sealed CSV rows. It refuses
to overwrite an existing report; run it in an isolated checkout/export with
that generated Markdown omitted. The analysis CLI itself requires the raw
research-host history and RN1 inputs identified in its receipt. Its full
invocation is retained with the validation evidence.

## Interpretation

These are one-event forecasts, not independent samples across 3,688 storms or
36 hour/threshold combinations. Source timing/coverage of the processed RN1
analysis remains uncertain. Background preservation changes eight native
initialization fields; the combined run does not identify a QR/QS-only effect
or separate six-hour policy/guard effects. Water/energy closure, process-level
flux attribution, other events, separate C2 stability and operational approval
remain outside this validation. Graph freshness is structural bookkeeping and
not runtime or scientific validation.
