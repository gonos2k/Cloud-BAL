# B1 representative profiles

`profiles.json` retains five complete 39-level columns from the immutable B1 input named and SHA-256 pinned in its provenance. `tools/cp02_ice_stage_cases.py` selects them before native response analysis using the nominal fixed-mass NI-feasibility ratio: near half the boundary, closest below, closest above, first infeasible in z/y/x order, and maximum ice water content. Tie-breaking is deterministic.

The saved Fortran i,j,k target coordinates are (212,84,20), (199,111,22), (219,236,17), (209,94,17), and (192,72,26). All original mass, moment, thermodynamic, pressure, density proxy and layer-geometry fields are retained. The density proxy is REAL32 `1/(AL+ALB)`; actual temperature uses file dry perturbation potential temperature `T+300` and pressure. These are input estimates, not observed first-WRF-call operands.

Three experimental NI seeds are supplied separately: file QNICE, nominal maximum mean ice mass, and fixed 50 micrometre diameter. The latter two are research inputs, not observations or accepted initialization candidates. The strict publication validator remains unchanged; these probes do not resolve the 1,362 infeasible input cells or establish forecast skill.

[Profiles and source hashes](profiles.json) · [Full report](../../../ICE_NUMBER_STAGE_CONTRACT_20261111.md)
