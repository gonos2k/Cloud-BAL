# CP02 same captured density comparison

This scoped audit uses the validated archived HYDRO radar-input capture and its
canonical 440-row background profile. The existing analyzer verifies raw capture
types, canonical keys, capture-to-background CSV SHA-256 identity, and visited
radar-local call records. This comparison keeps the 190 cells with valid archived
reflectivity observations.

For each observed sample, the equal-density quantities are

```text
Cdiag  = captured density_return.rho_d × REAL64 diagnostic qdiag species
Cbg_eq = the same captured density_return.rho_d × canonical qbg species
```

`qdiag` is the captured REAL64 diagnostic work-array species from
`publish_hydrometeor_candidate_post`. `qfinal` is the final captured REAL32 state
and is reported separately to expose output rounding. `qbg` is the canonical
background rain or snow mixing ratio, and the comparison verifies it equals the
captured actual-input species. The comparison also checks that the returned
dry-air density equals the density passed to phase allocation, the REAL64
allocation total exactly equals the active diagnostic species, the total rounds
to the final active REAL32 species, and the inactive rain/snow species and
graupel are zero in both diagnostic and final state.

Because both concentrations in a sample use identical positive density,
`Cdiag / Cbg_eq` equals `qdiag / qbg` per cell when `qbg` is positive. A grouped
ratio of concentration sums is density weighted, so it can differ from the
unweighted mean of those per-cell ratios. Zero-background ratios are undefined
and excluded from ratio summaries, while their background-equivalent concentrations are zero and
their samples remain counted (diagnostic concentrations need not be zero). Statistics include both the REAL64 diagnostic
concentrations and REAL32 final concentrations.

This is an equal-density counterfactual for archived samples. It does not
reconstruct historical original density or concentration, establish the old
LAPSPREP conversion equation, or validate runtime/model behavior. No model,
Fortran, forecast, or replay execution is part of this audit.

## Files

- `density_comparison.json`: scope, formulas, grouped phase/quality statistics,
  identity checks, and input/tool SHA-256 hashes.
- `density_comparison.csv`: one row per sample, including Fortran key, dBZ,
  pressure, temperature, captured density, phase, reflectivity quality, both
  background species, allocation total, final species, concentrations, and
  concentration ratios.
- `density_comparison.png`: log-scale Cbg_eq versus Cdiag scatter and grouped
  per-cell diagnostic ratio distributions.

Regenerate with:

```sh
/var/tmp/pr108_portable_env_20261026/bin/python tools/cp02_density_comparison.py \
  --output-dir /tmp/cp02_density_regenerated
```
