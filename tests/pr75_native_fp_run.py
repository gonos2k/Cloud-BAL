#!/usr/bin/env python3
"""Build and run the O0-only PR75 native FP-state diagnostic in scratch."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pr75_native_fp_transform import transform


EXPECTED = {
    "pr73_receipt": "5be57e83f5ebe8e7124e4f9d5bb7ab527bdf4ae495ff19a9b1bd4e532a10a355",
    "archive": "b6cb181e2016b10b7ccd1b040308eecee4e8cbbdb54ffc87473bc2cb05da4dbd",
    "kdm6_source": "1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819",
    "instrumented_driver": "342378285d929d06aa88b3c47b27c906bac05e560244162e4f946481ea4bd322",
    "shinhong_source": "5fbe821bb3b82e406fee459e5b2d745156ea1a030b5f0ecd2c7191025f296553",
    "native_archive_o0": "3ddba2be0e657b3e5717f867d81805b73e5a15c3583bcbdcfc06de46802a6083",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> int:
    repo = Path(__file__).resolve().parents[1]
    work_root = Path(sys.argv[1]).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    tool_dir = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin")
    ifx = Path(os.environ["CLOUD_BAL_FC"]).resolve()
    icx = tool_dir / "icx"
    mpi = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpiifx")

    pr73_receipt = repo / "docs/evidence/pr73_native_first_violation_20261008_attempt2/native_receipt.json"
    pr74_receipt = repo / "docs/evidence/pr74_shinhong_qni_driver_20261008.json"
    pr73 = json.loads(pr73_receipt.read_text())
    pr74 = json.loads(pr74_receipt.read_text())
    original_source = Path("/var/tmp/pr73_native_first_violation.x3bvfn/build/source/module_mp_kdm6.f90")
    original_archive = Path(pr73["build_artifacts"]["archive_path"])
    native_archive = Path(pr74["profiles"]["O0"]["archive_path"])
    driver_source = repo / "docs/evidence/pr74_actual_driver_instrumented.F"
    shinhong_source = Path("/var/tmp/pr73_pbl_research/source_after/module_bl_shinhong_pr65.F")
    for name, path in (("pr73_receipt", pr73_receipt), ("archive", original_archive),
                       ("kdm6_source", original_source), ("instrumented_driver", driver_source),
                       ("shinhong_source", shinhong_source), ("native_archive_o0", native_archive)):
        if sha256(path) != EXPECTED[name]:
            raise SystemExit(f"{name} hash differs from pinned PR74 evidence")
    if sha256(native_archive) != pr74["profiles"]["O0"]["archive_sha256"]:
        raise SystemExit("PR74 O0 archive hash differs from its receipt")

    compiler_version = subprocess.run([str(ifx), "--version"], check=True, text=True,
                                      capture_output=True).stdout.splitlines()[0]
    c_version = subprocess.run([str(icx), "--version"], check=True, text=True,
                               capture_output=True).stdout.splitlines()[0]
    if not compiler_version.startswith("ifx (IFX) 2026.0.0 20260331"):
        raise SystemExit(f"unexpected pinned Fortran compiler: {compiler_version}")
    if not c_version.startswith("Intel(R) oneAPI DPC++/C++ Compiler"):
        raise SystemExit(f"unexpected Intel C compiler: {c_version}")

    case = work_root / "O0"
    compile_dir = case / "compile"
    link_dir = case / "build/link/main"
    run_dir = case / "run"
    compile_dir.mkdir(parents=True)
    link_dir.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    shutil.copytree(native_archive.parent, link_dir, dirs_exist_ok=True, copy_function=shutil.copy2)
    archive = link_dir / native_archive.name
    source_copy = compile_dir / "module_mp_kdm6.f90"
    source_copy.write_text(transform(original_source.read_text()))
    c_source = repo / "tests/pr75_native_fp_mxcsr.c"
    c_copy = compile_dir / c_source.name
    shutil.copy2(c_source, c_copy)

    flags = list(os.environ["PR75_FP_FLAGS"].split("\n"))
    flags = [flag for flag in flags if flag]
    include_args = ["-I" + str(Path("/var/tmp/pr61_ccn_origin_20261006/hostcopy/phys")),
                    "-I" + str(Path("/var/tmp/pr61_ccn_origin_20261006/hostcopy/frame"))]
    compile_argv = [str(ifx), *flags, "-convert", "big_endian", *include_args,
                    "-free", "-c", str(source_copy)]
    pinned_compile_argv = pr73["build_artifacts"]["compile_argv"]
    pinned_compile_prefix = pinned_compile_argv[:pinned_compile_argv.index("-c")]
    if compile_argv[:compile_argv.index("-c")] != pinned_compile_prefix:
        raise SystemExit("KDM6 diagnostic compile options differ from pinned O0 source build")
    c_compile_argv = [str(icx), "-O0", "-c", str(c_copy), "-o", str(compile_dir / "pr75_native_fp_mxcsr.o")]
    with (compile_dir / "compile.log").open("wb") as log:
        subprocess.run(compile_argv, cwd=compile_dir, check=True, stdout=log, stderr=subprocess.STDOUT)
        subprocess.run(c_compile_argv, cwd=compile_dir, check=True, stdout=log, stderr=subprocess.STDOUT)

    old_archive_sha = sha256(archive)
    subprocess.run(["/usr/bin/ar", "r", str(archive), str(compile_dir / "module_mp_kdm6.o"),
                    str(compile_dir / "pr75_native_fp_mxcsr.o")], check=True, cwd=link_dir)
    members = subprocess.run(["/usr/bin/ar", "t", str(archive)], check=True, cwd=link_dir,
                             text=True, capture_output=True).stdout.splitlines()
    member_sha = {}
    for member, obj in (("module_mp_kdm6.o", compile_dir / "module_mp_kdm6.o"),
                        ("pr75_native_fp_mxcsr.o", compile_dir / "pr75_native_fp_mxcsr.o")):
        if members.count(member) != 1:
            raise SystemExit(f"archive member count mismatch: {member}")
        member_data = subprocess.run(["/usr/bin/ar", "p", str(archive), member], check=True,
                                     cwd=link_dir, capture_output=True).stdout
        if hashlib.sha256(member_data).hexdigest() != sha256(obj):
            raise SystemExit(f"archive member bytes differ: {member}")
        member_sha[member] = sha256(obj)

    link_argv = list(pr74["profiles"]["O0"]["actual_link"]["argv"])
    inherited_link_argv = list(link_argv)
    old_output = link_argv[2]
    executable = case / "wrf.exe"
    link_argv[link_argv.index(old_output)] = str(executable)
    normalized_link_argv = list(link_argv)
    normalized_link_argv[normalized_link_argv.index(str(executable))] = old_output
    if normalized_link_argv != inherited_link_argv:
        raise SystemExit("diagnostic link argv changed beyond the scratch executable path")
    archive_arg = next((item for item in link_argv if Path(item).name == archive.name), None)
    if archive_arg is None or (link_dir / archive_arg).resolve() != archive.resolve():
        raise SystemExit("diagnostic archive was not selected in inherited link argv")
    with (link_dir / "pr75_link.log").open("wb") as log:
        subprocess.run(link_argv, cwd=link_dir, check=True, stdout=log, stderr=subprocess.STDOUT)

    input_before = {}
    for entry in pr73["input_hashes_before_after"]:
        source = Path(entry["path"])
        if source.name == "wrf.exe":
            continue
        if sha256(source) != entry["sha256_before"]:
            raise SystemExit(f"PR73 input hash mismatch: {source.name}")
        target = run_dir / source.name
        if target.name in input_before:
            raise SystemExit(f"duplicate staged input basename: {target.name}")
        shutil.copy2(source, target)
        input_before[target.name] = sha256(target)
    executable_in_run = run_dir / "wrf.exe"
    shutil.copy2(executable, executable_in_run)
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "68"
    raw_log = run_dir / "candidate_run.log"
    with raw_log.open("wb") as log:
        try:
            process = subprocess.run([str(executable_in_run)], cwd=run_dir, env=env,
                                     stdout=log, stderr=subprocess.STDOUT, timeout=900)
            status: int | str = process.returncode
        except subprocess.TimeoutExpired:
            status = "TIMEOUT_900S"

    input_after = {name: sha256(run_dir / name) for name in input_before}
    diag = run_dir / "pr75_native_fp.raw"
    rsl_error = run_dir / "rsl.error.0000"
    pr74_pretrace_path = Path(pr74["profiles"]["O0"]["first_call_pretrace_path"])
    new_pretrace_path = run_dir / "kdm6_first_call_pre.raw"
    pr74_driver_capture_path = Path(pr74["profiles"]["O0"]["driver_capture_path"])
    new_driver_capture_path = run_dir / "pr74_qni_driver.raw"
    diagnostic_text = diag.read_text(errors="replace") if diag.is_file() else None
    native_failure = None
    if diagnostic_text:
        rows = [line.split(",") for line in diagnostic_text.splitlines()]
        if len(rows) >= 3 and rows[0][0] == "NI_ADAPTER_FAILURE" and rows[1][0] == "BITS_AND_STATE":
            mxcsr_before = int(rows[1][1], 16)
            mxcsr_after = int(rows[1][2], 16)
            native_failure = {
                "i": int(rows[0][1]), "j": int(rows[0][2]), "k": int(rows[0][3]),
                "j_semantics": "wrapper call_lat_index; global-j mapping unclaimed",
                "public_ni_kg_inverse": float(rows[0][4]),
                "dry_density_kg_m3": float(rows[0][5]),
                "converted_ni_m_inverse3": float(rows[0][6]),
                "conversion_valid": rows[0][7].strip().upper() == "T",
                "public_ni_binary32": rows[1][3], "dry_density_binary32": rows[1][4],
                "converted_ni_binary32": rows[1][5],
                "mxcsr_before": f"0x{mxcsr_before:08X}",
                "mxcsr_after": f"0x{mxcsr_after:08X}",
                "daz_enabled_before": bool(mxcsr_before & (1 << 6)),
                "ftz_enabled_before": bool(mxcsr_before & (1 << 15)),
                "thread_id_before": int(rows[1][6], 16),
                "thread_id_after": int(rows[2][1]),
                "same_thread": int(rows[1][6], 16) == int(rows[2][1]),
                "mxcsr_unchanged": mxcsr_before == mxcsr_after,
            }
    receipt = {
        "schema": "pr75_native_fp_runtime_diagnostic_v1",
        "scope": "O0 diagnostics-only partialhost reproduction; NI adapter FP state observed at exact failure",
        "run_exit_status": status,
        "runtime_configuration_changed": False,
        "mxcsr_modified_by_diagnostic": False,
        "sources": {
            "base_native_source": str(original_source), "base_native_source_sha256": sha256(original_source),
            "transformed_source_sha256": sha256(source_copy), "transform_sha256": sha256(repo / "tests/pr75_native_fp_transform.py"),
            "runner_sha256": sha256(repo / "tests/pr75_native_fp_run.py"),
            "shell_runner_sha256": sha256(repo / "tests/run_pr75_native_fp_O0.sh"),
            "C_helper": str(c_copy), "C_helper_sha256": sha256(c_copy),
            "driver_source_sha256": sha256(driver_source), "shinhong_source_sha256": sha256(shinhong_source),
        },
        "attempted_execution": {
            "prior_first_direct_capture_record": str(repo / "docs/evidence/pr75_native_fp_first_attempt_20261008.json"),
            "prior_first_direct_capture_record_sha256": sha256(repo / "docs/evidence/pr75_native_fp_first_attempt_20261008.json"),
            "prior_first_direct_capture_classification": "nonfinal; compile omitted original -convert big_endian, pretrace encoding differed",
        },
        "toolchain": {
            "ifx_path": str(ifx), "ifx_version": compiler_version, "ifx_sha256": sha256(ifx),
            "icx_path": str(icx), "icx_version": c_version, "icx_sha256": sha256(icx),
            "ifx_compile_argv": compile_argv, "icx_compile_argv": c_compile_argv,
            "pinned_kdm6_compile_option_prefix_matches": True,
        },
        "archive": {
            "incoming_path": str(native_archive), "incoming_sha256": sha256(native_archive),
            "incoming_pr74_receipt_sha256": pr74["profiles"]["O0"]["archive_sha256"],
            "scratch_path": str(archive), "scratch_sha256_before_replace": old_archive_sha,
            "scratch_sha256_after_replace": sha256(archive), "replacement_object_sha256": member_sha,
            "incoming_archive_unchanged": sha256(native_archive) == pr74["profiles"]["O0"]["archive_sha256"],
        },
        "link": {
            "inherited_pr74_link_argv_sha256": hashlib.sha256(json.dumps(pr74["profiles"]["O0"]["actual_link"]["argv"], separators=(",", ":")).encode()).hexdigest(),
            "diagnostic_link_argv": link_argv,
            "non_output_link_arguments_unchanged": True,
            "inherited_fp_flags": [flag for flag in link_argv if flag in ("-ftz", "-no-ftz")],
            "executable_sha256": sha256(executable),
        },
        "inputs": {"count": len(input_before), "unchanged": input_before == input_after,
                   "sha256_before": input_before, "sha256_after": input_after},
        "call_binding": {
            "pr74_o0_reference_pretrace": str(pr74_pretrace_path),
            "pr74_o0_reference_pretrace_sha256": sha256(pr74_pretrace_path),
            "pr74_o0_receipt_pretrace_sha256": pr74["profiles"]["O0"]["first_call_pretrace_sha256"],
            "diagnostic_run_pretrace": str(new_pretrace_path),
            "diagnostic_run_pretrace_sha256": sha256(new_pretrace_path) if new_pretrace_path.is_file() else None,
            "pretrace_hash_matches": new_pretrace_path.is_file() and sha256(new_pretrace_path) ==
                                     pr74["profiles"]["O0"]["first_call_pretrace_sha256"],
            "pr74_o0_driver_capture_sha256": sha256(pr74_driver_capture_path),
            "diagnostic_run_driver_capture_sha256": sha256(new_driver_capture_path) if new_driver_capture_path.is_file() else None,
            "driver_capture_hash_matches": new_driver_capture_path.is_file() and sha256(new_driver_capture_path) ==
                                           sha256(pr74_driver_capture_path),
        },
        "observations": {
            "diagnostic_path": str(diag), "diagnostic_sha256": sha256(diag) if diag.is_file() else None,
            "diagnostic_text": diagnostic_text, "native_failure": native_failure,
            "rsl_error_sha256": sha256(rsl_error) if rsl_error.is_file() else None,
            "rsl_error_tail": rsl_error.read_text(errors="replace")[-2500:] if rsl_error.is_file() else None,
            "run_log_sha256": sha256(raw_log),
        },
        "work_root": str(work_root),
    }
    out = repo / "docs/evidence/pr75_native_fp_O0_20261008.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"PR75_NATIVE_FP_RECEIPT {out}")
    print(f"PR75_NATIVE_FP_STATUS {status}")
    print(f"PR75_NATIVE_FP_TRACE {receipt['observations']['diagnostic_sha256']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"PR75_NATIVE_FP_RUN_ERROR {exc}", file=sys.stderr)
        raise
