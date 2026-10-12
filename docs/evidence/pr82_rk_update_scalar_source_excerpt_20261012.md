# `rk_update_scalar` source contract excerpt

Read-only source linkage for the PR82 native stage trace. Hashes identify the source text inspected; the patched solve source below differs only by the temporary scalar boundary observer described separately.

| Source | SHA-256 |
|---|---|
| `KIM_RDPS_MODL_V2026.2/dyn_em/module_em.F` | `7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7` |
| PR64 `solve_em_pr64_qc_channel.f90` | `72aa50d495fa13d58029189f643fba218c819f8d0911c5138997124d6e99459b` |
| staged observer patch | `8a365b69931e15bb24e7b96ae0661a16c7aa036113750319dc68e83c48b908f1` |

The observer build compiled `solve_em_pr64_qc_channel.f90` at SHA-256 `25d0614215a22ffc892789dc41e18e21c114d0bf206cb99fe0da0c2e7923f8d0` and its object at `24fc08c28dd13f1d5ae8930aa00426aaa06c3e541882a0cc3c82ca66ec1499d6`.

## Call site and field bindings

At `solve_em_pr64_qc_channel.f90:3179–3196`, `CALL rk_update_scalar` is invoked from the scalar-variable loop. The caller binds `scs=sce=is`; `scalar_1=scalar_old(…,is)`; `scalar_2=scalar(…,is)`; `sc_tend=scalar_tend(…,is)`; `advect_tend=advect_tend`; `msfty=grid%msfty`; `c1/c2=grid%c1h/grid%c2h`; `mu_old/mu_new/mu_base=grid%mu_1/grid%mu_2/grid%mub`; and `rk_step=rk_step`, `dt=dt_rk`. For NC, the variable-loop selection makes `is=P_QNC`, and `scalar` is the `scalar(:,:,:,P_QNC)` field. The neighboring `NC_TEND` and `NC_AFTER` observer calls bracket the update at the same target coordinates.

## Update equation and branches

In `module_em.F:1695–1724` (RK step 1), the routine forms the coupled tendency and updates the old/new scalar fields:

```fortran
tendency(i,k,j) = advect_tend(i,k,j) * msfty(i,j)
tendency(i,k,j) = tendency(i,k,j) + sc_tend(i,k,j,im)
MUOLD(i) = MU_OLD(i,j) + MU_BASE(i,j)
MUNEW(i) = MU_NEW(i,j) + MU_BASE(i,j)
scalar_1(i,k,j,im) = scalar_2(i,k,j,im)
scalar_2(i,k,j,im) = ((c1(k)*muold(i)+c2(k))*scalar_1(i,k,j,im) + &
                      dt*tendency(i,k,j))/(c1(k)*munew(i)+c2(k))
```

For later RK steps, `module_em.F:1746–1774` forms the same tendency and applies the same quotient to `scalar_2`, while `scalar_1` remains the time-t state. Nested or specified-grid options narrow `i/j/k` limits using `spec_zone`, periodic-x, and domain bounds (`module_em.F:1655–1678`); the target cell is within this update's observed tile. Optional `advh_t`/`advz_t` diagnostic accumulation is guarded by `PRESENT` and `tenddec` and does not alter the scalar quotient.

## Attribution limit

The runtime observer measures the field only at completed boundaries. It identifies the `rk_update_scalar` call as the first observed transition when the clean-run trace confirms it, but it does not record the target cell's `advect_tend`, `sc_tend`, `msfty`, `c1/c2`, `mu_old/new/base`, or intermediate tendency/numerator values. Therefore the boundary trace cannot attribute the transition to a specific term or operand. A follow-up diagnostic must capture those exact scalar operands at `(i,k,j)=(4,22,2)` before proposing a physical correction. No source physics or numerical validation rule is changed by this excerpt or observer.
