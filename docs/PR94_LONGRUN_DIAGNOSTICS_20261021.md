# PR94 Long-Run Diagnostics Profile — 2026-10-21

## Scope

This note records preparation of a compact PR85 observer profile for the frozen PR93-C4 OFF and COUPLED stability extension. The HYDRO 600-second control uses the original C4 executable separately. The intended model durations are 1800 seconds and 3600 seconds at the existing 20-second timestep. The PR85 completed-state observer must still write `POST_KDM6` at every timestep; full state and PBL tendency records are retained through step 30 (600 seconds), then at steps 60, 90, and 180 when within the requested duration.

## Observer identity and manufactured validation

The baseline observer remains at `tools/pr85_joint_stage_observer.f90`, SHA-256 `ea50fe2b380d2d5572da42f97261afe19eabdfef194edbfa5e4abc6360ee33bb`. The generated sources are:

- `docs/evidence/pr94_longrun_diagnostics_20261021/observer_1800.f90`, SHA-256 `4892de2a3d0019e379e323f61406745faa74358d18cdccae4df6957eab392ea2`
- `docs/evidence/pr94_longrun_diagnostics_20261021/observer_3600.f90`, SHA-256 `d04edb3747df3057762be1fe013ce9bdcf09e14e6a974e4e8bc2daa3e2dea1b3`
- Validation manifest: `docs/evidence/pr94_longrun_diagnostics_20261021/observer_validation.json`, SHA-256 `7899f5a0b64e0ecb0c55758f9f645966d38d53e3be5c50b1a58a9006e4b43127`

The source generator pins the baseline observer hash and changes only the two observer output blocks. Existing dry-density calculations and fatal validation run before the output gates. The manufactured 2×2×2 driver called six state stages and one PBL tendency record for steps 1–180. It was compiled with the pinned Intel profile at O0 and O2 for the baseline and both generated sources. All retained records matched their corresponding baseline bytes; each compact output had a byte-identical 600-second prefix. Invalid `AL+ALB` retained the existing fatal message and nonzero exit in every build.

These results validate the generated observer code with a manufactured driver. They do not establish that the full WRF executable is physically unaffected; the gates change only whether observer files are written after the density validation. The full executable must be built with the recorded C4 object set and the selected generated observer before any long run.

## Closed-run audit

`tools/pr94_longrun_audit.py` reuses the pinned frozen PR93 closed-receipt reader, trace reader, completion-prefix derivation, generic completed-state predicates, exact endpoint predicates, and active-ice policy split. The compact OFF/COUPLED audit requires six observer states at every completed step through step 30, plus at completed steps 60, 90, and 180; every other completed step must retain exactly one `POST_KDM6`. It stores only each state’s timestep/stage/RK metadata after immediately evaluating its native arrays. It compares the common first-600-second prefix against the matching closed C4 arm, including metadata and field-array bytes, while streaming both full traces to EOF to verify their receipt-bound compressed and expanded identities. PBL record contents contribute to those full-trace hashes, but the frozen reader does not yield or count PBL records; the report says so explicitly.

Before interpreting a trace, the utility checks the finalized run preflights and receipts against the pinned PR94 source/build audit: the baseline executed executable must be frozen C4 (`20aaa605…e44be`), and the compact run must use the reviewed observer overlay (`3eea34b7…27641bac`). It also requires identical same-arm input hash maps, `wrfinput`, boundary, and source namelist identities. It regenerates the expected baseline and compact namelists from the shared source with the existing runner duration/end-time/history edits, so all other namelist settings must match. HYDRO is excluded because its 600-second C4 run does not use the compact overlay profile.

If a finalized compact run ends before 600 seconds, the audit compares the available completed common prefix, drains both traces for whole-file identity checks, and marks the prefix and requested duration `INCOMPLETE`; it does not call a partial prefix a 600-second pass. Generic, exact-source-endpoint, and active-ice predicate outcomes are findings reported separately. They do not change procedural audit completion, since a retained predicate failure can also be present in the frozen C4 baseline. The CLI exits successfully only for a complete requested duration with a valid profile, full first-600-second match, and passing runtime identity checks; predicate findings remain separate in the report.

Focused manufactured-record tests exercise missing/extra/wrong-RK profile records, metadata-only retention, wrong executable identity, a changed prefix array value, and an incomplete three-step prefix. No closed longrun has been audited by this utility yet; it reads only finalized receipts and closed output files, never a live binary trace.

## Runtime source and input scope

The completed overlay replaces only the parent PR85 observer object with the generated observer object. The frozen PR93-C4 KDM6 and other physics object sources, the nine selected C4 source overrides, and the existing PR90 cycle-support extra object remain separately pinned by the overlay build receipt. The HYDRO case uses its source-bound `wrfinput_d01` receipt and the same matched boundary as OFF/COUPLED; the OFF template remains an ancillary runtime template. The runner’s HYDRO receipt binding, cross-filesystem staging fallback, and duration/snapshot support passed independent review. The [source/build audit](evidence/pr94_longrun_diagnostics_20261021/source_build_audit.json) binds the completed pinned-Intel partial overlay. Preprocessed physics bodies match C4 after removing only CPP line markers; this does not prove full native prefix equality.

## Runtime status

One 3600-second request for each OFF and COUPLED arm has been launched, including the 1800-second checkpoint. At launch, both disk guards passed and WRF entered initialization. The requests are **RUNNING**, not COMPLETE. Neither duration is yet a closed validated result. No full-model physics validation or scientific conclusion follows from launch. The intended selected states are 600, 1200, 1800, and 3600 seconds, bounded by each run’s requested duration. Any later runtime report must bind the executable, C4 source overrides, observer source/object, HYDRO input receipt where applicable, run inputs, stage trace, and generated history artifacts.
