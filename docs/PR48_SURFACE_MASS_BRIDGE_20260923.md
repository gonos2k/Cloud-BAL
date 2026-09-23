# PR48: surface support and common-pressure comparison

This read-only calculation extends the PR47 one-column study at actual13
`(55,162)`. It binds the PR47 receipt, PR45 cloud receipt, PR39 pressure-prior
arrays, and the original LSX surface product by SHA-256. The complete
[receipt](evidence/pr48_surface_mass_bridge.json) records inputs and results.
Production fields and the BALCON path are unchanged.

## What the surface data support

The LSX surface values are `PS=100512.09375 Pa`, `T2=301.219055 K`, and
dry-air vapor mixing ratio `r=0.018475565 kg/kg` at 2 m. The producer derives
LSX MR from surface dewpoint and pressure; it is not an independent moisture
observation. The declared constant-T/r
hydrostatic **0–10 m prior** gives `p10=100399.401549 Pa`, matching the pinned
PR39 array. It supports only `PS→p10`, not an extrapolation to the first
regular 1000 hPa interface. Its supported strip contains 11.282948 kg/m² dry
air and 0.208459 kg/m² vapor *under that prior*.

| Fixed-PS interval | Supported PS→p10 | Unsupported p10→regular lower edge |
|---|---:|---:|
| Original lower edge, 100000 Pa | 112.692201 Pa | 399.401549 Pa |
| PR47 moved lower edge, 100096.887440 Pa | 112.692201 Pa | 302.514109 Pa |

The unsupported spans correspond to total-gas pressure masses of 40.727624
and 30.847854 kg/m². **No dry/vapor split, temperature, energy, height or
flux is assigned there.** Their difference is the PR47 added regular-column
gas mass, 9.879769 kg/m², if PS is held fixed. It is an algebraic requirement
on a still unmodeled partial layer, not an observed transfer. The 10 m prior
alone cannot close the full PS-to-regular-level column at this target.

## Same original pressure intervals

PR47 attached ON humidity cell means to moving dry-mass cells. Here the new
cells are repartitioned over their common 100000–5000 Pa range. The new
100096.887–100000 Pa edge is kept separately, not discarded. For each donor
cell, overlap pressure width divided by donor width carries dry mass, vapor
mass, and the gas-only mixture enthalpy as extensive quantities. The enthalpy
uses Cloud-BAL's `T0=273.15 K`, `cpd=1004.5`, `cpv=1846.4 J/(kg K)` and
`hv0=2.5e6 J/kg`; `r_v=q/(1-q)`. The reconstructed temperature preserves
mixture enthalpy during pressure rebinning; it is not a physical temperature
response. The resulting cell `q` and `T` are
compared with the original ON LQ3 and retained LT1 **endpoint cell means**.
This does not reconstruct unique pressure-level point values.

| Quantity | Result |
|---|---:|
| Moved-edge dry / vapor mass | 9.703431 / 0.176339 kg/m² |
| Common-interval dry / vapor mass | 9630.513291 / 56.790732 kg/m² |
| Maximum / RMS (q) difference from ON cell means | 4.90908e-5 / 1.80270e-5 kg/kg |
| Maximum / RMS (T) difference from LT1 cell means | 0.077234 / 0.031127 K |
| Dry-air and vapor mixture enthalpy before / after | 7.837691 / 32.647704 MJ/m² |

The edge plus common-interval mass closes **separately** for dry air and vapor.
The new common interval's total gas mass equals `95000/g0`. The supported
19-layer gas-column mixture enthalpy changes by +24.810012 MJ/m² at imposed
fixed T. This is a conditional analysis-state difference, **not** an energy
budget or a mandate
to change T: no condensate inventory, pressure work, boundary flux, or
internal phase conversion is represented. Since vapor mass changes, this
enthalpy difference also depends on the stated vapor reference enthalpy. The
`q,T` differences are
observation-operator diagnostics with no fitted acceptance threshold.

The PR47 status remains `PASS_SCOPED / CONDITIONAL_DRY_MASS_COLUMN`. PR48 adds
`PASS_SCOPED / SURFACE_SUPPORT_AND_COMMON_PRESSURE_COMPARISON`; the surface
partial layer is explicitly **incomplete**. A physical candidate still needs
a supported 10 m-to-first-level thermodynamic profile and datum, an assigned
partial-layer species/energy and flux budget, and a native dry-hybrid mapping.
No BALCON ON, native, or forecast authority follows from this result.

Reproduce the receipt with:

```sh
python3 tests/diagnose_qbal_surface_mass_bridge.py \
  --dry-report docs/evidence/pr47_dry_mass_column.json \
  --cloud-report docs/evidence/pr45_cloud_force.json \
  --output /path/to/new/report.json
```
