# CP06-A: real pressure-level producer with a background tendency prior

This batch connects retained observations to a nonzero spatial candidate inside
`run_cloud_bal_pipeline()`. It is an isolated pressure-level research result.
The complete CP06-A checkpoint, native initialization, and FG1 remain open.

## Fixed experiment

The case is 2026-08-16 13 UTC. The original 235 × 283 × 22 grid, pressure,
terrain, surface pressure, and boundary arrays are retained. The input hashes,
pre-candidate support snapshot, compiler, libraries, source bytes, and executable
are bound by the producer receipt. The [v1 specification](CP06_A_BACKGROUND_PRIOR_SPEC_20261012.md)
and [v2 specification](CP06_A_BACKGROUND_PRIOR_V2_SPEC_20261012.md) were declared
before their respective runs. V2 keeps the original selected center `(136,18)`.

| Support | Fixed cells | Purpose |
|---|---:|---|
| Inner 3 × 3, excluding end levels | 162 | Material retrieval |
| Warm liquid subset | 69 | Saturation/mixture-enthalpy adjustment |
| Full inner 3 × 3 columns | 180 | Geopotential reconstruction |
| Original 5 × 5 columns | 500 | Wind control |
| Original 7 × 7 columns | 980 | Validation shell |

Every OFF/HYDRO/COUPLED trial starts from the same immutable background.
The existing local radar retrieval supplies an analysis increment. Precipitation
transport is explicitly disabled in this experiment; internal phase exchange
has a separate water and represented-enthalpy budget. This liquid-equilibrium
ablation does not validate mixed-phase kinetics or a transport trajectory.

HYDRO reconstructs material, thermodynamics, and geopotential while preserving
winds. COUPLED additionally uses the canonical pressure-overlap operator:

```text
dMd_dt_prior = -B Fd(background)
dMd_dt_prior + B Fd(candidate) = 0
```

The nonzero prior is fixed by the original background; optimization iterations
are not physical time. Candidate dry fractions enter the velocity coefficients.
The metric uses the existing research prior scales of 4 m/s and 0.5 Pa/s.
These are not validated observation error covariances. Omega target and sigma
remain unchanged; neither COM nor the prior is relabeled as an observation.

The material buffer preserves composition on fixed normal-flow boundaries.
Copied interior omega boundaries are accepted only under an explicit, unchanged
background-prior contract. Ordinary physical-boundary and target-authority
checks retain their existing meaning. Failed stages roll the whole proposal back.

## Validation and interpretation

The source-bound O0/O2 pair produced byte-identical HYDRO and COUPLED files.
COUPLED converged in four outer trials and 75 final solver iterations, changing
100 material-stage cells and 476 wind-stage cells (483 overall). Rounded prior
residual RMS/max decreased from `1.01522e-7 / 7.24671e-7` to
`1.95067e-10 / 1.26725e-9 s⁻¹`. Maximum wind/omega corrections were
`0.0060188 m/s` and `0.000373244 Pa/s`. These are prior-closure diagnostics.

The [validation receipt](evidence/pr78_validation_20261012.json) records the final
Intel O0/O2 source-bound runs and their limits. Artifact data stay in external
private scratch; compact logs and hashes are retained in the repository.
Writer replay regenerates the candidate using the common producer. Python
readback checks the fixed masks, unchanged fields outside support, target/sigma,
nonzero changes, represented endpoint mass/enthalpy accounting, and the rounded
prior residual from persisted full-domain flux arrays. It does not independently
rebuild the entire pressure-overlap flux stencil.

V1's authority rejection and the intermediate mixed-source V2 rejection are
retained separately. The latter is not a frozen O0/O2 comparison: it exposed
reader pressure provenance and diagnostic wind-coverage integration defects.
The final science pair uses identical source bytes, the same V2 scientific assumptions,
the same selected window, and unchanged residual thresholds. A separately hashed
post-run shim corrected comma-separated log parsing without changing verifier
criteria. The final parser and writer-status logging fix are versioned separately
from the archived executed driver/tool; the driver fix was compile-checked in
O0/O2 without repeating the scientific computation.

The new optional geostrophic diagnostic mask describes where this producer may
change winds. It reports the existing before/after residual; it adds no acceptance
threshold. The full producer is replayed before that diagnostic is written.
The saved COUPLED geostrophic RMS increases from `6.533182855682618e-4`
to `6.792153972382788e-3 m/s²` on the fixed diagnostic footprint. Continuity
prior closure therefore does not demonstrate momentum balance or reduced
initial shock. Observation fit and physical time response are not assessed.
The ordinary standalone validator remains `INVALID / UNBOUND / REJECTED`;
it does not implement this new supported-prior/retrieval contract. Its rejection
and full failure list are retained rather than bypassed.

## Remaining checkpoint work

- Independently rebuild shared-face fluxes from stored state and geometry.
- Validate observation fit/error assumptions, phase policy, and any restored
  precipitation transport trajectory for the chosen experiment.
- Connect this candidate to WPS/metgrid/real and native Q/N/B initialization.
- Complete the same candidate's physical water/energy/dry-mass tendencies and
  BASE/HYDRO/COUPLED first-call and 10/30/60-minute comparisons.

The [controlled native evidence](CP06_A_NATIVE_CONTROLLED_20261012.md) is a
parallel task. Its rejected runs do not block this isolated pressure-level
producer and do not certify its native consumption. CP06-A is `IN_PROGRESS`;
the checkpoint gate remains `NOT_RUN`, with no operational or scientific
promotion.
