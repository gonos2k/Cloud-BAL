# CP06-A background-prior v2: fixed flux boundary buffer

Experiment ID: `CP06A-20260816T130000Z-background-prior-v2`.
Declared on 2026-10-12 before the v2 candidate run. The first v1 attempt is
retained as rejected evidence: it stopped at boundary authority, before solving.
This is a different declared support variant, not a relabeling of that attempt.
All assumptions, retrieval ablation, mixture thermodynamics, existing metric,
solver limits and open science/native gates in the [v1 design](CP06_A_BACKGROUND_PRIOR_SPEC_20261012.md)
remain, with these explicit support differences.

Use the SAME selected real-input center `(i,j)=(136,18)` on the full original
235×283×22 grid. Selection was made from the background and observations,
before candidate outcomes. No alternative window or changed numerical
tolerance is selected after a rejection.

- Wind control: the original 5×5 columns (`i=134:138,j=16:20`), all usable
  above-ground levels. Normal wind increments at its boundary remain zero.
- Material retrieval and thermodynamics: the inner 3×3 columns
  (`i=135:137,j=17:19`), excluding the lowest and highest above-ground cell
  in each column. Warm liquid thermo cells are a subset of that mask.
- Geopotential: all above-ground levels of those inner nine columns, with
  the original lowest analysis-center reference. This is a separately
  declared support; it includes the material support and the overlying
  hydrostatic response, rather than silently expanding material updates.
- Validation shell: the original 7×7 columns, all usable above-ground levels.
  All masks, clocks, dimensions and hashes are recorded before OFF/HYDRO/COUPLED.

The buffer is required by the equation, independently of solver output.
In `F_d = f_d S(v)`, changing the dry fraction on a fixed-normal-velocity
boundary changes dry-air boundary flux. The new material footprint therefore
leaves composition at the control boundary and top/bottom prior boundaries
unchanged. This makes the frozen background flux/tendency constraint meaningful
without inventing a physical source or an arbitrary correction to the boundary.

The actual reader's copied-interior omega boundaries are an explicit prior
assumption: exact analyzed-wind provenance, exact legacy/copy quality flags,
original interior values and unchanged boundary arrays. They are not promoted
to observed physical boundary conditions. Ordinary observation/model target
and physical-boundary gates remain unchanged.

Every trial restarts from the same immutable background. OFF must be identical;
HYDRO must leave winds unchanged; COUPLED must have a nonzero correction and
pass the same rounded dry-flux residual and increment-cap gates. Readback must
verify the exact masks and immutable fields, independently recompute the stored
prior residual, and retain any failed attempt. No complete CP06-A, physical
time tendency, native initialization or scientific forecast approval is claimed.
