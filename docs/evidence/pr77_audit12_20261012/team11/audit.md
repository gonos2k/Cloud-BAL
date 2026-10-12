# Cloud-BAL Team 11/12 test and portability audit

Date: 2026-10-12  
Source worktree: `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL`  
Base/source commit: `9701ef23f04576d875508a0882d0e0af67282587`  
Scope: read-only audit of PR77 test design, native diagnostic harness, validation claims, portability, hash closure, and relation to the existing Cloud-BAL graph. No tests were rerun and no project files were edited.

## Coverage map

| Layer | Current evidence | What it supports | What remains uncovered |
|---|---|---|---|
| Test-only source transforms | `tests/test_pr77_native_state_transform.py` (5 unittest methods); generated KDM6 and WRF-main fixtures; missing/duplicate-anchor rejection | Observer placement and main/startup insertion are checked against synthetic source strings; legacy checks remain present | Fixtures mirror the exact anchor text and do not semantically parse arbitrary Fortran or prove generated source is equivalent outside the tested anchors |
| Host-startup FP receipt | `tests/test_pr77_native_state_receipt.py` (2 cases); `check_startup_policy()` | Requires one main row, 68 unique startup thread IDs in native run, main membership, and clearing only MXCSR bits `0x8040`; rejects malformed/duplicate/incomplete rows | Unit fixture uses 2 threads; no negative injected native log/open failure; later thread pools and external libraries are explicitly outside scope |
| Native KDM6 diagnostic | `tests/run_pr77_native_state.sh`, `tests/pr77_native_state_run.py`, transformed copied KDM6 | Two O0 partial-host runs with byte-identical staged inputs; both use KDM6-entry gradual policy; treatment also rebuilds WRF main and initial OpenMP team; actual entry observer identifies first species-state rejection | Diagnostic rows are saved but not parsed/asserted by the runner. No fully rebuilt host, successful native initialization, completed first physical step, independent model-state oracle, or science acceptance |
| Shared helper / build path | Existing PR76 helper control test plus PR77 runner; pinned `ifx`; Intel `icx`; compilation in `/var/tmp` | Helper masks are tested; copied KDM6 source/object, optional main source/object, archive replacement, link argv/executable, inputs, and runtime traces are hashed or retained | C compiler is version-prefix checked and recorded but has no expected SHA/version gate. MPI env script, relevant dynamic-library environment, and runtime library identities are not receipt-pinned |
| Manufactured assessment endpoint | Existing PR77 common-inlet test and O0/O2 NetCDF writer/readback evidence described in `docs/PR77_INTEGRATION_PROGRESS_20261012.md` | Tests endpoint assessment and estimator serialization for a fixed small synthetic fixture | Does not establish independent meteorological authority, production by column/balance operators, canonical-validator acceptance, continuity, mass closure, or forecast improvement; canonical result is explicitly `UNBOUND/REJECTED` |
| CI / automation | `git ls-files` finds no workflow tracked in the PR77 target or maintained checkout. The PR77 target has no `.github/workflows/contract-ci.yml`. A separate maintained directory has an untracked workflow of that name; it runs pinned Python tests only. | No tracked CI coverage for PR77; the separate untracked workflow does not cover pinned Intel/native tests. | No CI gate is part of the PR77 target at audit time. |

## Findings

### Medium — observer evidence is not an automated assertion

`tests/pr77_native_state_run.py:102-117` reads and stores `pr77_native_species.raw`, then records run status and prints it. It does not parse `PR77_FIRST` or `PR77_COUNTS`, assert the expected entry stage/species/coordinates, or compare the observed first bad pair with the separate pretrace oracle. `retain()` hashes retained files, but hashing is not semantic validation. A missing or malformed species trace can therefore still produce a zero harness exit if compilation and receipt construction finish. The current human-reviewed receipt contains the expected observed row, so this is a coverage gap, not evidence that the recorded result is wrong.

Reproduction/check: inspect `tests/pr77_native_state_run.py:102-117` and `tests/pr77_native_state_transform.py:203-227`; compare the current receipt’s `profiles.kdm6_entry_gradual.pr77_native_species.raw.text` with the pretrace result. Next useful check is a parser/assertion that fails on absent or malformed rows and compares the reported first violation with an independent pretrace record.

### Interpretation — zero exit means evidence collection completed

`tests/pr77_native_state_run.py:117-147` prints each native exit/failure but returns 0 after receipt creation. This is intentional evidence collection: the shared runner records `physical_pass: False` (`tests/pr76_native_fp_run.py:261-268`), and PR77 sets `native_candidate_accepted` and `science_assessed` false (`tests/pr77_native_state_run.py:131-141`). It is not a validation pass or an implementation defect. It also does not enforce that expected failure signatures remain stable, so callers must treat exit 0 as completed collection only.

Reproduction/check: a changed runtime outcome is not rejected by `main()` unless an unrelated assertion fails. If this harness is used as a regression gate, assert its explicit expected status/trace and label the harness result as evidence collection rather than physics acceptance.

### Medium — native reproducibility record omits compiler/runtime environment pins

The shell runner sources the pinned `tests/intel_toolchain.sh`, then an external MPI setup script (`tests/run_pr77_native_state.sh:5-7`). The receipt hashes `ifx` and records `icx` version/hash, but `compile_profile()` accepts any `icx` banner beginning with the generic Intel compiler prefix (`tests/pr76_native_fp_run.py:39-52`). The receipt does not bind the MPI vars script, final `LD_LIBRARY_PATH`, or runtime shared-library identities (`tests/pr77_native_state_run.py:124-130`). Current evidence identifies the actual tool binaries and archive, but an equivalent rebuild on another installation is not fully closed by the receipt.

Reproduction/check: `tests/intel_toolchain.sh:33-63` pins `ifx` and runtime libraries; `tests/pr76_native_fp_run.py:42-51` only prefix-checks `icx`; `tests/run_pr77_native_state.sh:6-7` introduces the external MPI/runtime environment. Next useful check is to validate the expected `icx` SHA/version and retain hashes/values for the external environment script and linked runtime dependencies.

### Low — native unit tests use mirrored source fixtures

`tests/test_pr77_native_state_transform.py:11-45` synthesizes a KDM6 module by repeating the same anchor strings the transformer expects. This is useful for deterministic anchor/count checks, but it is not an independent semantic oracle. Actual copied-source compilation and runtime probes reduce this risk, while exact transformed source and binary hashes support review.

### No implementation defect found in audited observer placement

Against the pinned source, the observer call signatures match the entry, slope, and local validator arguments, the entry observer is inserted before the existing species validator, and observer calls precede the unchanged slope/local validators. Classification uses the already-existing `classify_species_state()` and state values 0–4 fit `counts(5,4)`. The observer is diagnostic only and does not repair input state. The generated-source tests remain limited as noted above.

## Outcome interpretation and open native/science gates

- Current receipt reports KDM6-entry gradual run exit 128, rejected for an ice number-only state at `(i, call_lat_index, k)=(104,2,1)`, mass `0`, internal number `4.2038792500161422e-36 m^-3`. This is an observed input-state rejection, not a successful native pass.
- Startup-plus-KDM6 arm aborts with Intel floating-invalid error 65 during host initialization before KDM6. Because the arm rebuilds main with O0/strict/`-fpe0`/OpenMP flags, that outcome is not causally isolated to the explicit FTZ/DAZ change.
- `PR77_COUNTS` describes classifications in the captured KDM6 entry slice (`i=2..233`, `k=1..39`, 9,048 cells per species across rain/cloud/ice/graupel). It is not a meteorological error rate or a count of completed physics calls. Separately, the same-call pretrace totals (299,933 number-only, 740 mass-only, 23,494 negative/invalid) are internal state-pair counts on the captured research input, not forecast-error statistics.
- The manufactured endpoint fixture is a narrow inlet/serialization test. Its canonical validator remains `UNBOUND`, `REJECTED`, and `science_assessed=false`; its result must not be represented as operational producer acceptance.
- Remaining work explicitly outside this test batch: valid spatial candidate with real observation/background authority, successful full native initialization and first call, same-carrier dry-mass/water/energy and cell/shared-face mass-wind closure, WPS/metgrid/real handoff, and fixed-setting BASE/HYDRO/COUPLED short-time response.

## Graphify evidence and extraction limits

Read the Graphify skill and its code-review workflow, then consulted the maintained `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/graphify-out/graph.json`: 8,542 nodes and 15,847 edges. Its 2026-10-08 report describes a selected PR76 overlay (`2f27b3fc680f5fad14b2efa2879ab5fddd5325f4`) against `fd7e1be37075a7ba80ee3a0be080111a5be03a26`; the maintained checkout HEAD is `f837bad0bdf1050a34975d93b178b7dee4420094`, separate from that selected extraction. It is not the local scratch graph, which is a smaller 1,499-node/3,094-edge September snapshot. The maintained report itself notes cluster-only stats, a combined history/overlay, partial cross-file Fortran CALL extraction, and external native source trees omitted. No graph update was run because this was a read-only audit. Graph freshness is navigation evidence, not runtime/scientific validation.

## Previously reported validation segments

The parent-provided validation record is preserved as segmented: the broad prefix reached only the LGT workspace-path failure; after repair the LGT test and original replay37/6 passed; the final source tail of original unit commands through qbal fixed72 compilation exited 0; and three path-only runner corrections were rechecked separately with exit 0. Earlier failures remain historical evidence and were not reclassified as open defects here. No full suite or native rerun was performed for this audit.
