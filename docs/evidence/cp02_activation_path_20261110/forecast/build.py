#!/usr/bin/env python3
"""Build the previous conservative or first-ice-normalized KDM6 WRF variant from frozen inputs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROFILE = Path(__file__).resolve().parents[4] / "tests" / "intel_toolchain.sh"
EXPECTED_IFX_SHA256 = "909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef"
EXPECTED_IFX_VERSION = "ifx (IFX) 2026.0.0 20260331"
EXPECTED_SET_VARS_SHA256 = "26084d08db985eadb61adc43c7f18821be9e75156b60f920de363ea51c70887e"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_identity(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "path": str(path),
        "resolved_path": str(path.resolve()),
        "size_bytes": stat.st_size,
        "device": stat.st_dev,
        "inode": stat.st_ino,
        "sha256": sha256(path),
    }


def load_profile() -> tuple[dict[str, str], str, str]:
    command = ["bash", "-c", 'set -e; set +u; source "$1"; env -0', "profile", str(PROFILE)]
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    environment = {
        key.decode(): value.decode(errors="surrogateescape")
        for item in result.stdout.split(b"\0") if item
        for key, value in [item.split(b"=", 1)]
    }
    compiler = Path(environment["CLOUD_BAL_FC"]).resolve()
    version = subprocess.run([str(compiler), "--version"], check=True, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.splitlines()[0]
    if sha256(compiler) != EXPECTED_IFX_SHA256 or version != EXPECTED_IFX_VERSION:
        raise RuntimeError(f"pinned IFX mismatch: {compiler} {version}")
    setvars = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh")
    if sha256(setvars) != EXPECTED_SET_VARS_SHA256:
        raise RuntimeError("pinned oneAPI setvars hash mismatch")
    return environment, str(compiler), version


def checked_inputs(manifest_path: Path) -> tuple[Path, dict[str, object]]:
    manifest = json.loads(manifest_path.read_text())
    input_root = manifest_path.parent
    mismatches = []
    for item in manifest["files"]:
        path = input_root / item["relative_path"]
        actual = sha256(path)
        if actual != item["sha256"]:
            mismatches.append({"path": str(path), "expected": item["sha256"], "actual": actual})
    if mismatches:
        raise RuntimeError("frozen input hash mismatch: " + json.dumps(mismatches))
    return input_root, manifest


def run_command(argv: list[str], cwd: Path, environment: dict[str, str], log_path: Path) -> dict[str, object]:
    result = subprocess.run(argv, cwd=cwd, env=environment, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    log_path.write_bytes(result.stdout)
    return {
        "argv": argv,
        "argv_shell_display": shlex.join(argv),
        "cwd": str(cwd),
        "exit_code": result.returncode,
        "log": file_identity(log_path),
    }


def main() -> int:
    if len(sys.argv) != 5 or sys.argv[1] != "MP10_NN_END":
        print("usage: build_native_variant.py MP10_NN_END INPUT_ROOT FRESH_OUTPUT_DIR REVIEW_JSON", file=sys.stderr)
        return 2
    variant, input_arg, output_arg, review_arg = sys.argv[1:]
    task_root = PROFILE.parents[1].parent
    expected_input_root = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_grouped_forecast_20261105/runtime/native_build/inputs")
    variants_root = task_root / "runtime/nn_end/native_build/variants"
    input_manifest = Path(input_arg).resolve() / "copy_manifest.json"
    output = Path(output_arg).resolve()
    if input_manifest.parent != expected_input_root:
        raise RuntimeError(f"input root must be the frozen scratch copy: {expected_input_root}")
    if not output.is_relative_to(variants_root) or output.is_relative_to(PROFILE.parents[1]):
        raise RuntimeError(f"build output must be under fresh runtime/native_build/variants: {variants_root}")
    if output.exists():
        raise FileExistsError(f"refusing existing output directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    input_root, manifest = checked_inputs(input_manifest)
    source = Path(__file__).resolve().parent / "source" / (variant + ".f90")
    receipt_path = Path(__file__).resolve().parent / "source/source_receipt.json"
    generator = Path(__file__).resolve().parent / "source/generate.py"
    policy = Path(__file__).resolve().parent / "policy.json"
    review = json.loads(Path(review_arg).read_text())
    generated = json.loads(receipt_path.read_text())
    required = {"source_receipt_sha256": receipt_path, "generator_sha256": generator,
                "policy_sha256": policy, "build_script_sha256": Path(__file__)}
    if review.get("status") != "GO_FOR_BUILD" or any(review.get(k) != sha256(p) for k, p in required.items()):
        raise ValueError("source/build review does not bind current recipe")
    if generated["candidate_sha256"] != sha256(source) or generated["parent_sha256"] != "4604dc031d618a6feeb43a72a7cfabc656abf7f3e4eb591b0c7724f7e490f586":
        raise ValueError("candidate source identity differs")
    module_dir = input_root / "modules"
    output.mkdir(parents=True)
    work = output / "compile"
    work.mkdir()
    archive = output / "libwrflib.a"
    frozen_archive = input_root / "experiment" / "build_FIX" / "libwrflib.a"
    archive.write_bytes(frozen_archive.read_bytes())

    receipt: dict[str, object] = {
        "schema": "cp02_nn_end_native_build_receipt_v1",
        "review": file_identity(Path(review_arg)),
        "source_receipt": file_identity(receipt_path),
        "policy": file_identity(policy),
        "variant": variant,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "status": "BUILDING",
        "profile_script": file_identity(PROFILE),
        "input_manifest": file_identity(input_manifest),
        "input_manifest_sha256": sha256(input_manifest),
        "input_hash_audit_before": manifest["files"],
        "source": file_identity(source),
        "original_archive": next(x for x in manifest["files"] if x["relative_path"].endswith("build_FIX/libwrflib.a")),
        "variant_archive_before": file_identity(archive),
    }
    receipt_path = output / "build_receipt.json"
    try:
        environment, compiler, version = load_profile()
        temporary = work / "tmp"
        temporary.mkdir()
        environment["TMPDIR"] = str(temporary)
        environment["NETCDF"] = "/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel"
        environment["LD_LIBRARY_PATH"] = environment["NETCDF"] + "/lib:" + environment.get("LD_LIBRARY_PATH", "")
        receipt["compiler"] = {"path": compiler, "version": version, **file_identity(Path(compiler))}
        compile_flags = ["-c", "-O2", "-fp-model", "strict", "-fimf-arch-consistency=true",
                        "-no-ftz", "-fpe0", "-traceback", "-FR", "-convert", "big_endian",
                        "-real-size", "32", "-i4", "-I", str(module_dir), "-o",
                        str(work / "module_mp_kdm6.o"), str(source)]
        compile_result = run_command([compiler, *compile_flags], work, environment, output / "compile.log")
        receipt["compile"] = compile_result
        if compile_result["exit_code"] != 0:
            raise RuntimeError("IFX module compile failed")
        object_path = work / "module_mp_kdm6.o"
        receipt["object"] = file_identity(object_path)
        archive_commands = []
        archive_steps = [
            ["ar", "d", str(archive), "module_mp_kdm6.o"],
            ["ar", "q", str(archive), str(object_path)],
            ["ranlib", str(archive)],
        ]
        for index, argv in enumerate(archive_steps, start=1):
            tool_path = Path(shutil.which(argv[0]) or "").resolve()
            if not tool_path.is_file():
                raise RuntimeError(f"archive tool unavailable: {argv[0]}")
            argv[0] = str(tool_path)
            receipt.setdefault("archive_tools", {})[tool_path.name] = file_identity(tool_path)
            result = run_command(argv, work, environment, output / f"archive_{index}.log")
            archive_commands.append(result)
            if result["exit_code"] != 0:
                receipt["archive_commands"] = archive_commands
                raise RuntimeError(f"archive update failed: {result['argv_shell_display']}")
        receipt["archive_commands"] = archive_commands
        receipt["archive_after"] = file_identity(archive)
        member = subprocess.run(["ar", "p", str(archive), "module_mp_kdm6.o"],
                                check=True, stdout=subprocess.PIPE).stdout
        receipt["archive_member_sha256"] = hashlib.sha256(member).hexdigest()
        if receipt["archive_member_sha256"] != receipt["object"]["sha256"]:
            raise RuntimeError("compiled object and linked archive member hashes differ")

        host = input_root / "experiment" / "host"
        netcdf = input_root / "netcdf"
        executable = output / "wrf.exe"
        explicit = [
            host / "main/wrf.o", host / "main/module_wrf_top.o", archive,
            host / "external/fftpack/fftpack5/libfftpack.a",
            host / "external/io_grib1/libio_grib1.a",
            host / "external/io_grib_share/libio_grib_share.a",
            host / "external/io_int/libwrfio_int.a",
            host / "external/RSL_LITE/librsl_lite.a",
            host / "frame/module_internal_header_util.o", host / "frame/pack_utils.o",
        ]
        mpi_mpif90 = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpif90")
        linker = [str(mpi_mpif90), f"-f90={compiler}", "-o", str(executable), "-O2",
                  "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz", "-fpe0",
                  "-traceback", "-FR", "-convert", "big_endian", "-ip", *map(str, explicit),
                  "-L" + str(host / "external/esmf_time_f90"), "-lesmf_time",
                  "-L" + str(host / "external/io_netcdf"), "-lwrfio_nf",
                  "-L" + str(netcdf), "-lnetcdff", "-lnetcdf"]
        receipt["linker"] = file_identity(mpi_mpif90)
        receipt["link"] = run_command(linker, work, environment, output / "link.log")
        if receipt["link"]["exit_code"] != 0:
            raise RuntimeError("MPI link failed")
        receipt["executable"] = file_identity(executable)
        ldd = subprocess.run(["ldd", str(executable)], env=environment, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, check=False)
        (output / "ldd.txt").write_bytes(ldd.stdout)
        ldd_text = ldd.stdout.decode(errors="replace")
        resolved_paths = []
        for line in ldd_text.splitlines():
            match = re.search(r"=>\s+(/\S+)|^\s*(/\S+)\s+\(", line)
            if match:
                resolved_paths.append(Path(match.group(1) or match.group(2)))
            elif "not found" in line:
                raise RuntimeError("unresolved shared library: " + line.strip())
        if ldd.returncode != 0:
            raise RuntimeError("ldd failed")
        receipt["ldd"] = {
            "exit_code": ldd.returncode,
            "log": file_identity(output / "ldd.txt"),
            "resolved_libraries": [file_identity(path) for path in resolved_paths],
        }
        receipt["generated_module"] = file_identity(work / "module_mp_kdm6.mod")
        receipt["status"] = "PASS"
    except Exception as error:
        receipt["status"] = "FAIL"
        receipt["failure"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        receipt["input_hash_audit_after"] = [
            {"relative_path": item["relative_path"], "expected_sha256": item["sha256"],
             "observed_sha256": sha256(input_root / item["relative_path"])}
            for item in manifest["files"]
        ]
        changed_inputs = [item for item in receipt["input_hash_audit_after"]
                          if item["expected_sha256"] != item["observed_sha256"]]
        if changed_inputs:
            receipt["status"] = "FAIL"
            receipt["failure"] = {"type": "InputMutation", "message": "frozen scratch input changed during build", "files": changed_inputs}
        receipt["inputs_unchanged"] = not changed_inputs
        if not receipt["inputs_unchanged"]:
            receipt["status"] = "FAIL"
            receipt["failure"] = {"type": "InputChanged", "message": "frozen copied input changed during build", "files": changed_inputs}
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "receipt": str(receipt_path)}, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
