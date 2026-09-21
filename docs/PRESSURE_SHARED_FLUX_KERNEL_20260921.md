# Partial-layer and finite-top pressure flux research kernel

Status: **RESEARCH_KERNEL / GEOMETRY_ONLY**, following PR33 at
`b5bee8f08ea71e46c271128a26b069a1f843705e`. No production caller, solver,
RHS, support mask, boundary permission, or acceptance threshold changes.
The last-interval `surface_layer` defect is corrected separately: its search
includes the final pressure level, while `p(n) < PS <= p(1)` remains the domain.

## Equation and implementation

`tests/qbal_pressure_flux.f90` contains four small Fortran procedures:

1. `pressure_interfaces` constructs `[PS, p_omega(q), ..., p_omega(n)]`,
   with the original first above-ground level `q` and finite top `p(n)`.
   Consecutive interface differences define new control-volume thicknesses.
   These are not the old legacy rows with a changed denominator.
2. `integrate_pressure_profile` integrates a declared piecewise-linear profile
   between specified pressure endpoints. It reproduces affine profiles exactly
   in exact arithmetic, including cut intervals; it rejects extrapolation.
   Valid physical samples, wind frame, and location are caller requirements.
   In particular, stored legacy U/V plane k is at p(k+1): it must not be
   paired with the original p(k) array. Partial-bottom transport requires
   explicitly mapped surface samples rather than extrapolated sentinel values.
3. `flux_divergence` applies `D = V^-1 B` to **integrated face fluxes**.
   Each stored face contributes once with opposite signs to its two cells;
   index zero denotes the exterior. `V = horizontal area * pressure thickness`
   has units m2 Pa; face flux has units m2 Pa/s, and D has units s^-1.
4. `multiplier_flux` applies `G = -K B^T`. With cell inner product V and
   Euclidean face inner product this is the negative mobility-weighted adjoint.
   `A = D G` is evaluated by composition, with no independently assembled row.
   `x^T V A x = -(B^T x)^T K (B^T x) <= 0` for nonnegative K.

Zero mobility freezes a correction face. Exterior multiplier zero describes
only an explicitly adjustable boundary; every unapproved boundary must have
K=0. This kernel neither grants permission nor computes an accepted candidate.
Its arithmetic envelopes reject extreme inputs before overflow; those bounds
are not scientific increment tolerances or calibrated covariances.

The existing `cloud_bal_grid_geometry:partition_pressure_face` provides shared
horizontal pressure segments. No second overlap algorithm or new solver is
introduced. The canonical `configure_pressure_geometry` cannot simply replace
this experiment: it extrapolates the top by half a level spacing, whereas this
experiment retains the actual finite endpoint `p(n)`. Neither canonical nor
legacy production geometry is changed.

For a sloping material surface the lower normal flux is
`area * (omega_s - v_s . grad(PS)) = area * PS_t`, not `area * omega_s`.
The lateral flux must integrate the complete pressure span to that surface.
Then the pressure-volume sum is
`PS_t + div_horizontal(integral(v dp)) - omega_top`.
Adding surface advection a second time would break this identity.

## Actual NE57 geometry replay

Command from the repository root (use a new output directory):

```sh
python tests/diagnose_qbal_pressure_flux.py \
  --snapshot /path/to/operator_snapshot.bin --output-dir scratch/pressure_geometry
```

The Python wrapper only reads, prepares input, invokes the pinned Intel
compiler, and records hashes. Numerical geometry and segment construction are
Fortran. Builds use fresh scratch directories. O0/O2 result files are identical.
The input SHA256 is
`96932e53e5f30bf3e9c307617765aaa7200750ec01d4ead6b45842faf97fa661`;
prepared geometry SHA256 is
`8d8f2ec0a2a6d6a7c80c3b634f8b8b49544953b41b1d56fde733718d1f586b7d`.

| Geometry quantity | Result |
|---|---:|
| Columns, including horizontal perimeter | 66,505 |
| New pressure control volumes | 1,294,999 |
| Adjacent horizontal column pairs | 132,492 |
| Shared pressure segments | 2,583,082 |
| Cell thickness range | 2,500 to 7,499.984375 Pa |
| Finite-top cell thickness | 2,500 Pa |
| Maximum column-span and shared-span sum errors | 0 Pa |
| Maximum nonshared side pressure interval | 5,904.28125 Pa |

An independent Python union-of-interface-knots calculation reproduced both
the cell and shared-segment counts without calling the Fortran partitioner.
These counts use all PS columns, not the 723,638 legacy active rows or their
eight components. Old component labels and `z=h*dp` are not copied to this
geometry. No horizontal area/length metric is inferred from that old z.

The nonshared side interval is important: two column-average surface pressures
do not define a continuous sloping face surface. Simply treating the exposed
strip as an impermeable vertical wall would introduce an unjustified boundary.
The replay therefore reports geometry only; **physical flux residual is null**.
It does not read or reconstruct winds, assume missing donors are zero, or claim
that a complete terrain-conforming finite-volume mesh has been built.

## Validation and remaining physical connection

`tests/run_qbal_pressure_flux_tests.sh` checks actual interface widths,
nonuniform affine omega, integrated affine horizontal terms paired with
quadratic omega, shared face cancellation, the sloping-ground column identity,
adjoint/energy/composition, frozen corrections, and invalid input rejection.
`tests/run_qbal_physical_boundary_tests.sh` retains the production-expression
probes and adds the last pressure interval regression. The new flux suite passes 30 checks per optimization level; the boundary suite passes 20. Both use pinned Intel
O0/O2 in fresh scratch directories; synthetic identities are not NE57 forecasts.
Six pinned Intel mutation runs (O0/O2 each) reject endpoint-only horizontal
integration, same-sign shared-face incidence, and a reversed adjoint sign.

Local evidence is retained in the isolated worktree under
`scratch/pr34_pressure_flux_20260921/Cloud-BAL/scratch/`: `actual_geometry_final/`
contains prepared input, generated build script, both executable outputs,
compiler log and source/input hashes; `independent_geometry.json` records the
independent counts. The original snapshot is unchanged.

Next, construct the actual **face surface and its integrated wind transport**
using independently supported horizontal metric, pressure reconstruction,
wind height/frame, and boundary time contracts. Require the represented cell
measure, shared lateral flux and ground normal term to satisfy the same column
identity. In particular, a horizontal overlap inventory alone does not resolve
the nonshared strips. Rebuild D/G and components after that geometry is fixed.
Only then bind permitted corrections and independently calibrated error ranges.
No arbitrary wall, endpoint wind as layer mean, clipping, mean RHS removal or
source fitted to the old obstruction is authorized.

The previously demonstrated legacy operator, face gate, NaN and receiver
diagnostic closures remain scoped. Nonzero ON, native consumed-state mass,
thermodynamics, startup response and forecast validation remain OPEN.
