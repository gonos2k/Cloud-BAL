# Physical surface and legacy face mapping — 2026-09-21

Status: **READ_ONLY_DIAGNOSTIC / PHYSICAL_BOUNDARY_OPEN / NOT_AUTHORIZED**.
Base: PR32 merge `d3881a7271dadb22acc4f6ab42009aafd6df4b98`.
Production Fortran, D/G, RHS, masks, boundary permissions and physical increment
limits are unchanged. No BALCON/ON/native/forecast candidate is generated.

## Discrete geometry must precede the boundary substitution

`balstagger` shifts stored U/V plane `k` to the input pressure `p(k+1)`.
Stored omega plane `k<nz` averages the input values at `p(k)` and `p(k+1)`;
the top plane remains the input value at `p(nz)`. For an affine pressure profile
these donor locations are exactly the arithmetic midpoints and the finite top.
Horizontal U/V faces and omega do not share the same horizontal sampling location.
The diagnostic records stored indices, not an invented collocated surface wind.

A legacy continuity row `k` uses omega `k-1` and `k`, but divides their difference
by `dp(k)=p(k-1)-p(k)`. For uniform interior levels the donor spacing equals dp.
At the finite top of this case the spacing is 2,500 Pa and dp is 5,000 Pa.
This is a geometric limitation of the existing legacy D, separate from the
previously verified algebraic equality A=DG. It does not establish the cause of
PR25's old iteration stall, nor authorize a one-line dp replacement: changing D
requires rebuilding G/rows, weights, component compatibility and physical budgets.

The inventory uses `q=min{k:p(k)<=ps}` and records
`partial_dp=ps-omega_pressure(q)`. This pressure span to the upper donor can
exceed one nominal layer width; it is not clipped to a unit cell fraction.
It is geometry evidence, not an assertion that all q-level wind donors exist. The nearest existing omega donor is not a
material-surface value. Sentinel donors remain excluded; none is filled with zero.

## Two different column questions

For a contiguous sequence of valid legacy rows, the exact discrete identity is

```text
sum_k dp(k) D_k(y) = sum_k dp(k) div_h,k(y)
                    + omega(bottom donor) - omega(top donor).
```

This checks signed horizontal and endpoint contributions without equating an
endpoint with the physical surface. Gaps split the sequence into separate blocks.
The arithmetic check must scale with pre-cancellation terms, not the residual.
Neither support filtering nor a missing donor is allowed to disappear from the
reported coverage. Legacy dp-weighted sums have units Pa/s and are not native
mass fluxes in kg/s.

The physical fixed-top column residual instead is
`partial_t ps + div_h integral_[pt,ps](v dp) - omega_t`, with target zero.
Leibniz differentiation gives `div_h integral(v dp) = integral(div_p(v) dp)
+ v_s dot grad(ps)`; the surface-advection contribution cannot be omitted.
It includes the terrain-cut partial layer, a surface wind mapping, finite-top
omega and lateral fluxes in one declared geometry. Missing surface sampling and
boundary authority prevent calling a truncated legacy sum this physical residual.
The numeric procedures can validate an explicitly supplied column, but the real
case must retain unresolved terms until their inputs are bound.

## Influence is not permission

A unit change of an existing stored omega face contributes `-1/dp(k)` to row k
and `+1/dp(k+1)` to row k+1 when those rows exist in the audited active set.
Weighting both incident rows gives the corresponding column of `Z^T D E`.
If both rows belong to the same component their contributions cancel for this
case's analytic weights. A face inventory must record both rows, including a
missing active neighbor, rather than assign all its change to one component.
Nearest-donor incidence is a hypothetical stored-face sensitivity only. It does
not define the physical surface interpolation E_s or grant a new boundary right.
A nonzero component defect with zero mapped sensitivity cannot be corrected by
that face family alone. Changing geometry invalidates the old D/Z certificate.

## Actual execution and validation

The maintained runner `tests/run_qbal_physical_boundary_tests.sh` passed 18
checks at each pinned Intel optimization, including an affine omega input to
an exact extraction of production `balstagger`. It independently confirms the
midpoint/finite-top placement. A unit stored-omega probe of the exact
production `qbal_divergence_value` confirms row signs -1/+1 for D; the
RHS -D would have the opposite signs. Normal and gapped telescopes, exact-level and
partial surface spans, NaN rejection, explicit unavailable temporal input,
surface advection and top-flux sign are tested. The existing nonlinear/stagger
suite also passed O0/O2; its rollback controls retain their earlier scope.

`tests/diagnose_qbal_physical_boundary.py` only prepares NetCDF/snapshot inputs,
checks lineage, compiles in fresh scratch, and packages results. Numerical
mapping, pressure secants, column sums and component sensitivities are Fortran.
The actual 235×283×22 replay at Intel O0/O2 produced byte-identical outputs:

| Quantity | Result |
|---|---:|
| Existing active rows / components | 723,638 / 8 |
| All-support valid continuity rows | 1,218,907 |
| Interior columns / valid contiguous blocks | 65,988 / 65,988 |
| Columns without an active row | 2,583 |
| First active row is q+1 | 56,643 columns |
| Surface-to-upper-donor pressure span, all columns | 2,500.046875–7,499.984375 Pa |
| Top active rows using legacy 5,000 Pa denominator | 282 |
| Maximum absolute legacy dp-weighted column sum | 15.8713945293 Pa/s |
| Maximum telescope arithmetic difference | 7.1054273576e-15 Pa/s |

The last two rows are different quantities: a nonzero column sum is preserved;
the tiny arithmetic difference only verifies its signed decomposition. Independent
Python array calculations agree on geometry, coverage, incidence and column-sum
maximum; their sum order gives telescope roundoff 7.99e-15 Pa/s instead.
No synthetic algebra test is counted as a real initialization or forecast.

| Old component | Rows | Nearest-omega nonzero sensitivity faces | Partial-upper-donor nonzero sensitivity faces |
|---|---:|---:|---:|
| 0 | 722,376 | 0 | 56,552 |
| 1 | 1 | 0 | 1 |
| 2 | 1 | 0 | 1 |
| 3 | 1 | 0 | 1 |
| 4 | 1 | 0 | 1 |
| 5 | 135 | 0 | 87 |
| 6 | 670 | 0 | 0 |
| 7 | 453 | 0 | 0 |

Both hypothetical families use existing stored faces and the fixed old active
set. Every nearest-to-surface omega donor has no incident active row. The partial
upper donor is a different face: it can affect six old components, but not the
670/453-row support components. Neither family is the unknown physical E_s.
Thus even changing these partial upper donors cannot repair all eight defects.
The output retains one-based face coordinates, both incident active row IDs
(zero means outside this active set), and signed coefficients -h/+h, alongside
full mapping arrays. Internal same-component terms cancel before counting.

The actual 12/14 LSX secant reproduces -0.0140874566 to +0.0571538628 Pa/s.
The center LSX pressure is checked equal to snapshot PS, and navigation is
identical across the three LSX files. This is retrospective only; delivery time
is unknown. `physical_surface_residual` and `physical_column_residual` remain
explicit null values, because their physical endpoint mapping is not yet bound.

## Reproduction and retained evidence

The CLI accepts explicit snapshot, sparse-row and three LSX paths. For this case:

```sh
python tests/diagnose_qbal_physical_boundary.py \
  --snapshot "$SNAPSHOT" --rows "$ROWS" \
  --lsx-before "$LSX12" --lsx-center "$LSX13" --lsx-after "$LSX14" \
  --center-epoch 1786885200 --output-dir scratch/new_boundary_replay
```

The output directory must be new. The report records paths and SHA256 of all
five inputs, diagnostic sources and Intel profile, hashes prepared/results/NPZ,
checks input hashes again after execution, and refuses O0/O2 differences.
`arrays.npz` contains the full inventory and column terms; no state or candidate
is written. The raw Fortran executable consumes the validated prepared stream;
its direct invocation is not an independent general-purpose input validator.

Retained execution: `scratch/pr33_validation/actual_final/` in the isolated
`study/physical-boundary-map-20260921` worktree. Input snapshot SHA256:
`96932e53e5f30bf3e9c307617765aaa7200750ec01d4ead6b45842faf97fa661`;
sparse rows SHA256:
`dceb0827dc26bd09510568a9ae1bfe6889c1d09a9a809d738559ac37a278b335`.
The three LSX hashes are unchanged from the [PR32 input record](LEGACY_PHYSICAL_BOUNDARY_POLICY_20260921.md).
The production qbalpe source remains SHA256
`63a8fd2e1f7a0025e02efa91d77bfe576452c83810f7ba676ee936dc97b60e17`.

## What must change before a physical candidate

The next operator design must represent the physical partial bottom and finite
upper interval together, bind the surface wind sampling/rotation and time
contract, and account for lateral fluxes. Any new D must be paired with G and
re-certified weights/components. The two tested stored-face families cannot reach the
two isolated support components identified above; the physical E_s remains
unbound, and their support/receiver policy
still needs independent physical justification. No covariance, receiver
allowance or mass source is inferred from these diagnostic magnitudes.

