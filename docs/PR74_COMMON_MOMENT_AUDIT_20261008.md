# PR74 common Q/N/B moment audit

This audit reuses the retained PR73 `KDM6TRC1` parser and the existing PR63
geometry parser. It checks the four paired states consumed by the common KDM6
preflight: rain Q/NR, cloud Q/NC, ice Q/NI, and graupel Q/BG. It scans the full
active `(j,k,i)` input capture, then derives the first rejection in native
iteration order: `j`, `k`, `i`, followed by rain, cloud, ice, graupel.

The retained native line is reproduced exactly: ice is mass-only at Fortran
trace indices `(i=133,j=2,k=1)`, with `q=3.5308575789291633e-35 kg kg-1` and
zero moment. The recorded latitude is the KDM62D call index; geographic
latitude and global-j mapping are unclaimed.
That first value is tiny, while the global audit also finds **423,771 ice
mass-only cells** and a maximum mass-only ice value of `8.467670530080795e-3
kg kg-1` at `(197,71,24)`. Across all species, counts are 23,494 negative,
751,350 mass-only, 492 moment-only, and zero nonfinite cells. These issue
counts are independent predicates; the negative count is also the invalid
union count for this capture.

| Species | Negative | Nonfinite | Mass-only | Moment-only | Largest mass-only Q (kg/kg) | Absolute Q × dry-air mass on mass-only cells (kg) |
|---|---:|---:|---:|---:|---:|---:|
| Rain | 0 | 0 | 35 | 3 | 8.6490e-11 | 2.2202 |
| Cloud | 23,494 | 0 | 327,544 | 8 | 1.1335e-6 | 321,358.6 |
| Ice | 0 | 0 | 423,771 | 481 | 8.4677e-3 | 1,728,749,415.6 |
| Graupel | 0 | 0 | 0 | 0 | — | 0 |

`NC`, `NR`, and `NI` in the public trace are specific number per kilogram of
dry air. The audit reproduces the retained source conversion
`N_internal = N_public * rho_d`, where `rho_d = DEN / (1 + Q)`, and reports
both bases. `BG` remains specific volume (`m3 kg-1`); it is not interpreted as
number concentration. Pair admission uses exact zero equivalence: absent means
both values are exactly zero, active means both are positive. No tolerance
turns positive mass into absent mass.

The mass scale uses same-call hybrid dry-air weights from the retained
`PRE_MICROPHYSICS` geometry record:
`dry_mass = dp * DX * DY / (MSFTX * MSFTY * g)`. The captured geometry, timestep,
active bounds, and instrumented source hash match the PR73 receipt. The run
ended at controlled initial rejection, so only the pre-call geometry record
exists; no post-call geometry comparison or completed-step budget is claimed.
The weighted values are diagnostic scale measures, not closed hydrometeor
budgets or physics validation.

The run is a retained partialhost research execution. It does not establish a
clean full-physics host build, production-source equivalence, producer
correctness, water or energy closure, or a completed native timestep. The
same-call weighted scale does not validate the native physics.

Machine-readable details and artifact hashes are in
[`receipt.json`](evidence/pr74_common_moment_audit_20261008/receipt.json).
