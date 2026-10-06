# PR60 follow-up team audit — 2026-10-06

Review base: `303a4f22cb9e5b93a8038d77e4508d22075f5b8f`. Four independent
reviews covered component arithmetic and rollback; writer identity and build
runners; native stream parsing and actual trace; claims, lineage and KG.
Graphify navigation used the maintained candidate-overlay graph. Source and
exact artifacts were authoritative.

## Confirmed finding and correction

The native parser checked active tile bounds against allocated memory but did
not check them against declared global domain bounds. A manufactured header
with `ide=1`, `ite=3`, `ime=3` was accepted although the active tile exceeded
the declared domain. This could give an incorrect evaluation region for a
malformed trace; the retained actual header was coherent.

The parser now checks ordered global domain bounds and active bounds within
the declared domain on all three axes. Allocated memory may contain halos
outside the domain. No unproved WRF exclusive-end convention was introduced.
Tests cover reversed domains, lower/upper tile escapes on each axis and a
valid halo case. Thirteen focused tests pass. Replaying the actual timestep-1
raw pair produces the retained summary byte for byte:
`33dbe95367ea422120513f0d8a3f9396306a78de86f7e711422df81fc1a76018`.
Root and an independent evidence reviewer checked the focused fix.

## Other review results

- Component arithmetic, local cancellation, finite checks, permissions,
  coverage and rollback: no additional actionable defect in the declared
  prescribed-net-increment scope.
- Writer: every new assessment field participates in replay identity.
  Unreproducible contract assessments and nonfinite residuals are rejected
  before NetCDF creation. The new regression directly calls that validator;
  existing writer tests cover pre-I/O rejection. No new writer defect found.
- Claims and provenance: the source-442 producer replay and source-901 native
  execution remain separate; content equality is explicitly qualified.
  Original receipts and the 10-test frozen-source validation index are
  historical records and remain unchanged.

## Validation and remaining limits

The original focused Intel logs contain only a PASS line. They do not
independently record compiler invocation, version or scratch location. A
follow-up focused O0/O2 run passed and records these details separately; its results
are indexed in [the follow-up receipt](evidence/pr60_followup_team_audit_20261006.json).
The six selected Fortran/test inputs matched review HEAD303a4f2 before and
after the builds. Unrelated Python edits were present; no clean-worktree
claim is made. An initial O2 setup failure from a changed shell cwd is
preserved separately and excluded from test results.
No whole-unit-suite PASS is claimed. The broad suite remains partial because
its legacy child runners still use source-tree scratch.

The actual retained capture still has 33,617 nonfinite t+20 reflectivity cells,
all coinciding with positive rain mass and zero rain number. This correction
does not fix or approve that physical initialization. Negative call-entry
CCN origin, moment priors, independent source/boundary attribution, joint
optimality, BASE/HYDRO/COUPLED 0–60 minute response and forecast improvement
remain open. Graph freshness is structural navigation evidence only.
