# Team 02 Cloud-BAL microphysics contract audit

Date: 2026-10-12  
Scope: Q/N/B microphysics contracts, PSD admission, particle creation/extinction, phase transfers, and local process transaction behavior. Read-only review of the PR77 working source/evidence plus the frozen selected research source `/var/tmp/pr73_native_first_violation.x3bvfn/build/source/module_mp_kdm6.f90`.

## Outcome

The current PR77 native KDM6-entry arm is reproduced as **REJECTED** at the actual ice number-only state `(i, call_lat_index, k)=(104,2,1)`: `QI=0` and internal `NI=4.2038792500161422e-36 m^-3` (public `NI=3.8173049035872155e-36 # kg^-1 dryair`). The strict species preflight correctly rejects it before PSD work. The startup-plus-entry arm instead exits earlier in host initialization with Intel floating-invalid (signal 6); it gives no KDM6 process result. Both miss all declared post-call files. Neither is a successful physics call or evidence that the FTZ/DAZ policy alone caused the startup failure. The previous graupel coordinate is not the PR77 fatal.

Separately, source review finds unresolved state transitions: cloud freezing transfers mass and latent heat even when the donor cloud number is below its transfer threshold; rain freezing assigns graupel at the source ratio 1000 kg m^-3, outside the selected PSD support [100,900]; and small-species cleanup zeros water mass without a paired vapor/heat transfer. These are source-verified triggers and impacts, but were not dynamically reproduced in this audit. The rain cold-process fraction helper checks a trial endpoint before applying its selected rates; the subsequent in-place endpoint update has a fatal check but no rollback path.

## Findings

### F1 — Actual PR77 KDM6 entry has orphan ice number

**Class:** Reproduced native rejection. **Priority:** P1.  
**Source:** `module_mp_kdm6.f90:L193-L208` classifies exact zero-mass/positive-number as `SPECIES_NUMBER_ONLY`; `L253-L264` rejects it; `L210-L225` runs the admission check at `L1489`, before internal clipping or PSD reconstruction. The public-to-volume conversion is `L945-L951`.  
**Trigger/result:** The recorded first KDM6 entry has `QI=0` and positive subnormal `NI` at `(104,2,1)`. The KDM6-entry arm exits 128 with `KDM6 orphan number/volume state without positive mass`; the startup-policy arm exits -6 before KDM6. Native receipt `docs/evidence/pr77_native_state_20261012.json` binds both arms. PR77 progress notes confirm the `.f90` copy now explicitly uses `-fpp`, so the measured converted NI is not overwritten by the test-only preprocessor branch.  
**Impact:** No property/process stage or KDM6 return is reached; `kdm6_first_call_post.raw`, process/water captures, and t+20 WRF output are absent. The same receipt's pre-call audit reports 299,933 moment-only, 740 mass-only, and 23,494 negative cells over the captured active domain. This is an input-state rejection; this audit does not attribute its producer (upstream PBL/advection/RK are Team 03 scope).

### F2 — Cloud freezing can transfer liquid mass without ice number

**Class:** Static source risk, directly visible branch; no targeted execution in this audit. **Priority:** P1.  
**Source:** `module_mp_kdm6.f90:L2277-L2301`. For `supcol>0` and `QC>qmin`, positive freezing extent is formed and QC-to-QI mass plus fusion heating are applied at `L2279-L2301`. Ice-number transfer is conditional on `NC>ncmin` at `L2289-L2298`; mass transfer is unconditional within the freezing branch. The later local paired-state validator is at `L3982-L3984`.  
**Trigger/result:** A supported input with `0 < NC <= ncmin`, supercooled cloud and a surviving `QI>qmin` can transfer positive QI while `NI` remains zero. The local species validator then rejects the generated mass-only ice state; if the QI falls below cleanup threshold first, F4 applies and the mass is discarded.  
**Impact:** Either a controlled fatal before return or unaccounted water/thermal removal under cutoff cleanup. The exact positive-N subthreshold range and rate cases need a pinned-Intel source fixture before calling this a reproduced runtime defect.

### F3 — Rain freezing creates graupel outside the selected density domain

**Class:** Static selected-source risk; earlier source-matched observer evidence exists but is not the PR77 fatal. **Priority:** P1.  
**Source:** `module_mp_kdm6.f90:L2307-L2325` creates graupel mass `QG += pfrzdtr`, bulk volume `BG += pfrzdtr/denr`, and fusion heating; the retained driver constant is `denr=1000 kg m^-3`. `ProgB_param` accepts only 100–900 kg m^-3 at `L4322-L4477` (density setup checks are around `L4390-L4420`); unsupported status is rejected by the slope consumer at `L4531-L4536`.  
**Trigger/result:** A positive rain-freezing extent produces `QG/BG=denr=1000 kg m^-3`. If the resulting pair survives terminal cutoff, the next graupel property setup is unsupported. Prior PR70/PR71 receipts observed the same source ratio and domain mismatch; PR71 documents a matched tiny pair and controlled fatal. Those historical coordinates and runs must remain distinct from PR77's actual `(104,2,1)` ice failure.  
**Impact:** The generated pair has no admitted PSD properties and can terminate a later process stage. If it is below the cutoff, the terminal cleanup clears both QG and BG but then F4 applies to its water mass. No source-backed creation/extinction convention that enters the 100–900 domain is established.

### F4 — Small-mass cleanup deletes water without phase/heat accounting

**Class:** Static source behavior; no runtime mass-closure reproduction in this audit. **Priority:** P1 for a conservation acceptance gate.  
**Source:** `module_mp_kdm6.f90:L3918-L3936`. QC/NC and QI/NI are zeroed when their mass is `<=qmin`; QR/NR, QS, and QG/BG are zeroed when mass is `<=qcrmin`. These assignments do not add the removed condensate to vapor or another species, and do not adjust temperature.  
**Trigger/result:** Any positive species mass at or below its threshold is removed at cleanup. The removed amount per cell is bounded by the relevant threshold; the model-domain sum is unmeasured in the PR77 receipts because both native arms reject before completion. Pair/descriptor clearing is internally consistent for these branches, but water and phase enthalpy are not accounted for.  
**Impact:** Water storage loses up to the cutoff amount per affected cell; the thermal state also lacks the corresponding phase-change treatment. Cumulative impact is unknown without same-call pre/post captures and geometry.

### F5 — KDM6 process state is not rollback-atomic

**Class:** Missing rollback implementation/evidence; no recoverable failure was reproduced. **Priority:** P2 (fatal-path integrity); P1 if KDM6 is expected to reject and continue transactionally.  
**Source:** The rain/cold process builds fixed and scalable trial components and calls `kdm6_rain_process_fraction` at `module_mp_kdm6.f90:L3473-L3480`; failure stops before the rain-block writes at `L3486-L3506`, and successful selection scales rates at `L3508-L3519`. It then applies updates directly to Q/N/B/T at `L3537-L3577` and validates the stored endpoint afterward at `L3579-L3592`. The validator failure is `error stop`, with no snapshot restore. Other phase/sedimentation updates also mutate local state in sequence. At the wrapper, public Q/T fields are copied only after `kdm62D` returns (`L989-L1028`), while surface precipitation accumulators are passed into and updated inside the routine (`L2088-L2110`); timestep-1 `NN` is initialized before species admission (`L900-L925`).  
**Impact:** Candidate search is locally pre-validated, but the complete KDM6 call has no error-status/rollback contract. A fatal terminates the model; receipts show no post-call outputs. There may be prior column/precipitation side effects in memory, but no evidence shows they were serialized or consumed after these fatal exits. Do not describe the process trial guard as full-call atomicity.

## PSD and transition evidence

The paired-state validator admits any finite strictly positive Q/N or Q/B pair; it does not itself establish a feasible PSD. The source later reconstructs gamma slopes and bounds for selected active ranges, and `ProgB_param` enforces the selected graupel density range. Historical PR62 output analysis found remaining source-bound PSD violations after its cloud-evaporation candidate; the PR73 16-mask property matrix returns before n0 reconstruction and process application, and the separate full-module mask probe stops at mask 5. Thus neither the property matrix nor a positive pair is full PSD/process acceptance evidence.

Source transfer signs for freezing/melting and condensation/evaporation pair mass increments with fusion/vapor latent terms on the active path (`L2060-L2081`, `L2277-L2325`, `L3861-L3909`). The full-cloud-evaporation extent path uses one incoming QC amount for vapor, zeroed cloud mass/number transfer, and cooling (`L3894-L3908`). The cutoff cleanup described in F4 bypasses equivalent destination/heat accounting. PR62's matched historical evaporation run reduced 49,067 QC-positive/NC-zero returns to one, but remaining PSD gates failed; it is not PR77 native acceptance.

## Graph navigation, coverage, and exclusions

Used the maintained Cloud-BAL graph at `Cloud-BAL/graphify-out/graph.json` (2026-10-08 PR76 snapshot: 8,542 nodes / 15,847 edges). Queries navigated KDM6 wrapper, graupel-volume transition, PR62 evaporation, rain-process trial helper, and transaction references. Graph evidence directed review to source and docs; it did not establish runtime or physical correctness. The graph receipt reports AST and Markdown-heading extraction with partial cross-file Fortran CALL extraction and no semantic refresh; external frozen native source trees are not extracted. The separate 1,499-node graph under the isolated PR77 copy is stale and was not used as the maintained snapshot. No graph refresh or KG mutation was done because this was a read-only audit.

Read PR61–PR73 source/receipt reports and PR76 closure checklist, inspected the PR77 integration note and native receipts, wrapper fixture README, selected frozen source, and maintained graph. No tests, compiles, native runs, or broad suites were executed. No source, input, prior evidence, or graph files were edited. Excluded producer attribution for upstream PBL/advection/RK (Team 03) and FP/toolchain/startup diagnosis (Team 04). Recommended next microphysics checks are focused frozen-source O0/O2 cases for F2 and F3, cutoff water/enthalpy accounting for each F4 species, and accepted/rejected cold-process state snapshots that verify rollback semantics.
