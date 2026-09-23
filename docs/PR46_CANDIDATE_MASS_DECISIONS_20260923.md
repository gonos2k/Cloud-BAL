# PR46: cloud-force output and candidate mass decisions

Base: merged PR #45, `ea5fa10321faf6a3945b2c7532be61133f84ead6`.
This change fixes a diagnostic output contract and records the decisions still
needed for a physical candidate. It does not change the analyzed state or run
the balance solver.

## Supported-level output

The cloud-force CLI accepts `--triangle`. Its final JSON summary now reports
`100000_Pa_acceleration_en_m_s2: null` when that pressure level is unsupported;
the saved upper-level report remains valid. A triangle with no supported
levels is rejected before writing a result. An actual13 rerun on triangle 397
completed with 19 supported levels, including 90000 Pa but not 100000 Pa.
The default triangle 75,455 still has 20 levels, and its numerical level rows
and vapor-column result are identical to PR #45. The compact
[receipt](evidence/pr46_cloud_force_summary.json) records both runs and hashes.
The vapor-column summary always refers to the fixed node `(55,162)`, regardless
of `--triangle`; the selected triangle controls the force summary.

## Present state roles

The two existing diagnostics have different domains and must remain separate:

| Scope | Fixed reference for attribution | Established quantity | Missing condition |
|---|---|---|---|
| 98 ground-supported triangles | Retained HT and the PR43 stage/final T/q inputs | Conditional `-grad S`, `-grad D`, `-grad F` on 1,959 triangle-levels | Accepted physical datum and complete lower transport; triangle 75,455 is outside this support |
| Triangle 75,455 | Retained final LT1 temperature and common pressure levels | LQ3 cloud ON–OFF relative force with a 5000 Pa zero gauge | Ground reference, surface partial layer, full column and independent moisture authority |

For these read-only comparisons, retained final T and original HT/winds are
unchanged. Ground attribution uses its fixed stage/final T/q inputs; only the
controlled cloud ON/OFF comparison varies q. Cloud OFF is a producer
counterfactual, not a candidate initialization. No T/q, HT, wind or boundary increment is selected
by the size of either force. Making T/q adjustable would require separately
supported errors and correlations, a mass and energy convention, and limits
on the saved increments.

## Mass convention that a candidate must choose

PR #45's cloud result uses LQ3 specific humidity `q` (kg vapor per kg dry air
plus vapor), fixed total gas-pressure endpoints, and omits condensate mass.
In that diagnostic convention, for an area-normalized regular pressure column,

```text
M_gas = (p_bottom - p_top)/g0
M_v   = integral(q dp)/g0
M_d   = M_gas - M_v
```

The 19 supported 100000–5000 Pa layers at node `(55,162)` give
`delta M_v = +9.802161313 kg/m²`. If the same pressure-cell total mass is held
fixed, this composition-only comparison has
`delta M_d = -9.802161313 kg/m²`. It is **not** a dry-mass-conserving native
moisture addition. The surface partial layer, condensate loading, boundary
transport, precipitation and energy response are absent. A candidate that
instead keeps native dry mass fixed must specify its pressure/EOS and water
response; preserving `MU+MUB` alone does not construct that state. The
[native mass-frame contract](NATIVE_MASS_FRAME_CONTRACT.md) keeps those bases
separate.

## Conditions before a joint candidate

The [readiness record](PHYSICAL_CANDIDATE_READINESS_20260922.md) remains the
gate: an accepted scalar reference `b(x,y)` and connected hydrostatic path,
physical lower wind/0–10 m transport, the role of derived LW3 top omega,
matching time and face geometry, and independently supported errors and
increment limits. The missing flux must not be set to close the present
subtotal. A joint pressure-grid candidate and its native dry-mass, face-flux,
thermodynamic and startup checks therefore remain `NOT_AUTHORIZED`.
