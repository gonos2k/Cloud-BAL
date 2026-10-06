# PR62 team review — 2026-10-06

Base: `6f403258a8b67675e0882f0edb0cbbe3a6ee5459` (PR61 main).
Changes were made in an isolated worktree; the dirty maintained source checkout
and maintained WRF/KDM6 source were not used as edit targets.

## Independent responsibilities

Four `gpt-6-luna` agents with high reasoning reviewed separate responsibilities:
common volume bounds and file replay; contract retention/writer/readback;
native process tracing and experiment; independent process mathematics and
mass-scale audit. The root reviewed the combined changes and file identities.
Graphify guided navigation; exact source, tests, and recorded bytes are the
verification evidence.

## Findings and resolution

| Finding | Resolution and scope |
| --- | --- |
| Derived volume limits overflowed to Inf and passed NaN comparisons | Reject nonfinite bounds before tolerance calculations; ordinary density declarations retain their prior result. |
| 49,067 returned cloud-mass/zero-number cells had not been process-attributed | A diagnostic control preserves the old pre/post/output bytes. Of the gaps, 49,066 are tagged in full cloud evaporation; the largest was already present at entry. |
| Full evaporation returned NC before rate arithmetic left positive QC | One captured positive phase extent updates QC, QV and the existing latent-temperature relation together. Zero extent and non-trigger paths retain the original arithmetic. |
| A supplied component contract disappeared at writer reevaluation | Retain its declaration, label, coverage, increments and tolerances; replay with the retained contract and serialize the eight-component inputs. |
| A first reader draft could assess a detached physical-state copy | Bind available canonical field values/masks and dry mass, enforce ranges and packing, and reject a coordinated state/source mutation. |
| A draft fallback confused a matching copy with an unchanged candidate | Compare candidate mass with background only for actually unchanged thermo state; otherwise reconstruct it from pressure mass and represented water. |
| Draft handling treated an empty supplied contract like an omitted one | Preserve `PRESENT` semantics and allocation-aware dispatch; test default-contract failure/rollback separately from omission. |
| Geometry metadata named a different input than the runtime input | Report both hashes separately. Actual input is zero QC/NC at the remaining cell; the creating pre-call step remains unlocalized. |
| Neighbor and temperature labels were imprecise | Distinguish four horizontal neighbors, upper/lower vertical positions, and NetCDF perturbation potential temperature from raw TH×PII air temperature. |
| A diagnostic build omitted the REAL32 CPP definition | Exclude the stalled run from causal evidence. The corrected control uses `RWORDSIZE=4` and the pinned Intel profile. |
| A scratch hardlink clone rewrote historical raw/launch artifacts | Restore exact recorded bytes from an independent matching control, detach outputs, and record the incident and hashes. New experiments require fresh output files. |
| A copied manifest and provisional output hash were stale | Check actual compiled source/object/executable and output bytes; final candidate output is distinct from the control. |
| An agent refreshed the isolated historical graph instead of the selected maintained corpus | Preserve the attempted outputs and restore that historical graph; update the two maintained corpora separately after source freeze. |
| An initializer cap was being interpreted as a runtime invariant | Report it as a conditional prior diagnostic; do not count it as a universal native PSD constraint. |

The findings were addressed or explicitly retained as scientific open items.
No change lowers the physical acceptance criteria or modifies the frozen PSD prior.

## Validation

- Focused Python helper/MP37/initializer/parser batch: **87 tests passed**;
  source bytes were equal before and after the batch. This is not the full suite.
- Pinned Intel actual SHADOW writer/readback harness: **O0/O2 passed** in fresh
  external scratch. Final pipeline presence/rollback code was retested O0/O2.
  The receipt separates the earlier writer-build pipeline bytes from the later
  semantically equivalent cleanup; it does not assert a clean compiler-process closure.
- Independent file replay: **11 corruptions rejected** for each writer fixture;
  two synthetic changed-state reader controls passed. The actual writer fixture
  is schema-5, 2×2×2 and zero-change. Source authority and joint optimality are unproved.
- Matched copied-source native run: **20 seconds completed**, byte-identical
  first-call input; returned `QC>qmin, NC=0` count **49,067 → 1**. Reflectivity
  has no nonfinite values. This is one rank, one tile and inherited host objects.
- Local water/temperature update is checked against its recorded operands;
  a same-call total water/energy or mapped conservation proof is not available.

The [contract receipt](evidence/pr62_component_contract_readback.json),
[scale audit](PR62_MOMENT_SCALE_AUDIT_20261006.md),
[pre-call gap audit](PR62_PRECALL_CLOUD_GAP_20261006.md), and
[closure checklist](PR62_REVIEW_CLOSURE_CHECKLIST_20261006.md) retain the scopes,
paths, hashes, and remaining gates.

## Physical decision and next work

**Full physical approval remains FAIL/OPEN.** One positive-QC/zero-NC cell and
23,494 negative entry-QC cells require tracing before KDM6. Strict post-call
moment checks fail for cloud, ice, rain and graupel; small float32 edge flags
are distinguished from the zero-number and zero-mass/nonzero-volume cases.
The native patch is a research source-copy change, not deployment to maintained WRF.

Next work is ordered: locate the earliest pre-call Q/N failure; preserve the
joint moment domain through common-air transport and finalized process updates;
generate feasible joint trials with independent source/boundary terms and internal
phase freedom; verify same-call native mapped budgets and parallel execution;
compare fixed-setting BASE/HYDRO/COUPLED at 10/30/60 minutes and against independent
observations. Reflectivity finiteness and a small gap-mass share do not replace these gates.
