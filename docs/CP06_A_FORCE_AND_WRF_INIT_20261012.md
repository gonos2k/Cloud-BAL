# Retained force prior and WRF initialization

The retained 13 UTC CP06-A candidate remains the analysis baseline. The force
stage follows its converged background dry-flux prior in the common pipeline;
it preserves the nonzero background force residual as its reference. The
[experiment specification](CP06_A_FORCE_PRIOR_SPEC_20261012.md) fixes the masks,
prior scales, caps, and original continuity thresholds before candidate runs.
This wind-only experiment does not replace the retrieval or erase its T/q/Phi
and hydrometeor increments. Writer replay binds the added stage and stores the
pre-force winds, force mask, and diagnostics. Failure rolls the pipeline back.

The [independent state/geometry analysis](evidence/pr80_force_independent_20261012.json)
uses the same 900-cell mask for OFF, HYDRO, and COUPLED. HYDRO and COUPLED force
RMS are almost identical on that mask; the Phi gradient dominates their added
force residual. Pressure-overlap shared faces and boundary fluxes are rebuilt
from stored state mass measures and geometry, independently of persisted
divergence. Composition-derived mass is also checked separately. Observation
fit and its error assumptions remain unassessed.

The original retained artifact does not export separate candidate wind metadata,
candidate precipitation-phase metadata, or terminal-velocity mean/sigma. A
retained component probe therefore reconstructs wind source bits from the
verified producer rule and serialized changes; it is not an authenticated full
state readback. The new full producer independently rebuilds its state from the
original reader inputs and checks all nonwind state internally before accepting
force refinement. Writer replay compares that complete generated state. The
independent stored-state comparison covers only fields actually exported.

On the fixed 900-cell mask the wind-only refinement lowers absolute geostrophic
RMS from 0.00679215397238 to 0.00666665388082 m/s² (1.85%). The force/wind prior
objective decreases 3.64%. The final OFF-relative dry-flux RMS/max are
1.96540e-10 / 1.27888e-9 s^-1, within the unchanged original thresholds
2.03044e-10 / 1.44934e-9 s^-1. Temperature, vapor, Phi, hydrometeors, omega,
geometry, and exported observation state remain unchanged from COUPLED.

The maximum total horizontal-wind increment reaches the analytic 9.5 m/s
headroom (9.500000589 after REAL32 storage), below the hard 10 m/s cap. The
background force RMS is 0.0006533183 m/s², so the residual is still about 10.2
times background. This is a cap-limited wind-only ablation, not force-balance
closure or evidence of reduced forecast shock. Further improvement requires
examining the thermodynamic/Phi reconstruction with the observation contract.

## WRF initialization is part of the consumption contract

The native research patch is connected through WRF's existing initialization:
`wrf_init → med_initialdata_input → start_domain_em → phy_init → mp_init →
kdm6init → radar_init_variable_graupel`. It preserves the old zero-argument
`radar_init` ABI for inherited callers. KDM6's graupel mass coefficient is
computed locally from QG/BG; radar initialization prepares the shared exponent
and shape, and the wet-particle consumer uses that local mass coefficient.
It does not insert an arbitrary global graupel density to avoid division by zero.

The [native coefficient receipt](evidence/kdm6_graupel_radar_contract_20261012/receipt.json)
binds the source, objects, archive, executable, and pinned Intel profile. A
focused consumer calls the real `kdm6init` twice, then exercises `ProgB_param`
and wet-graupel reflectivity with distinct valid densities and absent graupel.
The copied partial host also reaches its initial WRF output through the full
cold-start path. Restart, nests, DFI, and other lifecycle configurations remain
outside this runtime scope.

The [same-time initialization readback](evidence/pr80_wrf_initialization_readback_20261012.json)
compares the actual wrfinput with WRF's time-zero output. Dry mass and all six
exported water species, Phi, T, and horizontal winds remain unchanged in this
case. Pressure changes by at most 0.0390625 Pa, W by 0.6027584 m/s, and QNCCN
is initialized. Thus the state consumed by physics must be checked after
initialization as well as after `real`. The checker enforces expected WRF
units and C-grid positions. The output lacks graupel volume and cannot certify
the complete Q/N/B state.

This native case is 12 UTC, while the pressure analysis is 13 UTC. They are not
the same candidate. The native run stops during its first integration in
`calc_ww_cp → rk_step_prep`; a completed first microphysics call has not been
established. The exact failing expression is still unidentified. Initialization
success does not establish physical-time budgets or reduced forecast shock.

CP06-A remains `IN_PROGRESS / NOT_RUN` at its complete scientific gate. The
next integration must bind this accepted analysis scope through WPS/metgrid/real,
WRF initialization, and the first completed physical call, then compare short
time response without losing the observed cloud signal.
