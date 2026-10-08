# PR72 retained-observation candidate preflight (2026-10-08)

## Decision

The 2026-08-16 12 UTC all-observation physical candidate remains **BLOCKED**.
The retained inputs contain useful observations, but they do not include the
independent declarations needed to assign those observations a physical source
term, uncertainty, boundary transport, common-air moment budget, or an adjusted
wind prior. `tools/pr72_joint_candidate_preflight.py` now rejects this case
before candidate evaluation with exit code 2. Its machine-readable result is
`docs/evidence/pr72_joint_candidate_preflight_result_20261008.json`.

The preflight checks declaration completeness and exact time matching only. It
does not authenticate cited evidence or approve the science. A `READY` result
would mean that required declarations are present for evaluation, not that a
candidate is physically valid.

## Authority inventory

| Component | 12 UTC evidence | Admission |
|---|---|---|
| Radar analysis | 70,051 usable echo cells; the producer emits diagnostic omega targets, but there is no independent per-cell radar-analysis source/error declaration. | Missing for an all-observation physical source term. Do not derive it from endpoint differences. |
| Phase exchange | Existing liquid saturation adjustment to RH=1 is supported as a conditional background thermodynamic experiment at the frozen PR64 cell. | Conditional only; not authority for the full radar-conditioned candidate. |
| Physical boundary | Fixed pressure geometry can define a scoped geometric increment; it does not supply the required water and enthalpy boundary fluxes. | Missing. |
| Common-air moments | Existing native captures do not establish one candidate-interval QC/NC carrier with donor-face, limiter, boundary, and RK terms. | Missing. |
| Wind | No source-matched omega target/sigma pairs and no background-omega uncertainty declaration. Fixed background winds are permitted for the conditional phase trial. | Fixed wind is not a completed wind analysis. The paired model increment is 13 UTC and cannot be used for this 12 UTC case. |

These findings follow the existing 12 UTC preflight and admission audit in
`docs/PR65_OBSERVATION_JOINT_PREFLIGHT_20261007.md` and
`docs/PR67_JOINT_INPUT_ADMISSION_20261007.md`. The separate 13 UTC paired-model
route does not change any 12 UTC gate.

## Conditional trial receipt

I reran the existing conditional phase-only experiment with the pinned Intel
O0 profile in a fresh `/var/tmp` build directory. The immutable input files,
source set, objects, executable, and independent reader passed their pre/post
hash guards. The candidate returned success and the independent physical
contract NetCDF readback passed. The receipt and copied candidate/readback
outputs are `docs/evidence/pr72_conditional_phase_O0_20261008.json`,
`docs/evidence/pr72_conditional_phase_O0_candidate.txt`, and
`docs/evidence/pr72_conditional_phase_O0_readback.txt`; the NetCDF artifact
remains in the temporary run directory recorded in the receipt.

The trial preserves the existing PR64 scope: 12 UTC background prior; one
predeclared cell `(143,191,9)`; liquid saturation adjustment to RH=1; zero
external source and physical boundary increments; fixed pressure geometry and
winds. The radar, radar LOS, and categorical cloud observations are withheld
from candidate evaluation using the canonical missing representation. The
reader still saw 70,051 valid radar cells in the retained source input. The
candidate's 1,294,186-cell physical feasibility coverage passed; its declared
phase extent was `-6.0007274473386669e-5 kg/kg`. The zero source/boundary terms
are trial assumptions and have not gained physical authority. No wind driver
or downstream WPS-to-real handoff was exercised.

This is a fresh conditional receipt, not a new all-observation or joint-wind
candidate. It does not close the missing source, moment, boundary, or wind
authority gates.

## Local closure checklist

- [x] Use graph navigation to trace pressure input, candidate, authority, and writer relationships; source and existing receipts remain authoritative.
- [x] Run the conditional background phase candidate with pinned Intel O0 in fresh scratch and pass independent physical-contract readback.
- [x] Add a fail-closed declaration preflight for retained-observation candidate admission and preserve the result as evidence.
- [ ] Obtain an independently authorized per-cell 12 UTC radar-analysis declaration with an error bound.
- [ ] Obtain external source and water/enthalpy boundary declarations for the same time interval.
- [ ] Declare and validate a common-air QC/NC moment policy on the candidate interval.
- [ ] For a wind correction, obtain source-matched target uncertainty, an approved background-prior uncertainty, or a validated exact-time paired-model target.
- [ ] Re-run the complete retained-observation candidate only after its required declarations are available.

## Validation and graph limits

`python3 -m unittest tests/test_pr72_joint_candidate_preflight.py` passes six
focused checks, including malformed `authorities`, `wind.mode`, and
`evidence_id` values. The CLI returns a controlled `INVALID_DECLARATION` JSON
result with exit code 2 rather than a traceback for malformed nested data. The
actual 12 UTC declaration exits 2 and reports missing radar source/error,
external source, boundary, phase authority for this scope, and common-air
moments. Fixed background wind is explicitly reported as incomplete.

Graphify query navigation used the inherited `graphify-out/graph.json` (1,499
nodes in this isolated worktree; the maintained Cloud-BAL corpus is separately
reported at 7,965 nodes). The raw count difference is -6,466 nodes, but the
snapshots have different freshness/corpus scope, so it is not a semantic graph
delta. The isolated graph predates this change and was not refreshed here.
Extraction limits and graph age mean the graph does not establish code
completeness, runtime behavior, or scientific validity.
