# PR73 species state transition evidence

## Property interface matrix

`tests/run_pr73_property_matrix.sh` runs the frozen KDM6 source under pinned
Intel O0/O2 and checks all 16 rain/cloud/ice/graupel masks against clean
reference calls. Each target mask re-enters the actual property reconstruction
after an active mask-15 call with poisoned property outputs. All 32 re-entry
records match their clean references: each optimization profile has 16 clean
reference records and 16 re-entry records. This covers cloud slope moments,
rain slope/number velocity, ice slope/number velocity, and graupel status,
density, properties, and velocity. See
`docs/PR73_PROPERTY_MATRIX_20261008.md` and
`docs/evidence/pr73_property_matrix_20261008/receipt.json`.

The matrix returns after property reconstruction but before `n0` reconstruction,
substep application, and microphysical processes. It validates property-state
independence and poisoned-output clearing; it is not a full-process success.
The separate full-module probe `tests/run_pr73_species_combinations.sh` reached
masks 0–4 at O0, then stopped at mask 5 in `ProgB_param` with
`ProgB unsupported PSD state rejected` (exit 128). Its logs and per-case hashes
are preserved in `docs/evidence/pr73_species_fullmodule_probe_20261008/receipt.json`;
masks 6–15 and O2 were not run by that probe.

## Native first unpaired input

`tools/pr73_native_input_pair_audit.py` binds the staged input to the retained
case time `2026-08-16_12:00:00` and SHA-256
`aecc4885da1d612e57ec8c603b6c85df6a89e3c53cda5a4a302ec65d33866739`. It
selects WRF variables by named dimensions (`Time`, `bottom_top`, `south_north`,
`west_east`) and compares only active `kts:kte` levels. The receipt is
`docs/evidence/pr73_species_native_origin_20261008.json`; three helper tests
cover reordered dimensions, one-based coordinates, and the timestamp.

The preserved first-call KDM6 trace is traversed in source order. The first
invalid pair is ice at `(i=133,j=2,k=1)`:
`QI=3.5308575789291633e-35`, `NI=0`. The staged input at that point has
`QICE=0`, `QNICE=0`; paired ice appears at upper levels in the same column.
This places the first mismatch between the staged input and first KDM6 call.
The stored files do not capture the PBL/RK intermediate values at this cell,
so the exact producer remains open. PBL transport of QI without matching QNI
is source-consistent, but not established as the cause.

## Research-only Shinhong QNI path

`docs/evidence/pr73_shinhong_ni_research.patch` is a research patch against the
existing PR65 Shinhong NC research source copies, not maintained WRF source.
It appends QNI as an optional channel to the same vertical operator that
transports QI, keeps the existing base channels and NC channel offsets intact,
requires the QI tendency interface before enabling QNI, initializes the
optional QNI tendency output, and accumulates the tendency once while the
generic scalar PBL path is disabled. The pinned Intel O0 compile of the
modified Shinhong module passed; see
`docs/evidence/pr73_shinhong_ni_research_receipt_20261008.json`.

The driver and coupled WRF runtime were not built. A pinned-Intel O0/O2
manufactured routine test calls the research Shinhong routine with a QNI
profile scaled by 2^30 from QI, giving mean particle mass within the configured
ice PSD interval. QNI tendency divided by 2^30 matches QI tendency exactly.
Both tendencies are positive at a recipient level whose initial QI/QNI are
zero, and a 60 s update remains nonnegative. Poisoned optional QNI output
halos are zeroed. See `docs/evidence/pr73_shinhong_ni_operator_20261008.json`.
This tests the common operator wiring, not production activation or whole-model
conservation. The patch records a source-supported construction, not a
validated production repair. The existing dry-carrier identity question
remains open: `DEL` is not authenticated as the native hybrid dry carrier. The
frozen `E/1000` graupel policy for
densities outside 100–900 kg m-3 also remains unresolved; this work adds no
floor, deletion, or density substitution.
