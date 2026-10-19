# PR89 native dry-mass and face-flux source gap — 2026-10-19

## Bound history evidence

The receipt-bound OFF and COUPLED `wrfout_d01_2026-08-16_13:00:00` files each have records at `13:00:00` and `13:01:00`. Both are C grids with `DX=DY=5000 m`, 282×234 mass cells, 39 mass levels, and 40 vertical interfaces. Available fields include `MU`, `MUB`, `C1H`, `C2H`, `DNW`; staggered `U` (`39×282×235`) and `V` (`39×283×234`); and face geometry `MAPFAC_UY` on U faces and `MAPFAC_VX` on V faces. The corresponding dimensions and grid descriptors match across arms. `MUT`, `MUU`, and `MUV` are not history outputs.

The existing PR87 native reader reconstructs cell dry layer mass as `dp=-(C1H*(MU+MUB)+C2H)*DNW`, multiplied by `DX*DY/(MAPFAC_MX*MAPFAC_MY)/g`. This supports endpoint column dry mass by summing layer mass. It does not establish a flux tendency.

## What the V50 caller establishes

The hash-bound V50 `module_em.F` calls `couple_momentum` with `MUU/MUV`, `U/V`, `C1H/C2H`, and staggered map metrics: `MSFU=MSFUY` for U and `MSFV=MSFVX`, `MSFV_INV=MSFVX_INV` for V. Its comments identify `MUT` as total column dry-air mass and `MUU/MUV` as total column dry-air mass at the horizontal velocity points. Thus the caller confirms the model uses face-coupled dry mass, hybrid layer coefficients, and map factors for the native momentum transport variables.

## Why a physical face flux is not yet source-verified

The preserved V50 source bundle contains `module_em.F` and `solve_em.F`, but not the definitions of `calc_mu_uv`, `couple_momentum`, or the routine that forms/advances the MU tendency. A sibling scratch source copy contains plausible formulas—arithmetic neighboring-column averaging for MUU/MUV and `C1H*MUface+C2H` coupled to U/V with the above map-factor arguments—but its provenance is not bound here to the V50 executable's base archive. I therefore do not treat those formulas as verified for this run. The history has the needed raw fields, but reproducing producer face weights and the physical face-length convention still requires those exact helper sources or an equivalent source-hash binding.

## Time-integration limit

Even with exact face formulas, `60 s * (divergence(T0)+divergence(T60))/2` would be an **endpoint-quadrature indicator**. The histories provide only endpoints; WRF's multi-stage Runge–Kutta/substep tendencies and boundary/nesting updates are absent. It cannot be called a completed-step dry-mass continuity closure. No new diagnostic was implemented.
