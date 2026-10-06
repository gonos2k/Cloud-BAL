# Joint-candidate and native first-call team review — 2026-10-06

Base: `ea2c02bb808bc9cf77b97fc4a25a2da06dfd73a1` (PR59 on main).
Four independent responsibilities covered component feasibility, numerical
review, isolated actual-case replay, and native first-call tracing. No GNU
Fortran result is used as Cloud-BAL validation.

## Findings addressed before source freeze

| Finding | Resolution |
| --- | --- |
| Missing optional species could be indexed by a stricter component check | Require complete allocated, shaped water fields before indexing; missing representation remains unsupported. |
| NaN declarations could reach ordered tolerance comparisons | Check finiteness first, then nonnegative physical tolerances. |
| Large source/boundary declarations could overflow when added | Compare scaled endpoint operands and declared increments without constructing their potentially overflowing sum. |
| Invalid NaN placeholders could trap during permission/identity checks | Compare only valid entries, after sequential finite checks; preserve mask and metadata checks. |
| Global cancellation could conceal opposite local component violations | Check all declared atmospheric cells separately and identify the first failing cell/component. |
| A fixed point could be accepted before component feasibility was checked | Evaluate every completed block trial before the stored-value fixed-point test; restore both output states and clear the accepted ledger on failure. |
| Writer comparison could discard newly added assessment fields | Compare those fields and reject nonfinite scaled residuals before equality; the current writer cannot reproduce a supplied contract and fails closed. |
| Native stream byte order and dimension labels could be ambiguous | Pin observed big-endian int32/real32 layout, validate header and payload, report physical x/y/z shape and explicit active-tile scope. |
| Native nonfinite statistics could produce invalid JSON | Count nonfinite values explicitly, summarize finite extrema, and reject nonstandard JSON numbers. |
| Unit runner assumed a checkout directly below KLAPS50 and compiled its bridge in the source tree | Resolve the existing workspace override and use fresh external test scratch; the installed pinned ncgen was present. |
| Native output cadence could be mislabeled as seconds | Record the namelist's minutes and seconds fields separately; a start-time reflectivity record is not a t+20 measurement. |

The supplied source and boundary arrays are checked only as a net prescribed
increment. Their independent attribution is not authenticated. Observation
fit, constrained stationarity and native conservation remain unassessed.
The actual producer does not supply the optional component contract; its
research result remains distinct from a joint physical acceptance.

## Execution evidence

- [Candidate contract](JOINT_CANDIDATE_PHYSICAL_CONTRACT_20261006.md)
  defines the mass metric, enthalpy reference, fixed geometry and API scope.
- [Actual-case checklist](NE57_PHYSICAL_EXECUTION_CHECKLIST_20261006.md)
  separates retained source `9017919` evidence from the new frozen-source replay.
- Native first-call evidence is tied to the retained source-901 candidate's
  exact WPS bytes. A diagnostic trace and a completed 20-second integration
  establish a captured call, without approving missing moment priors or a
  complete native initialization.
  [The report](PR59_CURRENT12_NATIVE_KDM6_FIRST_CALL_20261006.md) records
  negative call-entry CCN and 33,617 nonfinite t+20 reflectivity cells, all
  matching positive rain mass with zero rain number. This is a failed native
  gate despite finite traced thermodynamic and moment arrays.

## Validation scope

Pinned Intel O0/O2 `test_pipeline` passed in separate fresh `/var/tmp` build
directories. The complete `run_real_shadow_io_contract_tests.sh` passed,
including forged component-PASS and NaN-residual writer rejection. Ten native
parser tests and actual stream replay passed. These are distinct executions.

The broad `run_unit_tests.sh` run was deliberately stopped before its legacy
child runners, which still assume source-tree scratch. Its partial log is not
a whole-suite PASS. The installed pinned ncgen exists; the original early
failure was the test's worktree-root assumption, now corrected. The stop
removed temporary working directories while a compile was active, producing
a trailing `getcwd()` error; that is not a failed numerical assertion. No
child runner or source-tree compile was used as validation evidence.

BASE/HYDRO/COUPLED startup comparison, independently admitted physical
increments and boundary fluxes, observational error models, complete moment
priors, 10/30/60-minute response and forecast benefit remain open. They cannot
be replaced by component accounting, a finite first call, a stored fixed
point, or a fresh graph snapshot.

## Final frozen-source replay

Clean source `44212f938f0a529d298e903dc4146d7e0401134a` built and ran the
actual NE57 BASE and `LIQUID_RADAR_RH1_PHI` arms in external scratch.
Recorded build inputs (391), runtime entries (41), immutable input-copy hashes
and final source guards passed. Closed WPS/SHADOW readback passed. All three
product hashes match source-901 products byte for byte; execution lineage
remains separate. No transaction was committed or published. Neither this
research producer nor its readback establishes a coupled physical solve.

[The validation index](evidence/pr60_team_validation_20261006.json) pins code,
profile and logs, keeps the partial broad-unit run separate, and links the
[new producer receipt](evidence/pr60_current_lapsprep.json) to the failed native
reflectivity gate. Remaining scientific blockers stay explicit; no arbitrary
number or volume value was inserted to bypass them.
