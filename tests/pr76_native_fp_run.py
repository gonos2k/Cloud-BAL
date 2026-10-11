#!/usr/bin/env python3
"""Run paired PR75 baseline and FTZ/DAZ-only KDM6-entry policy experiments."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import difflib
from pathlib import Path

from pr76_native_fp_transform import transform


EXPECTED = {
    "pr73_receipt": "5be57e83f5ebe8e7124e4f9d5bb7ab527bdf4ae495ff19a9b1bd4e532a10a355",
    "archive": "b6cb181e2016b10b7ccd1b040308eecee4e8cbbdb54ffc87473bc2cb05da4dbd",
    "kdm6_source": "1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819",
    "driver_source": "342378285d929d06aa88b3c47b27c906bac05e560244162e4f946481ea4bd322",
    "shinhong_source": "5fbe821bb3b82e406fee459e5b2d745156ea1a030b5f0ecd2c7191025f296553",
    "native_archive_o0": "3ddba2be0e657b3e5717f867d81805b73e5a15c3583bcbdcfc06de46802a6083",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_hash(name: str, path: Path) -> str:
    actual = sha256(path)
    if actual != EXPECTED[name]:
        raise SystemExit(f"{name} hash differs from pinned PR74 evidence: {path}")
    return actual


def compile_profile() -> tuple[Path, Path, Path, Path, str, str]:
    repo = Path(__file__).resolve().parents[1]
    ifx = Path(os.environ["CLOUD_BAL_FC"]).resolve()
    icx = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/icx")
    tool_dir = ifx.parent
    ifx_version = subprocess.run([str(ifx), "--version"], check=True, text=True,
                                 capture_output=True).stdout.splitlines()[0]
    icx_version = subprocess.run([str(icx), "--version"], check=True, text=True,
                                 capture_output=True).stdout.splitlines()[0]
    if not ifx_version.startswith("ifx (IFX) 2026.0.0 20260331"):
        raise SystemExit(f"unexpected pinned Fortran compiler: {ifx_version}")
    if not icx_version.startswith("Intel(R) oneAPI DPC++/C++ Compiler"):
        raise SystemExit(f"unexpected Intel C compiler: {icx_version}")
    return repo, ifx, icx, tool_dir, ifx_version, icx_version


def verify_control_helper(work_root: Path, helper: Path, check: Path, icx: Path) -> dict:
    check_dir = work_root / "helper_control_check"
    check_dir.mkdir(parents=True, exist_ok=True)
    executable = check_dir / "policy_check"
    argv = [str(icx), "-O0", str(helper), str(check), "-o", str(executable)]
    log = check_dir / "helper_check.log"
    with log.open("wb") as output:
        subprocess.run(argv, cwd=check_dir, check=True,
                       stdout=output, stderr=subprocess.STDOUT)
    result = subprocess.run([str(executable)], cwd=check_dir, check=True,
                            text=True, capture_output=True)
    if "MXCSR_POLICY_OK" not in result.stdout:
        raise SystemExit(f"MXCSR helper preservation check produced unexpected output: {result.stdout}")
    return {"passed": True, "compile_argv": argv, "run_argv": [str(executable)],
            "stdout": result.stdout.strip(), "executable_sha256": sha256(executable),
            "helper_sha256": sha256(helper), "check_source_sha256": sha256(check)}


def compile_and_link(mode: str, case: Path, *, gradual: bool,
                     source: Path, archive_source: Path, pr73: dict,
                     pr74: dict, flags: list[str], ifx: Path, icx: Path,
                     repo: Path) -> dict:
    compile_dir = case / "compile"
    link_dir = case / "build/link/main"
    run_dir = case / "run"
    compile_dir.mkdir(parents=True)
    link_dir.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    shutil.copytree(archive_source.parent, link_dir, dirs_exist_ok=True,
                    copy_function=shutil.copy2)
    archive = link_dir / archive_source.name
    source_copy = compile_dir / "module_mp_kdm6.f90"
    source_copy.write_text(transform(source.read_text(), gradual=gradual))
    helper = repo / "tests/pr76_native_fp_policy.c"
    helper_copy = compile_dir / helper.name
    shutil.copy2(helper, helper_copy)

    include_args = ["-I/var/tmp/pr61_ccn_origin_20261006/hostcopy/phys",
                    "-I/var/tmp/pr61_ccn_origin_20261006/hostcopy/frame"]
    compile_argv = [str(ifx), *flags, "-convert", "big_endian", *include_args,
                    "-free", "-c", str(source_copy)]
    pinned_compile_argv = pr73["build_artifacts"]["compile_argv"]
    if compile_argv[:compile_argv.index("-c")] != pinned_compile_argv[:pinned_compile_argv.index("-c")]:
        raise SystemExit("KDM6 compile options differ from pinned O0 options")
    helper_object = compile_dir / "pr76_native_fp_policy.o"
    c_compile_argv = [str(icx), "-O0", "-c", str(helper_copy), "-o", str(helper_object)]
    with (compile_dir / "compile.log").open("wb") as log:
        subprocess.run(compile_argv, cwd=compile_dir, check=True,
                       stdout=log, stderr=subprocess.STDOUT)
        subprocess.run(c_compile_argv, cwd=compile_dir, check=True,
                       stdout=log, stderr=subprocess.STDOUT)

    archive_before = sha256(archive)
    subprocess.run(["/usr/bin/ar", "r", str(archive),
                    str(compile_dir / "module_mp_kdm6.o"), str(helper_object)],
                   check=True, cwd=link_dir)
    members = subprocess.run(["/usr/bin/ar", "t", str(archive)], check=True,
                             cwd=link_dir, text=True, capture_output=True).stdout.splitlines()
    object_hashes = {}
    for member, object_path in (("module_mp_kdm6.o", compile_dir / "module_mp_kdm6.o"),
                                ("pr76_native_fp_policy.o", helper_object)):
        if members.count(member) != 1:
            raise SystemExit(f"archive member count mismatch: {member}")
        member_bytes = subprocess.run(["/usr/bin/ar", "p", str(archive), member],
                                      check=True, cwd=link_dir,
                                      capture_output=True).stdout
        if hashlib.sha256(member_bytes).hexdigest() != sha256(object_path):
            raise SystemExit(f"archive member bytes differ: {member}")
        object_hashes[member] = sha256(object_path)

    link_argv = list(pr74["profiles"]["O0"]["actual_link"]["argv"])
    inherited = list(link_argv)
    old_output = link_argv[2]
    executable = case / "wrf.exe"
    link_argv[link_argv.index(old_output)] = str(executable)
    normalized = list(link_argv)
    normalized[normalized.index(str(executable))] = old_output
    if normalized != inherited:
        raise SystemExit("link argv changed beyond the scratch executable path")
    if not any(Path(item).name == archive.name and (link_dir / item).resolve() == archive.resolve()
               for item in link_argv):
        raise SystemExit("diagnostic archive is not selected by inherited link argv")
    with (link_dir / "pr76_link.log").open("wb") as log:
        subprocess.run(link_argv, cwd=link_dir, check=True,
                       stdout=log, stderr=subprocess.STDOUT)

    input_before = {}
    for entry in pr73["input_hashes_before_after"]:
        original = Path(entry["path"])
        if original.name == "wrf.exe":
            continue
        if sha256(original) != entry["sha256_before"]:
            raise SystemExit(f"protected model input changed: {original.name}")
        target = run_dir / original.name
        if target.name in input_before:
            raise SystemExit(f"duplicate staged input basename: {target.name}")
        shutil.copy2(original, target)
        input_before[target.name] = sha256(target)
    shutil.copy2(executable, run_dir / "wrf.exe")
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "68"
    raw_log = run_dir / "candidate_run.log"
    with raw_log.open("wb") as log:
        try:
            process = subprocess.run([str(run_dir / "wrf.exe")], cwd=run_dir,
                                     env=env, stdout=log, stderr=subprocess.STDOUT,
                                     timeout=900)
            status: int | str = process.returncode
        except subprocess.TimeoutExpired:
            status = "TIMEOUT_900S"

    input_after = {name: sha256(run_dir / name) for name in input_before}
    diag = run_dir / "pr75_native_fp.raw"
    entry_trace = run_dir / "pr76_thread_entry.raw"
    target_call_path = run_dir / "pr76_target_call.raw"
    pretrace = run_dir / "kdm6_first_call_pre.raw"
    driver_capture = run_dir / "pr74_qni_driver.raw"
    rsl_error = run_dir / "rsl.error.0000"
    log_text = raw_log.read_text(errors="replace")
    diagnostic_text = diag.read_text(errors="replace") if diag.is_file() else None
    native_failure = None
    if diagnostic_text:
        rows = [line.split(",") for line in diagnostic_text.splitlines()]
        if len(rows) >= 3 and rows[0][0] == "NI_ADAPTER_FAILURE":
            before = int(rows[1][1], 16)
            after = int(rows[1][2], 16)
            native_failure = {
                "i": int(rows[0][1]), "call_lat_index": int(rows[0][2]),
                "k": int(rows[0][3]), "j_semantics": "wrapper call_lat_index; global-j mapping unclaimed",
                "public_ni_binary32": rows[1][3], "dry_density_binary32": rows[1][4],
                "converted_ni_binary32": rows[1][5], "conversion_valid": rows[0][7].strip().upper() == "T",
                "mxcsr_before": f"0x{before:08X}", "mxcsr_after": f"0x{after:08X}",
                "ftz_before": bool(before & (1 << 15)), "daz_before": bool(before & (1 << 6)),
                "thread_id_before": int(rows[1][6], 16), "thread_id_after": int(rows[2][1]),
                "same_thread": int(rows[1][6], 16) == int(rows[2][1]),
            }
    outputs = sorted(path.name for path in run_dir.glob("wrfout*") if path.is_file())
    outputs += sorted(path.name for path in run_dir.glob("wrfrst*") if path.is_file())
    required_post_call_outputs = pr74["profiles"]["O0"]["required_post_call_outputs"]
    missing_post_call_outputs = [name for name in required_post_call_outputs
                                 if not (run_dir / name).is_file()]
    failure_markers = ("kdm6 invalid ", "kdm6 orphan ", "error stop", "fatal")
    failure_sources = [("rsl.error.0000", rsl_error.read_text(errors="replace") if rsl_error.is_file() else ""),
                       ("candidate_run.log", log_text)]
    first_failure_source = None
    first_failure = None
    for failure_source, failure_text in failure_sources:
        first_failure = next((line.strip() for line in failure_text.splitlines()
                              if any(marker in line.lower() for marker in failure_markers)), None)
        if first_failure:
            first_failure_source = failure_source
            break
    target_call = None
    if target_call_path.is_file():
        rows = [line.split(",") for line in target_call_path.read_text().splitlines()]
        if len(rows) >= 4 and rows[0][0] == "TARGET_CALL":
            mxcsr_before = int(rows[1][1], 16)
            mxcsr_after = int(rows[1][2], 16)
            entry_rows = entry_trace.read_text().splitlines() if entry_trace.is_file() else []
            entry = entry_rows[0].split(",") if entry_rows else None
            target_call = {
                "i": int(rows[0][1]), "call_lat_index": int(rows[0][2]), "k": int(rows[0][3]),
                "j_semantics": "wrapper call_lat_index; global-j mapping unclaimed",
                "public_ni": float(rows[0][4]), "dry_density": float(rows[0][5]),
                "converted_ni": float(rows[0][6]), "conversion_valid": rows[0][7].strip().upper() == "T",
                "public_ni_binary32": rows[1][3], "dry_density_binary32": rows[1][4],
                "converted_ni_binary32": rows[2][1],
                "mxcsr_before": f"0x{mxcsr_before:08X}", "mxcsr_after": f"0x{mxcsr_after:08X}",
                "ftz_before": bool(mxcsr_before & (1 << 15)), "daz_before": bool(mxcsr_before & (1 << 6)),
                "thread_id_before": int(rows[3][1]), "thread_id_after": int(rows[3][2]),
                "same_thread": int(rows[3][1]) == int(rows[3][2]),
                "same_thread_as_kdm6_entry": (int(rows[3][1]) == int(entry[3])) if entry else None,
                "entry_mxcsr_before": entry[1] if entry else None,
                "entry_mxcsr_after": entry[2] if entry else None,
            }
    return {
        "mode": mode, "gradual_policy_at_kdm6_entry": gradual,
        "run_exit_status": status, "first_failure_line": first_failure,
        "first_failure_source": first_failure_source,
        "physical_output_files": outputs,
        "physical_pass": False,
        "required_post_call_outputs": required_post_call_outputs,
        "missing_post_call_outputs": missing_post_call_outputs,
        "sources": {"transformed_source_sha256": sha256(source_copy),
                    "helper_sha256": sha256(helper_copy),
                    "helper_object_sha256": object_hashes["pr76_native_fp_policy.o"],
                    "transformed_object_sha256": object_hashes["module_mp_kdm6.o"]},
        "toolchain": {"ifx_compile_argv": compile_argv, "icx_compile_argv": c_compile_argv,
                      "compile_prefix_matches_pinned": True},
        "archive": {"incoming_path": str(archive_source),
                    "incoming_sha256": sha256(archive_source),
                    "scratch_sha256_before_replace": archive_before,
                    "scratch_sha256_after_replace": sha256(archive),
                    "incoming_unchanged": sha256(archive_source) == EXPECTED["native_archive_o0"]},
        "link": {"argv": link_argv, "non_output_arguments_unchanged": True,
                 "inherited_ftz_flags": [x for x in link_argv if x in ("-ftz", "-no-ftz")],
                 "executable_sha256": sha256(executable)},
        "inputs": {"count": len(input_before), "before": input_before, "after": input_after,
                   "unchanged": input_before == input_after},
        "call_binding": {
            "pr74_reference_pretrace_sha256": pr74["profiles"]["O0"]["first_call_pretrace_sha256"],
            "run_pretrace_sha256": sha256(pretrace) if pretrace.is_file() else None,
            "pretrace_matches": pretrace.is_file() and sha256(pretrace) == pr74["profiles"]["O0"]["first_call_pretrace_sha256"],
            "pr74_reference_driver_capture_sha256": sha256(Path(pr74["profiles"]["O0"]["driver_capture_path"])),
            "run_driver_capture_sha256": sha256(driver_capture) if driver_capture.is_file() else None,
            "driver_capture_matches": driver_capture.is_file() and sha256(driver_capture) ==
                                      sha256(Path(pr74["profiles"]["O0"]["driver_capture_path"])),
        },
        "policy_entry_trace": {
            "path": str(entry_trace) if gradual else None,
            "sha256": sha256(entry_trace) if entry_trace.is_file() else None,
            "text": entry_trace.read_text(errors="replace") if entry_trace.is_file() else None,
        },
        "target_call": {"path": str(target_call_path) if target_call_path.is_file() else None,
                        "sha256": sha256(target_call_path) if target_call_path.is_file() else None,
                        "record": target_call},
        "observations": {"adapter_failure": native_failure,
                         "adapter_diagnostic_sha256": sha256(diag) if diag.is_file() else None,
                         "adapter_diagnostic_text": diagnostic_text,
                         "rsl_error_sha256": sha256(rsl_error) if rsl_error.is_file() else None,
                         "rsl_error_tail": rsl_error.read_text(errors="replace")[-2500:] if rsl_error.is_file() else None,
                         "run_log_sha256": sha256(raw_log), "run_log_tail": log_text[-6000:]},
        "scratch_case": str(case),
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    work_root = Path(sys.argv[1]).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    pr73_path = repo / "docs/evidence/pr73_native_first_violation_20261008_attempt2/native_receipt.json"
    pr74_path = repo / "docs/evidence/pr74_shinhong_qni_driver_20261008.json"
    pr73 = json.loads(pr73_path.read_text())
    pr74 = json.loads(pr74_path.read_text())
    source = Path("/var/tmp/pr73_native_first_violation.x3bvfn/build/source/module_mp_kdm6.f90")
    archive = Path(pr74["profiles"]["O0"]["archive_path"])
    driver = repo / "docs/evidence/pr74_actual_driver_instrumented.F"
    shinhong = Path("/var/tmp/pr73_pbl_research/source_after/module_bl_shinhong_pr65.F")
    checked_hash("pr73_receipt", pr73_path)
    checked_hash("archive", Path(pr73["build_artifacts"]["archive_path"]))
    checked_hash("kdm6_source", source)
    checked_hash("driver_source", driver)
    checked_hash("shinhong_source", shinhong)
    checked_hash("native_archive_o0", archive)
    if sha256(archive) != pr74["profiles"]["O0"]["archive_sha256"]:
        raise SystemExit("incoming O0 archive differs from PR74 receipt")

    _, ifx, icx, _, ifx_version, icx_version = compile_profile()
    helper_test = verify_control_helper(work_root,
        repo / "tests/pr76_native_fp_policy.c",
        repo / "tests/pr76_native_fp_policy_check.c", icx)
    flags = [line for line in os.environ["PR76_FP_FLAGS"].split("\n") if line]
    profiles = {}
    for mode, gradual in (("baseline_ftz_daz", False), ("kdm6_entry_gradual", True)):
        profiles[mode] = compile_and_link(mode, work_root / mode, gradual=gradual,
                                         source=source, archive_source=archive,
                                         pr73=pr73, pr74=pr74, flags=flags,
                                         ifx=ifx, icx=icx, repo=repo)
    for mode, profile in profiles.items():
        case = Path(profile["scratch_case"])
        run_dir = case / "run"
        evidence = repo / "docs/evidence"
        artifacts = []
        source_copy = case / "compile/module_mp_kdm6.f90"
        source_diff = evidence / f"pr76_native_fp_{mode}_source.diff"
        delta = difflib.unified_diff(
            source.read_text().splitlines(keepends=True),
            source_copy.read_text().splitlines(keepends=True),
            fromfile=str(source), tofile=f"{mode}/module_mp_kdm6.f90",
        )
        source_diff.write_text("".join(delta))
        artifacts.append({"kind": "source_delta", "path": str(source_diff.relative_to(repo)),
                          "sha256": sha256(source_diff)})
        retained = (
            (case / "compile/compile.log", "compiler.raw", "compiler_log"),
            (case / "build/link/main/pr76_link.log", "linker.raw", "link_log"),
            (run_dir / "candidate_run.log", "stdout.raw", "run_stdout_log"),
            (run_dir / "rsl.error.0000", "rsl.error", "rsl_error_log"),
            (run_dir / "pr75_native_fp.raw", "adapter.raw", "adapter_trace"),
            (run_dir / "pr76_thread_entry.raw", "entry.raw", "entry_trace"),
            (run_dir / "pr76_target_call.raw", "target_call.raw", "target_call_trace"),
            (run_dir / "pr74_qni_driver.raw", "driver.raw", "driver_capture"),
        )
        for source_path, suffix, kind in retained:
            if source_path.is_file():
                target = evidence / f"pr76_native_fp_{mode}_{suffix}"
                shutil.copy2(source_path, target)
                artifacts.append({"kind": kind, "path": str(target.relative_to(repo)),
                                  "sha256": sha256(target)})
        profile["preserved_artifacts"] = artifacts
    prior_attempt_path = repo / "docs/evidence/pr76_native_fp_policy_first_attempt_20261008.json"
    prior_attempt = json.loads(prior_attempt_path.read_text())
    prior_artifacts = []
    for mode, prior_profile in prior_attempt["profiles"].items():
        prior_case = Path(prior_profile["scratch_case"])
        prior_run = prior_case / "run"
        retained = (
            (prior_case / "compile/compile.log", "compiler.raw", "compiler_log"),
            (prior_case / "build/link/main/pr76_link.log", "linker.raw", "link_log"),
            (prior_run / "candidate_run.log", "stdout.raw", "run_stdout_log"),
            (prior_run / "rsl.error.0000", "rsl.error", "rsl_error_log"),
            (prior_run / "pr75_native_fp.raw", "adapter.raw", "adapter_trace"),
            (prior_run / "pr76_thread_entry.raw", "entry.raw", "entry_trace"),
        )
        for source_path, suffix, kind in retained:
            if source_path.is_file():
                target = repo / "docs/evidence" / f"pr76_native_fp_first_attempt_{mode}_{suffix}"
                shutil.copy2(source_path, target)
                prior_artifacts.append({"kind": kind, "path": str(target.relative_to(repo)),
                                       "sha256": sha256(target)})
    if profiles["baseline_ftz_daz"]["inputs"]["before"] != profiles["kdm6_entry_gradual"]["inputs"]["before"]:
        raise SystemExit("paired policy runs did not stage byte-identical inputs")
    gradual_entry = profiles["kdm6_entry_gradual"]["policy_entry_trace"]["text"]
    entry_before = int(gradual_entry.split(",")[1], 16) if gradual_entry else 0
    entry_after = int(gradual_entry.split(",")[2], 16) if gradual_entry else 0
    entry_mask_only = (entry_before ^ entry_after) == 0x8040
    if not entry_mask_only:
        raise SystemExit("runtime KDM6 entry changed MXCSR bits beyond FTZ/DAZ")
    receipt = {
        "schema": "pr76_native_fp_policy_comparison_v1",
        "scope": "paired O0 partialhost research runtime-policy comparison; no model state/input repair; passive baseline observer and FTZ/DAZ treatment at KDM6 entry",
        "policy": {"description": "At KDM6 physics routine entry, preserve current MXCSR except clear FTZ bit 15 and DAZ bit 6.",
                   "mask_hex": "0x00008040", "rounding_mode_changed": False,
                   "exception_masks_changed": False, "sticky_flags_cleared": False,
                   "other_control_bits_changed": False,
                   "linked_ftz_flag_retained": True,
                   "applies_at": "KDM6 routine entry on each calling thread",
                   "restores_prior_thread_state_on_return": False,
                   "scope_limit": "The treatment covers threads entering KDM6; it does not establish process-wide or host-main startup state."},
        "helper_control_bit_test": helper_test,
        "toolchain": {"ifx_path": str(ifx), "ifx_version": ifx_version,
                      "ifx_sha256": sha256(ifx), "icx_path": str(icx),
                      "icx_version": icx_version, "icx_sha256": sha256(icx)},
        "pinned_inputs": {"pr73_receipt_sha256": sha256(pr73_path),
                          "pr74_receipt_sha256": sha256(pr74_path),
                          "base_kdm6_sha256": sha256(source),
                          "native_archive_sha256": sha256(archive),
                          "driver_source_sha256": sha256(driver),
                          "shinhong_source_sha256": sha256(shinhong)},
        "harness": {
            "runner_sha256": sha256(repo / "tests/pr76_native_fp_run.py"),
            "transform_sha256": sha256(repo / "tests/pr76_native_fp_transform.py"),
            "shell_runner_sha256": sha256(repo / "tests/run_pr76_native_fp_policy.sh"),
            "transform_test_sha256": sha256(repo / "tests/test_pr76_native_fp_transform.py"),
            "control_helper_sha256": sha256(repo / "tests/pr76_native_fp_policy.c"),
            "control_helper_test_sha256": sha256(repo / "tests/pr76_native_fp_policy_check.c"),
        },
        "preserved_prior_attempts": {
            "pr75_first_direct_capture_record": "docs/evidence/pr75_native_fp_first_attempt_20261008.json",
            "pr75_first_direct_capture_sha256": sha256(repo / "docs/evidence/pr75_native_fp_first_attempt_20261008.json"),
            "pr75_successful_baseline_record": "docs/evidence/pr75_native_fp_O0_20261008.json",
            "pr75_successful_baseline_sha256": sha256(repo / "docs/evidence/pr75_native_fp_O0_20261008.json"),
            "pr76_first_policy_attempt_record": "docs/evidence/pr76_native_fp_policy_first_attempt_20261008.json",
            "pr76_first_policy_attempt_sha256": sha256(repo / "docs/evidence/pr76_native_fp_policy_first_attempt_20261008.json"),
            "pr76_first_policy_attempt_classification": "paired comparison retained before exact successful target-call capture was added",
            "pr76_first_policy_attempt_artifacts": prior_artifacts,
        },
        "profiles": profiles,
        "comparison": {
            "same_pr74_pretrace_and_driver_capture": all(p["call_binding"]["pretrace_matches"] and
                                                        p["call_binding"]["driver_capture_matches"]
                                                        for p in profiles.values()),
            "same_inputs": all(p["inputs"]["unchanged"] for p in profiles.values()),
            "kdm6_entry_changed_only_ftz_daz": entry_mask_only,
            "kdm6_entry_ftz_daz_cleared": (entry_after & 0x8040) == 0,
            "target_call_same_coordinates": profiles["baseline_ftz_daz"]["target_call"]["record"] is not None and
                profiles["baseline_ftz_daz"]["target_call"]["record"]["i"] == profiles["kdm6_entry_gradual"]["target_call"]["record"]["i"] and
                profiles["baseline_ftz_daz"]["target_call"]["record"]["call_lat_index"] == profiles["kdm6_entry_gradual"]["target_call"]["record"]["call_lat_index"] and
                profiles["baseline_ftz_daz"]["target_call"]["record"]["k"] == profiles["kdm6_entry_gradual"]["target_call"]["record"]["k"],
            "target_call_same_input_bits": profiles["baseline_ftz_daz"]["target_call"]["record"] is not None and
                profiles["kdm6_entry_gradual"]["target_call"]["record"] is not None and
                profiles["baseline_ftz_daz"]["target_call"]["record"]["public_ni_binary32"] == profiles["kdm6_entry_gradual"]["target_call"]["record"]["public_ni_binary32"] and
                profiles["baseline_ftz_daz"]["target_call"]["record"]["dry_density_binary32"] == profiles["kdm6_entry_gradual"]["target_call"]["record"]["dry_density_binary32"],
            "baseline_target_call_rejected": profiles["baseline_ftz_daz"]["target_call"]["record"] is not None and
                not profiles["baseline_ftz_daz"]["target_call"]["record"]["conversion_valid"],
            "gradual_target_call_accepted": profiles["kdm6_entry_gradual"]["target_call"]["record"] is not None and
                profiles["kdm6_entry_gradual"]["target_call"]["record"]["conversion_valid"],
            "same_call_result_differs": profiles["baseline_ftz_daz"]["target_call"]["record"] is not None and
                profiles["kdm6_entry_gradual"]["target_call"]["record"] is not None and
                profiles["baseline_ftz_daz"]["target_call"]["record"]["converted_ni_binary32"] !=
                profiles["kdm6_entry_gradual"]["target_call"]["record"]["converted_ni_binary32"],
            "gradual_target_same_as_entry_thread": profiles["kdm6_entry_gradual"]["target_call"]["record"] is not None and
                profiles["kdm6_entry_gradual"]["target_call"]["record"]["same_thread_as_kdm6_entry"],
            "scheme_or_model_input_modified": False,
            "both_runs_physical_pass": False,
            "interpretation": "Record only the first rejection/failure and available outputs; absence of an adapter failure is not a physical pass.",
        },
        "work_root": str(work_root),
    }
    out = repo / "docs/evidence/pr76_native_fp_policy_20261008.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"PR76_NATIVE_FP_RECEIPT {out}")
    print(f"PR76_NATIVE_FP_BASELINE_STATUS {profiles['baseline_ftz_daz']['run_exit_status']}")
    print(f"PR76_NATIVE_FP_GRADUAL_STATUS {profiles['kdm6_entry_gradual']['run_exit_status']}")
    print(f"PR76_NATIVE_FP_COMPARISON {receipt['comparison']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PR76_NATIVE_FP_RUN_ERROR {exc}", file=sys.stderr)
        raise
