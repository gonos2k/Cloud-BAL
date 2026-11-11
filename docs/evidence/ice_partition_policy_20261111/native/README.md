# Historical B1 short-start capture

The unchanged historical B1 `wrfinput_d01` and existing `wrf.exe` were run for 80 seconds with eight Intel MPI ranks and one OpenMP thread in fresh scratch directories. `tests/intel_toolchain.sh` and Intel MPI environment were sourced; no compiler was run. The five selected cells are those in the preceding ice-stage study. They are observations of historical B1, not acceptance of a newly initialized or policy-backed moment bundle, a physical fix, or a forecast test.

`file_values.json` holds raw REAL32 file-state values. `capturedsmallrecords/` retains the debugger's raw little-endian REAL32 words, values, indices, array pointers, rank and tile ownership for RK tendency and update boundaries, moist-physics preparation, and first KDM6 wrapper entry and return. The GDB script reads inferior memory and installs breakpoints; it never assigns model state. Species index collisions between moist and scalar arrays make index alone insufficient: `validate.py` binds each QI/QS/NI RK array to the first KDM6 array by base pointer, records moist/scalar selection, checks all three RK stages and unique ownership. The prep output density, TH, PII and full-pressure pointers bind the wrapper inputs. Derived TK is computed offline as REAL32 TH × PII, not a captured model variable.

`receipt.json` reports checks and raw values. A control and a GDB run used the same modified history interval of 80 s solely to write both initial and terminal histories. The two histories match byte for byte across arms; both arms have all eight success markers and their 89 staged input files retain their hashes. A separate initial 3600 s history-interval pair also succeeded with matching t=0 output. The t=0 historical output also matches the archived B1 history. Equal endpoint outputs do not prove all intermediate values were equal, nor do file-to-wrapper changes alone identify their cause.

The initial control attempt failed in file distribution with an 8 MB stack; the historical environment prescribes unlimited stack, and a fresh case with that setting passed. A subsequent wrapper path typo stopped before model launch. The failure records are in the external runtime directory, with hashes in `manifest.json`; neither is counted as a pass. Historical preprocessed sources and object/library association are documented by `cp02_initial_boundaries_20261105/native/source_lineage.json`; an independent original compile transcript has not been established. The 1,362 analytically empty NI intervals use file-estimated density; physical treatment and actual domain-wide first-use assessment remain open. The probe is limited to five cells and does not establish domain water or energy conservation, scientific skill, or operational acceptance.

## Fresh terminal-pair recipe

From the Cloud-BAL worktree, choose a new runtime directory that does not exist. The following commands stage both arms with the 80-second history interval, run them, and validate them without overwriting the preserved receipt:

```bash
task_runtime="$PWD/../native_replay_unique"
task_evidence="$PWD/docs/evidence/ice_partition_policy_20261111/native"
mkdir -p "$task_runtime"
python "$task_evidence/stage.py" "$task_runtime/control_terminal" --terminal
python "$task_evidence/stage.py" "$task_runtime/probe_terminal" --terminal
bash "$task_evidence/run_pair.sh" "$task_runtime"
mkdir "$task_runtime/evidence"
python "$task_evidence/file_capture.py" "$task_runtime/control_terminal/wrfinput_d01" "$task_runtime/evidence/file_values.json"
python "$task_evidence/validate.py" "$task_runtime" "$task_runtime/evidence"
```

The recipe requires the historical source case and Intel environment paths, eight available CPUs 48–55, enough working storage, and GDB. `stage.py` without `--terminal` retains the 3600-second historical interval. The terminal pair originally used the earlier staging script followed by a separate interval edit; the updated script was subsequently run only to stage a fresh reproduction. Its namelist is byte-identical to both completed terminal runs (SHA-256 `dca7bf8b9fc28b196877cb4d555f598b6b81745df8ecab83efb64da2ea392d2a`), and its complete staged-file hash inventory is identical to the control. The updated run script's configurable runtime directory is a later reproducibility improvement; it was not used for the recorded WRF pair. No new WRF run is implied by this recipe check. The updated validator additionally confirms the three species' final RK update return words equal first KDM6 entry words for all five cells (15 comparisons).
