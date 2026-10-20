# PR92 graupel source identity capture

`tools/pr92_source_replay.py transform` accepts only the archived PR91 C14
`module_em.F` (SHA-256 pinned in the tool) and creates a diagnostic overlay.
The replacement keeps the failing identity guard and its early return. At each
rejected guard it appends exact binary32/binary64 bit patterns to
`pr92_graupel_source_capture.raw`; it does not alter source terms or candidate
state.

The capture includes timestep/RK/cell, producer identity when supplied, QG and
QIB five-point old-state stencils, diffusivity and metric inputs, diffusion
face coefficients, old/new carrier, density, pair4 `qt`/`nt` and `qs64`/`ns64`,
plus the donor weights and QG/QIB donor terms. When the paired producer cache is
present, it records the pair4 correction delta. The raw/physical source producer
arrays and old/non-diffusion cache only carry pair1/2 in this build; pair4
provenance is represented by actual pair4 tendencies and the pair4 delta, never
by indexing pair1/2 storage as if it had pair4 entries. A separate bounded scan
records up to twelve failed pair4 baseline candidates, including store failure
stage, candidate components, bounds, density, and carrier.

Run `python3 tools/pr92_source_replay.py summary --capture PATH` to count
captured failures, report the first location, and calculate the maximum
absolute difference between each captured source total and the corresponding
recomputed old-state diffusion. The summary describes the records available in
the file; a failed certification can return before later cells are visited, so
it is not a whole-domain count. It rejects empty or unrecognized captures. A separate RK1 fixture and its actual producer
identity must establish which source component causes T15 failure.

C14 source audit: the current guard compares the combined pair4 source amount
(`qs64`/`ns64`, initialized from `qt`/`nt` and possibly adjusted by cached
paired diffusion) with a direct diffusion evaluation on old `q1`/`n1`. That is
a caller-contract inconsistency requiring a source ledger before correction;
this observation alone does not identify the T15 producer component. The
pair4 QG/QIB physical check uses graupel bulk density and rime-volume mixing
ratio. QIB is not a particle-number moment.
