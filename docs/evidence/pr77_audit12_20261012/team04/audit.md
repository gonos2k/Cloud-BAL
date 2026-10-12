# Team04/12 — Cloud-BAL PR77 native FP build and runtime audit

Date: 2026-10-12  
Target: `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL`, source base `9701ef23f04576d875508a0882d0e0af67282587`  
Scope: read-only review of PR75/76/77 native transforms and runners, C MXCSR helper, pinned Intel profile, archive replacement and selection, Fortran preprocessing, OpenMP startup instrumentation, and run/receipt evidence. No rebuild or broad regression run was performed by this auditor.

## Evidence limitation — startup rows show idempotent no-op; no call-bound result

**Priority: P1 interpretation/evidence limit. Category: missing evidence.**

`tests/pr77_native_state_run.py:24-26` validates the desired postcondition and exact preservation outside FTZ/DAZ. Accepting already-clear bits is correct for this idempotent policy. The compiled startup main uses the pinned `-no-ftz` profile, so the observed clear-before/clear-after state is expected; it is not a checker defect.

The retained startup run shows the main row at `0x00001920` and workers at `0x00001900`, with all 68 unique worker IDs plus the main membership observed and every row unchanged. Thus this run documents team coverage and an already-satisfied state; it does not show a direct startup bit-toggle intervention. The separate Intel C control check proves the helper clears both bits when set (`0x0000DFFF -> 0x00005FBF`). The KDM6-entry arm also observes a live transition (`0x00009FFD -> 0x00001FBD`).

The `host_startup_plus_kdm6_gradual` arm exits `-6` with `forrtl: error (65): floating invalid` during `start_domain_em`, before KDM6. Its pretrace and driver capture are absent, and receipt call-binding fields are false. The arm therefore establishes no startup effect at KDM6 or downstream physics. The rebuilt main adds the pinned O0, `-fpe0`, `-no-ftz`, OpenMP profile (`tests/pr76_native_fp_run.py:118-132`), an acknowledged confound for FTZ-only causal attribution. Keep the recorded result scoped to initial startup observations and an initialization-time rejection.

## Open policy — later and external thread state

**Priority: P2 follow-up. Category: open policy.**

The receipt explicitly sets `later_or_external_threads_policy_assessed: false` and notes that later thread pools or external libraries may change FP state. Startup coverage is limited to the main thread and its initial 68-thread OpenMP team before `wrf_init`; it does not establish a whole-host guarantee. Next check, if this becomes a runtime policy requirement: observe FP state at the relevant later thread-pool creation and at the KDM6 call, then define whether the policy must be reapplied there.

## Missing portable native build closure

**Priority: P2 reproducibility. Category: missing portable build closure.**

The receipt pins compiler binaries and inputs by hash and records source/object/archive/executable hashes, arguments, outputs, and work root. However, critical build inputs are resolved through ephemeral `/var/tmp` paths (`tests/pr77_native_state_run.py:71-83`; paths are retained in the receipt). A clean-host rerun requires those external PR73/PR74 artifacts and source trees to remain available. Selected logs, transformed source diff, and main source are copied into repository evidence (`:37-64`), while the full inherited archive, complete scratch tree, and executable are not retained there. This is a portability/archival gap; it does not invalidate the captured run.

## Verified implementation/evidence

- The Intel profile is pinned in `tests/intel_toolchain.sh:9-63`: setvars hash, ifx version/hash, and Intel runtime hashes are checked; flags include strict FP, `-fpe0`, `-no-ftz`, and O0 (`:65-77`). The PR77 shell runner sources this profile and fixes `OMP_NUM_THREADS=68`, `OMP_DYNAMIC=FALSE`, stack limit, and a unique `/var/tmp` work root (`tests/run_pr77_native_state.sh:3-19`).
- The repaired runner explicitly adds `-fpp` to copied `.f90` KDM6 compilation and `-qopenmp` for synchronized observers (`tests/pr76_native_fp_run.py:98-109`). The main transformation places the main-thread operation and an OpenMP startup-team operation before `wrf_init` (`tests/pr77_native_state_transform.py:66-102`). The retained receipt records all 68 unique workers including main; this establishes those initial rows only.
- Archive provenance is bound to the PR74 incoming archive hash, and replacement is confined to the copied scratch archive. The runner checks exactly one selected member for each replacement object and byte-compares each member with its object (`tests/pr76_native_fp_run.py:134-150`), then verifies the inherited link argv selects that archive and differs only by output path plus the recorded OpenMP link flag (`:152-170`). Receipt records archive before/after hashes and executable hash.
- Run status and failure capture preserve negative signal status, inspect both `rsl.error.0000` and stdout/stderr-combined run log for `forrtl: error`, and capture text/hash tails (`tests/pr76_native_fp_run.py:187-237, 307-313`). The retained KDM6-entry arm is bound to the PR74 pretrace and driver capture by identical hashes; it reports the first native orphan state and exits 128. Input hashes remained unchanged in both arms.
- C helper logic only masks FTZ/DAZ (`tests/pr76_native_fp_policy.c:6-25`); the isolated Intel C control test forces those bits and verifies all other MXCSR bits remain unchanged (`tests/pr76_native_fp_policy_check.c:7-29`).

## Graphify navigation and extraction limits

Graphify navigation used the maintained absolute graph at `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/graphify-out/graph.json`. Its report is dated 2026-10-08 and contains 8,542 nodes and 15,847 edges. Freshness metadata identifies a selected PR76 overlay (`2f27b3fc680f5fad14b2efa2879ab5fddd5325f4`) against base (`fd7e1be37075a7ba80ee3a0be080111a5be03a26`); a `git_sha` field is not itself extraction identity. The graph query surfaced the PR75/76 runner, helper, Intel profile, and prior closure evidence. It predates the PR77 batch, so manual source and receipt inspection provides source proof for PR77.

The report says the persistent graph combines earlier snapshots and selected overlays, is not a full extraction of the candidate tree, has partial cross-file Fortran `CALL` extraction, and excludes external WRF source trees. Freshness is navigation evidence, not runtime or scientific validation. No graph refresh was run because this was a read-only audit.

## Disposition and coverage

No concrete defect was found in the C mask operation, pinned compiler gate, isolated archive replacement/member checks, link selection, or error capture. Already-clear startup bits are expected idempotent behavior. Open items are the unobserved later/external thread FP state, the startup arm’s pre-KDM6 failure, and portable closure of the native build inputs. Scientific acceptance remains open.

Coverage includes the named PR75/76/77 runner/transforms and tests, C helper/control, Intel profile, archive/link, preprocessing, startup observer, receipt, and retained native artifacts. Excluded: source implementation/scientific correctness outside observer/runner behavior, whole-host FP state after startup, external library threads, independent native rerun, and broad regression suite. No extra tests were run.
