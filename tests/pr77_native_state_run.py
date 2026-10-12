#!/usr/bin/env python3
"""Compare KDM6-entry and host-startup gradual underflow on pinned native inputs."""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
import shutil
import sys

from pr76_native_fp_run import (checked_hash, compile_and_link, compile_profile,
                               sha256, verify_control_helper)
from pr77_native_state_transform import transform, transform_host_main


def check_startup_policy(trace: str, expected_threads: int) -> dict:
    rows = [row.split(',') for row in trace.splitlines()]
    stages = {"MAIN_STARTUP": [], "OMP_STARTUP_TEAM": []}
    for row in rows:
        if len(row) != 5 or row[0] != 'PR77_HOST_FP' or row[1] not in stages:
            raise ValueError("malformed host FP startup record")
        before, after, thread = int(row[2], 16), int(row[3], 16), int(row[4])
        if thread <= 0 or after != before & ~0x8040:
            raise ValueError("startup helper changed bits beyond FTZ/DAZ")
        stages[row[1]].append(thread)
    main = stages['MAIN_STARTUP']
    workers = stages['OMP_STARTUP_TEAM']
    if (len(main) != 1 or len(workers) != expected_threads
            or len(set(workers)) != expected_threads or main[0] not in workers):
        raise ValueError("main and complete startup OpenMP team were not observed")
    return {"main_thread": main[0], "startup_team_threads": sorted(workers),
            "expected_team_size": expected_threads, "only_ftz_daz_cleared": True}


def retain(repo: Path, case: Path, mode: str, source: Path) -> list[dict]:
    evidence = repo / "docs/evidence" / "pr77_native_state_20261012" / mode
    evidence.mkdir(parents=True, exist_ok=False)
    records = []
    for relative in ("compile/compile.log", "compile/main_compile.log",
                     "build/link/main/pr76_link.log", "run/candidate_run.log",
                     "run/rsl.error.0000", "run/pr77_native_species.raw",
                     "run/pr77_host_fp.raw", "run/pr76_thread_entry.raw",
                     "run/pr76_target_call.raw", "run/pr75_native_fp.raw"):
        original = case / relative
        if original.is_file():
            destination = evidence / original.name
            shutil.copy2(original, destination)
            records.append({"path": str(destination.relative_to(repo)),
                            "sha256": sha256(destination)})
    generated = case / "compile/module_mp_kdm6.f90"
    delta = evidence / "kdm6_source.diff"
    delta.write_text("".join(difflib.unified_diff(
        source.read_text().splitlines(keepends=True),
        generated.read_text().splitlines(keepends=True),
        fromfile="pinned_PR73_kdm6", tofile=f"{mode}/module_mp_kdm6.f90")))
    records.append({"path": str(delta.relative_to(repo)), "sha256": sha256(delta)})
    main_source = case / "compile/wrf.f90"
    if main_source.is_file():
        shutil.copy2(main_source, evidence / "wrf.f90")
        records.append({"path": str((evidence / 'wrf.f90').relative_to(repo)),
                        "sha256": sha256(main_source)})
    return records


def main() -> int:
    repo, ifx, icx, _, ifx_version, icx_version = compile_profile()
    work_root = Path(sys.argv[1]).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    pr73_path = repo / "docs/evidence/pr73_native_first_violation_20261008_attempt2/native_receipt.json"
    pr74_path = repo / "docs/evidence/pr74_shinhong_qni_driver_20261008.json"
    pr73 = json.loads(pr73_path.read_text())
    pr74 = json.loads(pr74_path.read_text())
    source = Path("/var/tmp/pr73_native_first_violation.x3bvfn/build/source/module_mp_kdm6.f90")
    archive = Path(pr74["profiles"]["O0"]["archive_path"])
    main_source = Path("/var/tmp/pr61_ccn_origin_20261006/hostcopy/main/wrf.f90")
    if sha256(main_source) != "1ed575364433b64749086edee3a64b317febefbac9eb1a8c72011d13a69627ca":
        raise ValueError("native main source differs from the retained host source")
    pins = {"pr73_receipt": pr73_path, "archive": Path(pr73["build_artifacts"]["archive_path"]),
            "kdm6_source": source, "native_archive_o0": archive,
            "driver_source": repo / "docs/evidence/pr74_actual_driver_instrumented.F",
            "shinhong_source": Path("/var/tmp/pr73_pbl_research/source_after/module_bl_shinhong_pr65.F")}
    for name, path in pins.items():
        checked_hash(name, path)
    main_copy = work_root / "wrf.f90"
    main_copy.write_text(transform_host_main(main_source.read_text()))
    helper_test = verify_control_helper(work_root, repo / "tests/pr76_native_fp_policy.c",
                                       repo / "tests/pr76_native_fp_policy_check.c", icx)
    flags = os.environ["PR76_FP_FLAGS"].splitlines()
    profiles = {}
    sys.path.insert(0, str(repo / "tools"))
    from pr74_common_moment_audit import audit_capture_files
    for mode, host in (("kdm6_entry_gradual", False), ("host_startup_plus_kdm6_gradual", True)):
        case = work_root / mode
        profile = compile_and_link(mode, case, gradual=True, source=source,
            archive_source=archive, pr73=pr73, pr74=pr74, flags=flags,
            ifx=ifx, icx=icx, repo=repo, source_transform=transform,
            host_main_source=main_copy if host else None, preprocess_source=True,
            openmp_observers=True)
        run = case / "run"
        for name in ("pr77_native_species.raw", "pr77_host_fp.raw"):
            path = run / name
            profile[name] = {"sha256": sha256(path), "text": path.read_text()} if path.is_file() else None
        if host:
            host_trace = profile["pr77_host_fp.raw"]
            if host_trace is None:
                raise ValueError("startup FP trace is missing")
            profile['startup_policy_check'] = check_startup_policy(
                host_trace['text'], int(os.environ['OMP_NUM_THREADS']))
        trace = run / "kdm6_first_call_pre.raw"
        geometry = run / "pr63_geometry.raw"
        if trace.is_file() and geometry.is_file():
            profile["pre_call_moment_audit"] = audit_capture_files(trace, geometry)
        profile["preserved_artifacts"] = retain(repo, case, mode, source)
        profiles[mode] = profile
        print(f"PR77_NATIVE_CASE {mode} {profile['run_exit_status']} {profile['first_failure_line']}", flush=True)
    if profiles["kdm6_entry_gradual"]["inputs"]["before"] != profiles["host_startup_plus_kdm6_gradual"]["inputs"]["before"]:
        raise ValueError("paired native runs have different input bytes")
    receipt = {
        "schema": "pr77_native_state_comparison_v1", "source_base": "9701ef23f04576d875508a0882d0e0af67282587",
        "scope": "copied O0 partialhost research; identical inputs; KDM6-entry policy in both arms; added rebuilt main/initial OpenMP team policy in treatment",
        "profiles": profiles, "helper_control_bit_test": helper_test,
        "toolchain": {"ifx_path": str(ifx), "ifx_version": ifx_version, "ifx_sha256": sha256(ifx),
                      "icx_path": str(icx), "icx_version": icx_version, "icx_sha256": sha256(icx)},
        "pins": {name: {"path": str(path), "sha256": sha256(path)} for name, path in pins.items()},
        "host_main_source": {"path": str(main_source), "sha256": sha256(main_source)},
        "harness": {name: sha256(repo / 'tests' / name) for name in
                    ('pr77_native_state_run.py', 'pr77_native_state_transform.py', 'pr76_native_fp_run.py',
                     'run_pr77_native_state.sh')},
        "input_preservation_passed": all(p["inputs"]["unchanged"] for p in profiles.values()),
        "main_and_initial_worker_team_observed": 'startup_policy_check' in profiles["host_startup_plus_kdm6_gradual"],
        "later_or_external_threads_policy_assessed": False,
        "native_candidate_accepted": False, "science_assessed": False,
        "limits": ["Later thread pools and external libraries may change FP state; no whole-host guarantee.",
                   "Both new arms explicitly preprocess copied .f90 sources with -fpp; historical PR76 .f90 compile omitted this option and executed both number-basis branches.",
                   "Both new KDM6 observers compile/link with -qopenmp for serialized logging; the retained physical source has no OpenMP directives.",
                   "Startup arm rebuilds main with the pinned O0/no-ftz/fpe0/OpenMP profile; its contrast does not isolate only the explicit FTZ/DAZ bit change.",
                   "Full-domain pretrace audit predicts violations; actual fatal coordinates require the runtime observer.",
                   "The spatial estimator fixture and native inputs are separate candidates.",
                   "Inherited archive objects retain their earlier profiles; only copied KDM6 and optional main were compiled here."],
        "work_root": str(work_root),
    }
    output = repo / "docs/evidence/pr77_native_state_20261012.json"
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"PR77_NATIVE_RECEIPT {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
