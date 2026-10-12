# CP06-A real spatial producer: background-continuity prior

Experiment ID: `CP06A-20260816T130000Z-background-prior-v1`.
Declared before candidate execution on 2026-10-12, following the user's request
to develop a real pressure-level candidate alongside native baseline recovery.
This explicit research variant does not replace the observational omega-target
experiment in the earlier v3 specification or approve an operational product.

The case is 2026-08-16 13 UTC (epoch 1786885200). Use the retained processed
LT1/LQ3/LWC/LSX/LCP/LTY observations and Barnes LW3 winds, with the case-bound
FUA/FSF/VRZ/VRT/static inputs. The runner verifies their existing recorded
hashes and keeps the complete 235×283×22 grid, vertical coordinates, terrain,
surface pressure and boundaries. Input arrays remain private and unchanged.

Select the first interior 5×5-column window satisfying the runner's background
and observation coverage rule, in deterministic j/i order, before producing
any candidate. Record the actual window, selection rule and support hash.
No failed candidate is used to select a different window. The validation shell
includes the immediate face-adjacent columns; no support grows during solving.
Liquid-saturation adjustment uses usable warm cloud/radar cells only, with
RH=1 and the existing mixture enthalpy convention. This is an explicitly
limited liquid-equilibrium ablation, not KDM6 kinetics or a mixed-phase policy.
Geopotential reconstruction uses the same pressure geometry and a fixed
original lowest analysis-center reference in each selected column.

Generate OFF, HYDRO and COUPLED from the same immutable background. The initial
analysis variant uses the existing local radar reconstruction with precipitation
transport disabled explicitly. The retrieved water is an analysis increment;
internal saturation exchange has a separate water/enthalpy budget. No transport
rate or transport conservation claim is made. The legacy transport path remains
enabled by default; supported transport rejects arrivals outside its fixed domain.

HYDRO combines retrieval, thermodynamics and geopotential without wind changes.
COUPLED adds the existing pressure-overlap operator and its adjoint/solver,
with candidate dry fractions at each velocity contribution. It minimizes the
existing correction metric (`kappa_u=kappa_v=16`, `kappa_omega=0.25`) subject to

```
dry_mass_tendency_prior = -B F_d(background)
dry_mass_tendency_prior + B F_d(candidate) = 0
```

The tendency prior is diagnosed once from the background in kg/s. Analysis
increments divided by optimization iterations are never used as a time tendency.
The metric corresponds to research prior scales of 4 m/s and 0.5 Pa/s; these are
existing operator settings, not independently validated observational covariance.
No LCO COM, reflectivity or prior omega is relabeled as an omega observation,
paired native target or sigma. Omega target/sigma remain unchanged.

Keep original boundary fields and zero normal wind increments at the control
boundary. The real reader's top/bottom omega copies are accepted only as a
background prior: exact analyzed-wind provenance and legacy/interior-copy flags,
values bound to the original interior omega, and unchanged boundary arrays.
They are not observed physical boundary conditions. The ordinary physical
boundary gate and observation-target gate remain unchanged. Composition-induced
incompatible boundary fluxes reject the candidate.
Use existing limits: at most 800 solver iterations, 10 m/s and 5 Pa/s increments,
RMS and maximum final rounded residual each at most
`max(0.002 * corresponding initial residual, 1e-12 s^-1)` on the fixed shell.
Every producer failure rolls the entire candidate back to the background.
The outer loop is bounded to eight trials, always anchored to the same background;
coefficient feedback is not model time integration.

Acceptance evidence must bind inputs, support, configuration, compiled sources,
one final candidate, writer replay and readback. Independently recompute dry
flux/tendency residuals on cells/shared faces, water and represented-enthalpy
accounting, positivity, immutable fields outside support, and nonzero changes.
Do not copy the final endpoint residual into a physical source contract.

This batch's completion target is a real nonzero pressure-level producer and
its scoped validation. Full CP06-A additionally needs the remaining trajectory,
phase/observation-fit and physical assumptions validated. CP06-B, native first
call, WPS/metgrid/real handoff, energy in native time and BASE/HYDRO/COUPLED
time response remain separate open conditions. Native failures do not prevent
running this pressure-level research experiment.
