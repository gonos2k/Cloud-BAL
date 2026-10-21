# PR98 face/cutoff final peer review — 2026-10-22

## Decision

**GO for the bounded diagnostic evidence package, with the stated scope limits.** No blocker remains for the v8 face/cutoff replay evidence after the manifest metadata correction. This is not scientific or physical approval: the reports correctly retain `physical_approval: FAIL_OPEN`, and the remaining full-tile signed residual is about −22,655 to −22,683 kg (roughly −22.7 tonnes), still open after these terms.

## Independent checks

- Reviewed the frozen observer, source preparer, reducer, manifest writer, public report, per-arm face manifests/reports, and Intel accumulator test evidence.
- SHA256 pins:
  - `tools/pr98_budget_face_observer.f90`: `3f9115383ed26687ae1b453c1431d8375d776a8b3b6f3c325667f7c52133ab11`
  - `tools/pr98_prepare_sed_observer.py`: `e70b3713a40a7bbf5ef87cf64afae1830c598d9a5ff024670bc36095b8f87551`
  - `tools/pr98_budget_faces.py`: `c41d003b17661fc95b8af10a93ecb8c9ae6ada54c493369ef8ebddfbde65f385`
  - `tools/pr98_face_manifest.py`: `ab341e777b3696a179f32e467521b19de74afcf799dbfbec065a52528efd4cd3`
  - `docs/PR98_T1_RESIDUAL_20261022.md`: `ea891026d8667f7ff9aab4682e6d7edfe137b4521d1d976de305caad339251cb`
  - `OFF_face_replay_manifest.json`: `a75ad0309fb03d3a34039790a6015cc3210b122d7d46ba737c0ef8f12b247717`
  - `HYDRO_face_replay_manifest.json`: `3262b1d4f7398e231c2e043a57823165205a4eb9352a51b617fdb239ca538753`
  - `COUPLED_face_replay_manifest.json`: `ac724dec0424c80e76fc3b791e7321e994828f0ba93dea7ca511918a20724efc`
  - Per-arm reduced face reports OFF/HYDRO/COUPLED: `7c2d485d6dc318d8003fbc426e864a4c9acf8ec25f19eea50c106fb6439a0b24`, `dafb1c94764ce80ce8fe8b6e299d07e1445715d3f67b412507cdf73514f7943e`, `e6a2739400f0b595897d327d3fb69ef9276e64598d563ed6cfa5d86beda63421`.
  - `face_accumulator_test_manifest.json`: `db8b868409d2d165d1d00b2561853bc9c818ea6cfa163dacf191e0a14b3e32a2`.
- Source-preparation provenance pins the original PR97 diagnostic source and exact prepared-source hash. The observer adds guarded read-only capture of accepted packets and pre/post donor/receiver stores; it does not alter KDM6 state or physics expressions. Build manifests bind the pinned Intel IFX/MPI-IFX profile and executable. The three v8 arm manifests use the same executable SHA.
- All three current face manifests omit `returncode` and `status`, record the observed `REPLAY COMPLETED FULL ACTIVE TILE` marker, and attest exact equality of all 17 returned fields plus XLAND. I checked these assertions in each manifest. The previous cutoff manifests contain a return code, but those are separate earlier provenance; they are not used as face-replay completion proof.
- Each arm’s rain and ice stage-row counts equal its full-tile face-summary counts (78,926 rain; 64,960 ice). The independent selected raw capture contains 312 records (78 ice, 117 graupel, 117 rain); selected graupel records have zero approved packet. Full-tile face summaries are rain and ice only: 3,078,114 rain and 2,533,440 ice records. The report distinguishes selected records from full-tile summaries.
- The O0/O2 focused Intel accumulator checks both return exactly `1.0` for the manufactured cancellation case. I reran `pytest -q tests/test_pr98_budget_faces.py tests/test_pr98_budget.py`: **13 passed**.
- The O0 full-tile run was stopped for runtime and is excluded from evidence. No forecast rerun was performed.

## Scope and interpretation

The face term is explicitly an accepted-packet/store discrepancy that includes REAL32 store representation and REAL64 compensated accumulation effects. It is not called pure rounding and is not inferred from endpoint fitting. The cutoff term remains a separate threshold-removal contribution. The combined full-tile face terms are small relative to the remaining open residual, and subtraction leaves approximately −22.7 tonnes across all arms. The document does not claim whole-call, native hybrid-water, energy, or total physical closure.

The face/cutoff artifacts are therefore suitable as bounded diagnostics and reproducibility evidence. They do not justify scientific approval of the added wind treatment or closure of the remaining budget.
