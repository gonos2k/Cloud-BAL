# PR65 agent-team review (2026-10-07)

Base: `55924db4d9ae040c5234fdddeea2494882b0b64a`.
Four focused agents investigated Phi readback, PBL source/operator lineage,
NC donor transport, and observation-retaining candidate admission. Independent
cross-review and root review preceded the source freeze. Pinned Intel builds
and native experiments used fresh external scratch directories; maintained
WRF sources and operational inputs were not modified.

## Findings addressed during the investigation

| Finding | Correction and evidence required |
|---|---|
| PBL lower-diagonal indexing differs between caller and solver dummy bounds | Replay uses actual `al(k-1)` for row `k`; independent two-level analytic control checks weighted conservation and the Q/N ratio. |
| Mixing-ratio tendency and native mass-coordinate tendency were compared as if their units were identical | Apply the source's `(c1*mut+c2)` conversion once. The remaining QC channel difference is retained, without attributing it to an unobserved process. |
| Original NC face logs came from a different generated source | Instrument the exact retained advection source; reconstruct individual regular-advection faces in RK1/RK2 and keep RK3 PD separate. |
| A donor run was initially described as guarded although its invocation was not guarded | Preserve that attempt and repeat in a fresh isolated run. Check detached inputs, new output paths, receipt hashes and baseline byte matches. |
| Replay tolerance did not fully account for cancellation in face and RK arithmetic | Use operand-based binary32 bounds for each formula, including both face magnitudes and all RK numerator terms; reject nonfinite derived values. |
| A PBL native call capture contained inputs but not returned NC tendency | Separate observed call identity from an independently calculated solution; capture the returned tendency and its accumulation before claiming an actual solution. |
| Historical archive-member continuity could be mistaken for source/compiler closure | Record member hashes separately. Current-source research builds do not retroactively authenticate historical objects. |
| The first O0 Phi run's orchestration script was changed while it was active | Preserve the reader PASS and wrapper failure separately. Repeat the complete suite using an immutable private runner and fresh receipt. |
| Observation absence and lack of direct omega errors could be read as universal rejection rules | Report this case's coverage separately from admission authority. An independently justified background/model route remains possible; no such admission is invented here. |
| A preflight runner could lose the candidate's nonzero exit status | Return the captured process exit; keep all unsuccessful attempts and their source identities separate. |
| Same-call storage differences could be read as closed water/energy budgets | Bind geometry and captures to the guarded run, retain missing sedimentation/process/energy terms, and label temperature changes as diagnostics. |
| A copied transition-mask file produced two appended stage sequences | Preserve the rejected attempt; prepare the new run from only declared immutable inputs and declare the mask as a new output. |
| Rectangular WRF output was cropped with swapped horizontal extents and the initial time was selected | Use named `(Time,k,j,i)` dimensions, explicit global bounds, and the actual `12:00:20` record. Check the resulting `39×280×232` shape and target value independently. |
| The NC donor budget and shared-NC PBL run could be mistaken for one candidate | Keep their run receipts and scientific results separate; the control budget does not measure the PBL patch's effect. |
| Metrics replay could accept swapped times/dimensions, masked values, changed outputs or unchecked transition hashes | Validate both native files, live declared output paths/hash/single-link checks, and stage/mask bytes. Preserve the historical patchless mask receipt gap as PARTIAL instead of rewriting evidence. |

## Approval boundaries

- A successful replay authenticates the declared numerical relationship under
  its recorded inputs and scope. It does not authenticate a physical source,
  observation error model, historical compiler chain, or operational policy.
- PBL common-air mixing and differential particle sedimentation are separate
  processes. This research route does not manufacture NC from QC, add a number
  floor, disable PBL, or replace nonfinite reflectivity output.
- Input coverage, evaluation support, modification authority and candidate
  admission remain separate. A missing independently admitted per-cell analysis
  contract is not repaired by copying its final endpoint into a source array.
- First-call diagnostics and 20-second research output do not establish
  reduced acoustic/gravity-wave adjustment or improved rainfall forecasts.

Final checks and their exact receipts are recorded in the
[closure checklist](PR65_CLOSURE_CHECKLIST_20261007.md). Full physical approval
remains **FAIL/OPEN** until the remaining native admissibility, water/energy,
joint-state and time-response gates have direct evidence.

## Final focused regression gate

Root ran 51 tests across the geometry (14), paired BG (3), QC channel (8),
NC donor (5), PBL replay (7), same-call reducer (4), and domain metrics (10) suites. All passed;
the source-file pre/post hash guard passed. Commands, results and log hashes
are retained in the [focused receipt](evidence/pr65_final_focused_validation_20261007.json).
This is an affected Python regression gate; it is not a full unit-suite,
Fortran rebuild, native forecast, or scientific approval claim. Pinned Intel
builds and guarded native results are recorded separately by their owners.
