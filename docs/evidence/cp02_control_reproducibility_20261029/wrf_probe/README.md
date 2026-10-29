# CP02 WRF first-call capture feasibility

Read-only artifact/source inspection, 2026-10-29. No model was launched and no binary was built.

## Finding

A narrowly scoped three-arm first-microphysics capture is feasible to prepare against the *historical CP02 executable*: `Cloud-BAL/scratch/cp02_host_unit_contract_x3bcr8ui/host/main/wrf.exe` exists (71,834,200 bytes), and its SHA-256 `de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168` equals `Cloud-BAL/scratch/cp02_six_hour_20260914/RUNNING.json` and the recorded OFF/HYDRO/LIQUID run binding. It is an x86-64 ELF executable, not stripped; `nm -C` exposes `module_microphysics_driver_mp_microphysics_driver_` and KDM6 symbols. Co-located archived sources are present under `Cloud-BAL/scratch/cp02_host_unit_contract_x3bcr8ui/host/phys/`, including `module_microphysics_driver.F` (SHA-256 `bcac98180bfb5e260271a5836d71c5936d47ab167e2164c37b328f37ec2c03f4`) and `module_mp_kdm6.F` (SHA-256 `49cf8b0e3905a8d584073fdf3345ddfa64a0b0bac178676584505f7c4d7187ca`). These hashes were measured from the co-located files; no build-input source manifest was verified, so they are not asserted to be the exact source used to compile this executable. The CP02 namelist sets `mp_physics=37`.

The executable has `.symtab` but no `.debug_*` sections and `readelf --debug-dump=info` yields no DWARF. Thus function entry/return breakpoints and address-based state capture are plausible; source lines, formal argument types, and optimized local process tendencies are not directly inspectable in GDB. The co-located sources and binary do not by themselves establish that every desired microphysical process term is recoverable from the call frame. Intel Fortran ABI/argument addresses and per-rank point ownership must be established for a valid capture. Binary identity and symbols do not establish scientific validity.

## CP02-only evidence that can be joined

- The historical three-arm six-hour histories are retained in `Cloud-BAL/scratch/cp02_six_hour_20260914/{off,hydro,liquid}/run/`, with native 12:00 and hourly fields through 18:00; `docs/CP02_FIRST_HOUR_TRACE_SCOPE_20261027.md` and `docs/evidence/precip_transitions_20261027/native_trace/final-v2/` bind the 20 lost-hit stencil and its 4-corner mapping. Histories contain state, winds/vertical velocity and accumulated precipitation, not process-rate budgets.
- `docs/evidence/cp02_density_controls_20261029/controls/selected_points.csv` carries a 20-point selection: 16 RN1 comparison points (four each across the documented categories) plus four payload-proxy controls. Its native-corner indices and bilinear weights are usable as a selector/mapping source; it is not a WRF first-call capture. `controls/receipt.json`, `controls/wrf_mapping.csv`, and `controls/capture_points.csv` preserve mapping provenance. Existing CP02 density GDB evidence is a LAPSPREP/HYDRO shadow capture, not a WRF capture and not an OFF/HYDRO/LIQUID microphysics comparison.
- `docs/evidence/cp02_initial_species_20261027/historical_lineage.json` binds the original OFF, HYDRO and LIQUID `wrfinput_d01` candidates and makes clear that the PAIR_RECEIPT `real_OFF` is not the actual six-hour OFF input. Use the actual trajectory inputs in the retained run preparation/launch records; keep each arm's correct input and common boundary paired.
- The 13 UTC RN1 files and mapping already underpin selection/verification, but RN1 per-hour upstream input timing/coverage remains unresolved (`docs/CP02_RN1_REPRESENTATIVENESS_20261027.md`). Do not use RN1 as a process-rate proxy.

## Keep experiment families separate

This target is the archived 2026-08-16 12 UTC CP02 OFF/HYDRO/LIQUID experiment. PR60/C1 first-call and selected arithmetic records are Cloud-BAL diagnostics, not CP02 trajectories. PR99-C2 is a later 640-second Cloud-BAL candidate-storage run using its own C2 executable (SHA-256 `387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a`) and C1 template inputs. Neither C1 nor C2 capture can stand in for CP02's original three-arm first-call response. Their dry-mass ledgers may inform capture design only.

## Smallest next experiment

1. Make fresh, isolated run copies of the three archived CP02 initial inputs and their historically paired boundary/configuration/physics tables. Pin and recheck the historical WRF executable hash above. Do not rerun `real.exe` or alter source/input state. Record each arm's exact input and boundary hashes.
2. Use the existing 16 RN1 point IDs and four native corners/weights from the source-bound mapping, while retaining the separate 20-cell lost-hit stencil for cross-reference. Capture at the native corners before and after the first observed `module_microphysics_driver`/KDM6 invocation in each arm, recording valid time, timestep/RK stage, MPI rank and local index. Do not assume one invocation per step. Include at least `QVAPOR, QCLOUD, QRAIN, QICE, QSNOW, QGRAUP`, temperature, pressure, density, layer thickness, `MU/MUB`, eta coordinates, map factors/grid area, vertical velocity/winds, and precipitation accumulators; capture process tendencies/fluxes only where addresses and units are independently established.
3. Capture the first post-step native state and accumulated precipitation from a deliberately short, receipt-bound run so the observed KDM6 response can be connected to the first transport/dynamics increment. Compare each arm to its own t=0 state and then compare arms; do not call the cross-arm delta a single-process effect.
4. Derive a dry-air layer mass on an explicit basis from captured native geometry. For WRF eta layers, retain positive `Δη`, `MU+MUB`, gravity, map factor and cell area, and document the exact conversion used; keep per-layer mass separate from pressure-carrier-weighted Cloud-BAL ledger units. Reconcile hydrometeor mixing-ratio changes/tendencies against that layer mass and exported fluxes before interpreting a residual as loss.

Any build or runtime instrumentation must use the pinned profile `Cloud-BAL/tests/intel_toolchain.sh` (profile SHA-256 `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`), with compilation in a fresh scratch directory if later needed. No forecast or build was run for this inspection.

## Open points and limits

- Establish per-rank native corner ownership and ABI-safe access to arguments/globals with the exact executable; the current image lacks DWARF.
- Confirm whether KDM6's relevant process tendencies/precipitation fluxes survive as addressable values at the historic build's optimization level. If not, no source substitution or newer executable should be presented as original CP02 evidence; preserve the result as a feasibility limit and propose separately labeled instrumentation.
- Exact time-stamped RN1 upstream input/coverage remains open. This capture can link model response to the retained RN1-selected locations, not validate RN1 producer provenance.
- No full water/energy closure or causal explanation follows from endpoint snapshots alone.

## Extraction limits

Graphify query was run against the maintained graph (`graphify-out/graph.json`, 41,683 nodes) to locate dry-mass and first-call evidence; the broad query returned 994 nodes and truncated at the 1,200-token budget, so source and receipts were checked directly. No graph snapshot was rebuilt or changed. The paths/hashes above are bounded to the named CP02 artifacts and executable; no broad archive claim is made.
