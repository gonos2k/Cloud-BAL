# CP02 observed control density comparison

This comparison uses the frozen 20-column selection, the archived HYDRO capture,
and its canonical background point data. The unchanged
`tools/cp02_control_capture_analysis.py` validator checks the capture structure,
selection mapping, observed radar profiles, and captured-input/background
identity before any density statistics are produced. Its scoped result and
input hashes are embedded in `control_density_comparison.json`.

There are 141 selected levels with valid archived reflectivity and captured
density and phase-allocation operands. For each sample and for rain and snow,
the table computes `Cbg_eq = rho_d × qbg`, `Cdiag = rho_d × qdiag`, and
`Cfinal = rho_d × qfinal` using the same captured dry-air density. Group ratios
are ratios of concentration sums; zero-background ratios are recorded as null,
and those samples remain included in counts and sums. The grouped CSV contains
role/species rows and role/species/QC rows, including dBZ, temperature,
pressure, and density ranges. Each grouped species row includes only samples
whose captured phase matches that species. `sample_count` is phase matched;
`observed_control_count` also reports the full valid-observation count for the
role and, where applicable, QC group.

These archived equal-density comparisons do not reconstruct historical
density, establish causation or forecast skill, or demonstrate mass
conservation or runtime behavior.

Files:

- `control_density_comparison.json`: scope, validation result, formulas,
  limitations, grouped statistics, and SHA-256 hashes of frozen inputs and
  analysis tools and focused test.
- `control_density_samples.csv`: one row per observed selected level.
- `control_density_groups.csv`: grouped role/species and role/species/QC rows.
- `control_density_comparison.png`: matplotlib plot of role/species ratios.

Regenerate with:

```sh
python tools/cp02_control_density_comparison.py --output-dir /tmp/cp02-control-density-new
```

Use a fresh output directory; the CLI refuses to overwrite existing evidence.
