# CP06-A thermodynamic density-prior experiment

This specification is fixed before running the new candidate. The case is
2026-08-16 13 UTC, on the existing 235×283×22 grid and fixed PR79 support:
162 material cells, 69 liquid-thermodynamic cells, 180 Phi cells, 500 wind
controls, 980 continuity validation cells and the same 900 force cells.
OFF, the previous HYDRO/COUPLED and PR80 wind-only refinement remain comparisons.

## Independent research prior

Use the immutable background and the observation-derived, saturation-adjusted
column proposal to define `alpha = p/rho_total` from the canonical mixture EOS.
Before Phi reconstruction, minimize the equal-weight scalar research cost
`0.5*(alpha-alpha_column)^2 + 0.5*(alpha-alpha_background)^2` per material cell.
Its target is `(alpha_column + alpha_background)/2` (background weight 0.5).
This is a prescribed research prior. Its strength is not an observation error,
calibrated covariance, force optimum, physical source or time tendency.

Keep all five retrieved condensate mixing ratios and their metadata exactly.
At liquid-thermodynamic cells with nonzero liquid, solve the same saturation
law jointly for T and vapor with that alpha target. At cells with an exhausted
selected reservoir, retain vapor and require subsaturation. Elsewhere retain
vapor and solve T directly. The hard trial limits, relative to the incoming
post-phase proposal, are 5 K and 0.005 kg/kg dry air; reject the entire trial if
either stored limit or canonical/saturation validity fails. These limits are
an experiment envelope, not calibrated uncertainty. Zero strength is a no-op.

## One candidate and separate ledgers

Refresh dry mass and temperature-dependent column diagnostics from the adjusted
state. Reconstruct Phi through the existing hydrostatic increment. Build the
continuity operator from this changed composition, retaining the background
dry-flux tendency and the existing wind/omega caps (10 m/s and 5 Pa/s). Use the
existing force-prior stage only after this trial's continuity convergence.

Record the density-prior water/dry-mass/enthalpy changes as a separate analysis
ledger. Keep the preceding internal phase ledger intact. Do not copy endpoint
residuals into sources/boundary/phase. The final endpoint ledger includes all
stages; a sum of differently weighted phase/analysis ledgers is not a native
physical energy closure.

## Validation and scope

Require atomic rollback, unchanged original inputs and operational output,
retained condensates/observations, stored alpha and saturation closure, the
existing continuity acceptance, and writer producer replay. Independently
reconstruct state/geometry flux and force on the same fixed masks. Report the
change in T/vapor relative to the raw background without asserting an
observation-fit PASS: T/q/cloud error models remain unestablished.

This experiment tests added thermodynamic freedom. A reduced force increment
does not prove scientific acceptance or reduced initial shock. No wind-cap
increase, Phi-only smoothing, cloud-signal attenuation, window reselection,
or native promotion is allowed. The native 12 UTC cold-start investigation
continues separately; the same 13 UTC candidate still needs WPS/real/wrf_init,
first model/microphysics calls and 10/30/60-minute response.
