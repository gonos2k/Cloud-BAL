# Reconstructed sloping pressure faces and covered wind transport

Status: **RECONSTRUCTED_GEOMETRY / CONDITIONAL_COVERED_TRANSPORT**.
Base: PR34 merge `8c90696420868b293aed22d2e7a33587443fe670`.
No production solver, RHS, support, boundary permission or increment gate changes.
This step builds actual face metrics rather than prescribing a manufactured
set of face fluxes and merely checking their global sum.

## Declared geometry and metric

The static NE57 latitude/longitude samples define a spherical equal-area chart:

```
x = R cos(phi0) (lambda-lambda0)
y = R (sin(phi)-sin(phi0)) / cos(phi0)
dx dy = R^2 cos(phi) d(lambda) d(phi)
U = cos(phi0)/cos(phi) * u_east
V = cos(phi)/cos(phi0) * v_north
```

Here R=6371200 m, matching `klaps-v5.0_/src/include/constants.inc`, and
phi0=38 degrees, lambda0=126 degrees select the chart origin. U/V are coordinate
rates, not unrotated grid winds. Lambert grid winds are first rotated to local
east/north using the source convention, then scaled. A displacement test checks
the chart rates independently. This chart is equal-area, not conformal.
The actual domain stays away from the longitude seam and poles; those cases
are outside this replay. Local legacy `dx=dy=5000/map_factor` is not used as
an area array or a replacement for the face geometry.

Each adjacent four-node patch is checked for convexity and split along the same
southwest–northeast diagonal. PS is affine on each triangle. The upper surface
is the fixed finite pressure 5000 Pa. All surface vertices exceed this top.
This produces **full triangular columns**, not the vertically layered cells
of PR34 and not a remapping of legacy staggered values. The domain is the hull
between the existing grid-point rows/columns; no unobserved outer half-cell
band is added. Straight chart edges and affine PS are explicit reconstruction
choices, not a claim of exact terrain shape between samples.

For a horizontal triangle of area A, the pressure volume is
`V = A * (mean(PS_vertices)-p_top)` in m2 Pa, not m3 or native dry mass.
The five faces are the sloping ground, finite top, and three vertical sides.
Triangulating each planar face computes its integrated oriented metric M and
first moment Q. Positions in Q are relative to the cell's first horizontal
vertex and p_top, to avoid cancellation from a distant origin.

```
M_f = integral(outward metric)        Q_ab,f = integral(position_a metric_b)
sum_f M_f = 0                       sum_f Q_ab,f = V delta_ab
```

Thus constant chart fields have zero divergence and an affine chart field
`c + J position` has integrated divergence `V trace(J)`. These are **per-cell**
checks, stronger than global cancellation of duplicated face fluxes. They do
not certify exactness for arbitrary physical wind profiles on a sphere.
Ground metric includes `A[-PS_x,-PS_y,1]`; its flux is
`A(omega_s-U_s PS_x-V_s PS_y)`, not raw surface omega.

## Actual profiles and what is not filled

The replay reads the original pressure-level LW3 U3/V3 before legacy staggering.
It reverses ascending hPa levels to descending Pa and checks them against the
pinned snapshot. LSX PS is exactly the snapshot PS. Static, LSX and LW3
navigation agree; both analysis files have valid time 2026-08-16 13 UTC.
The misleading `Dx/Dy` metadata units are not used to infer face length.

The producer include sets `l_grid_north`, `l_grid_north_anal` and
`l_grid_north_out` true. Source rotation routines imply
`theta=n*(longitude-126 degrees)`,
`u_east=cos(theta)*u_grid+sin(theta)*v_grid`,
`v_north=-sin(theta)*u_grid+cos(theta)*v_grid`, with Lambert parallels 30/60.
The replay requires and hashes that source contract. **This is conditional
transport:** LW3 lacks an explicit frame attribute, writer commentary is not
fully consistent, and the historical producing executable/include identity was
not revalidated here. Source configuration evidence is not new production
boundary authority. The separate LSX 10-m wind is not substituted for a
material-surface or pressure-level sample.

On each unique edge, the two node profiles are interpolated linearly along the
edge and piecewise linearly in pressure. The surface pressure varies linearly
along that same edge. Two-point Gauss integration between crossings of profile
knots is exact for the resulting piecewise cubic integrated polynomial, up to
arithmetic rounding. For each metric/moment entry the arithmetic scale uses
its own uncancelled terms (and its same-unit exact diagonal moment), not a
volume floor for quantities with different units. `edge_wind_flux` reuses PR34's pressure-profile integral.
The same edge flux is stored once and consumed with opposite signs by its cells.

For actual data only levels above ground at **both** endpoints are used.
If those samples stop below the requested PS endpoint in pressure coverage,
the routine returns the covered integral and a separate missing pressure-span
integral along the unit edge parameter. `ok` means that partial calculation is
valid; it does not mean full coverage. The missing-span number is neither a
flux error estimate nor permission to set omitted wind to zero. Surface/top
omega and causal PS tendency are not supplied. Consequently, the complete
physical continuity residual stays **null**.

## Same-case execution

The focused suite passes 19 checks at each pinned Intel O0/O2 level.
Pinned Intel O0/O2 fresh-scratch builds both pass the cell metric and moment
checks. They are **not bitwise identical**: maximum edge-flux difference is
`9.5367431640625e-7 m2 Pa/s`. Comparison uses a per-edge arithmetic scale from
uncancelled metric, pressure span and wind magnitude, including summation depth;
this does not relax any physical residual tolerance. Both output hashes remain
in the report.

| Quantity | Result |
|---|---:|
| Full triangular columns | 131,976 |
| Unique side edges | 198,480 |
| Internal / external edges | 197,448 / 1,032 |
| Edges with an uncovered near-surface strip | 198,480 |
| Maximum normalized constant-metric closure error | 2.21947e-16 |
| Maximum normalized affine-moment closure error | 3.06610e-16 |
| Maximum missing pressure-span integral | 7,827.05078125 Pa |
| Maximum covered side flux magnitude | 6.96224e9 m2 Pa/s |
| Maximum partial lateral transport per horizontal area | 27.3736954 Pa/s |

The last row is **only the covered lateral contribution**, not a complete
column continuity residual. Missing pressure span can exceed one regular level
because a shared edge samples a varying PS while both profiles must be valid.
All internal edges have exactly two opposite incidences. An independent
closed-form pressure primitive reproduces actual covered edge fluxes within
`3.81470e-6 m2 Pa/s` arithmetic difference, missing spans within `1.46e-11 Pa`,
and all triangular volumes exactly in the inspected stored arithmetic.

## Reproduction, evidence and next connection

```
bash tests/run_qbal_sloping_geometry_tests.sh
python tests/diagnose_qbal_sloping_faces.py \
  --snapshot /path/operator_snapshot.bin --static /path/static.nest7grid \
  --lsx /path/262281300.lsx --lw3 /path/262281300.lw3 \
  --frame-evidence /path/main_sub.inc --radius-m 6371200 \
  --epoch 1786885200 --output-dir scratch/sloping_actual
```

The wrapper handles I/O and topology; geometry, wind conversion and numerical
integration run in Fortran. Local evidence is retained under the isolated
`scratch/pr35_sloping_faces_20260921/Cloud-BAL/scratch/pr35_validation/`:
`actual_final4/` has prepared input, executable outputs, arrays, source/input
hashes and compiler logs; `inputs/` retains LW3 and source contracts;
`independent_transport.py/json` contains the separate reference calculation.
Snapshot SHA256 is `96932e53e5f30bf3e9c307617765aaa7200750ec01d4ead6b45842faf97fa661`;
LW3 SHA256 is `71be1da633915ed058378e18cb7d31851fbe860b135c6bf47cda738232086065`.

Next bind the frame/producer contract and near-surface velocity representation,
then surface pressure tendency and finite-top omega on this same reconstructed
surface. Keep the ground normal and complete lateral transport in one column
budget. Subdividing these columns vertically must preserve shared faces and
moments; no production layered mesh is claimed here. Only after complete
physical fluxes are defined should compatibility, mobility/covariance and
velocity-space increment limits be connected. A flux correction is not an
accepted U/V/omega correction; a weighted-adjoint identity is not atmospheric
energy conservation. No solver, nonzero ON candidate, native startup,
thermodynamic or forecast success is claimed.

Final validation also compares every cell side against its signed unique-edge metric. Its arithmetic scale includes coordinate operands before subtraction, preventing almost axis-aligned edges from producing a false rejection. The 128-epsilon factor is unchanged; this is not a physical residual tolerance. Eight ground-orientation, moment, chart-scale and omitted-strip mutations were rejected across pinned Intel O0/O2.
