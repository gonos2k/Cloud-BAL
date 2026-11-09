#!/usr/bin/env python3
"""Build protected CP02 OLD/FIX executables with the pinned Cloud-BAL toolchain."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

WORK = Path(__file__).resolve().parent
CLOUD_BAL = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_protected_process_20261106/Cloud-BAL")
EVIDENCE = CLOUD_BAL / "docs/evidence/cp02_protected_process_20261106/native"
SOURCE_RECEIPT = EVIDENCE / "source/source_generation_receipt.json"
PROFILE = CLOUD_BAL / "tests/intel_toolchain.sh"
PROFILE_SHA = "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4"
ARCHIVE = Path("/var/tmp/firsthour-runtime-plan-20261030/experiment")
ARCHIVE_RECEIPT = ARCHIVE / "build_receipt.json"
HOST = ARCHIVE / "host"
STAGE = Path("/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED")
STAGE_RECEIPT = STAGE / "receipt.json"
EXPECTED_STAGE_INPUT = "9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5"
EXPECTED_BOUNDARY = "74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45"
ARM_SOURCE = {"OLD": "BASE", "FIX": "FIX"}


def sha(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def require_review(path: Path) -> dict:
    receipt = json.loads(path.read_text())
    status = str(receipt.get("status", receipt.get("review_status", ""))).upper()
    if status not in {"GO", "PASS", "APPROVED", "GO_FOR_COMPILE_STATIC_REVIEW"}:
        raise ValueError("independent plan/source review receipt is not GO")
    generated = json.loads(SOURCE_RECEIPT.read_text())
    source_review = receipt.get("generated_source", {})
    plan_review = receipt.get("plan", {})
    cohort_review = receipt.get("cohort", {})
    if source_review.get("receipt_sha256") != sha(SOURCE_RECEIPT):
        raise ValueError("review receipt does not bind current source-generation receipt")
    if source_review.get("schema_sha256") != generated.get("schema_sha256"):
        raise ValueError("review receipt does not bind current schema")
    if plan_review.get("sha256") != generated.get("plan_sha256"):
        raise ValueError("review receipt does not bind current plan")
    if cohort_review.get("receipt_sha256") != generated.get("cohort_receipt_sha256"):
        raise ValueError("review receipt does not bind current cohort")
    for arm in ("OLD", "FIX"):
        expected = next(item["sha256"] for item in generated["arms"] if item["arm"] == arm)
        key = "old_source_sha256" if arm == "OLD" else "fix_source_sha256"
        if source_review.get(key) != expected:
            raise ValueError(f"review receipt does not bind current {arm} source")
    return receipt


def run_command(argv: list[str], cwd: Path, log_path: Path, env: dict[str, str]) -> dict:
    started = time.time()
    with log_path.open("xb") as log:
        result = subprocess.run(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    return {"argv": argv, "cwd": str(cwd), "exit_code": result.returncode,
            "elapsed_seconds": time.time() - started, "log_sha256": sha(log_path), "log": str(log_path)}


def build(review_path: Path) -> dict:
    review = require_review(review_path)
    if sha(PROFILE) != PROFILE_SHA:
        raise ValueError("pinned Cloud-BAL Intel toolchain profile changed")
    if not os.environ.get("CLOUD_BAL_FC"):
        raise ValueError("source tests/intel_toolchain.sh before calling build_pair.py")
    compiler = Path(os.environ["CLOUD_BAL_FC"]).resolve()
    if compiler != Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/ifx"):
        raise ValueError("compiler path is not the pinned ifx")

    archive_receipt = json.loads(ARCHIVE_RECEIPT.read_text())
    source_receipt = json.loads(SOURCE_RECEIPT.read_text())
    if sha(STAGE_RECEIPT) != "00eddd6ac26a3a4857ea40e294256d2b32c9c9e6a2998f112000c39d5281bf5e":
        raise ValueError("B1 stage receipt pin changed")
    staged = json.loads(STAGE_RECEIPT.read_text())["staged_sha256_after"]
    if len(staged) != 89 or staged["wrfinput_d01"] != EXPECTED_STAGE_INPUT or staged["wrfbdy_d01"] != EXPECTED_BOUNDARY:
        raise ValueError("B1 stage inputs do not match the frozen initial/boundary inputs")

    build_root = WORK / "build"
    if build_root.exists():
        raise FileExistsError(f"fresh build root already exists: {build_root}")
    build_root.mkdir(parents=True)
    env = os.environ.copy()
    env["TMPDIR"] = str(build_root / "tmp")
    Path(env["TMPDIR"]).mkdir()

    link_inputs = {}
    template = archive_receipt["arms"]["BASE"]["link"]["argv"]
    for arg in template:
        p = Path(arg)
        if p.is_file() and p.suffix in (".o", ".a"):
            link_inputs[str(p)] = sha(p)
    host_archive = HOST / "main/libwrflib.a"
    host_archive_hash = sha(host_archive)
    output_arms = {}
    for arm, source_arm in ARM_SOURCE.items():
        source_path = EVIDENCE / f"source/module_mp_kdm6_{arm}.f90"
        expected_source = next(row["sha256"] for row in source_receipt["arms"] if row["arm"] == arm)
        if sha(source_path) != expected_source:
            raise ValueError(f"{arm} generated source does not match its receipt")
        arm_dir = build_root / arm
        arm_dir.mkdir()
        shutil.copy2(source_path, arm_dir / "module_mp_kdm6.f90")
        compile_argv = list(archive_receipt["arms"][source_arm]["compile"]["argv"])
        if Path(compile_argv[0]).resolve() != compiler:
            raise ValueError("historical compile command does not use pinned ifx")
        compile_argv[compile_argv.index("-o") + 1] = str(arm_dir / "module_mp_kdm6.o")
        compile_argv[-1] = str(arm_dir / "module_mp_kdm6.f90")
        compile_log = arm_dir / "compile.log"
        compile_receipt = run_command(compile_argv, arm_dir, compile_log, env)
        if compile_receipt["exit_code"] != 0:
            raise RuntimeError(f"{arm} compile failed; see {compile_log}")

        local_archive = arm_dir / "libwrflib.a"
        shutil.copy2(host_archive, local_archive)
        members = subprocess.check_output(["ar", "t", str(local_archive)], text=True).splitlines()
        if members.count("module_mp_kdm6.o") != 1:
            raise ValueError("host Fortran archive does not have one KDM6 member")
        subprocess.run(["ar", "r", str(local_archive), str(arm_dir / "module_mp_kdm6.o")],
                       cwd=arm_dir, env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        member = subprocess.check_output(["ar", "p", str(local_archive), "module_mp_kdm6.o"])
        member_sha = hashlib.sha256(member).hexdigest()
        if member_sha != sha(arm_dir / "module_mp_kdm6.o"):
            raise ValueError("archive KDM6 object differs from the compiler object")

        link_argv = list(archive_receipt["arms"][source_arm]["link"]["argv"])
        link_argv[link_argv.index("-o") + 1] = str(arm_dir / "wrf.exe")
        old_archive = str(ARCHIVE / f"build_{source_arm}" / "libwrflib.a")
        if link_argv.count(old_archive) != 1:
            raise ValueError("historical link archive argument differs")
        link_argv[link_argv.index(old_archive)] = str(local_archive)
        link_log = arm_dir / "link.log"
        link_receipt = run_command(link_argv, arm_dir, link_log, env)
        if link_receipt["exit_code"] != 0:
            raise RuntimeError(f"{arm} link failed; see {link_log}")
        output_arms[arm] = {
            "source_sha256": sha(source_path), "object_sha256": sha(arm_dir / "module_mp_kdm6.o"),
            "archive_sha256": sha(local_archive), "archive_member_sha256": member_sha,
            "executable_sha256": sha(arm_dir / "wrf.exe"), "module_sha256": sha(arm_dir / "module_mp_kdm6.mod"),
            "compile": compile_receipt, "link": link_receipt,
        }

    after_links = {path: sha(Path(path)) for path in link_inputs}
    if after_links != link_inputs or sha(host_archive) != host_archive_hash:
        raise ValueError("one or more pinned host link inputs changed during build")
    profile_info = {
        "profile_path": str(PROFILE), "profile_sha256": PROFILE_SHA,
        "compiler_path": str(compiler), "compiler_sha256": sha(compiler),
        "compiler_version": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0],
        "mpi_launcher": "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun",
        "mpi_env": "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh",
    }
    result = {"status": "PASS" if all(a["compile"]["exit_code"] == 0 and a["link"]["exit_code"] == 0 for a in output_arms.values()) else "FAIL",
              "review_receipt": str(review_path), "review_receipt_sha256": sha(review_path),
              "source_generation_receipt_sha256": sha(SOURCE_RECEIPT), "profile": profile_info,
              "archive_build_receipt_sha256": sha(ARCHIVE_RECEIPT), "host_archive_sha256": host_archive_hash,
              "link_inputs_before": link_inputs, "link_inputs_after": after_links,
              "arms": output_arms}
    (build_root / "build_receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    if result["status"] != "PASS":
        raise RuntimeError("paired build failed")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-receipt", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.review_receipt), indent=2))

if __name__ == "__main__":
    main()
