#!/usr/bin/env python3
"""Rebuild the KDM6 radar coefficient contract in a copied partial host."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from pr77_native_state_transform import transform as transform_kdm6


HOST = Path("/var/tmp/pr61_ccn_origin_20261006/hostcopy")
SOURCE = Path("/var/tmp/pr73_native_first_violation.x3bvfn/build/source/module_mp_kdm6.f90")
BASE = Path("/var/tmp/native-controlled-build/noah_scalar")
BASE_ARCHIVE = BASE / "build/link/main/libwrflib_pr65.a"
PR73_RECEIPT = "docs/evidence/pr73_native_first_violation_20261008_attempt2/native_receipt.json"
PR74_RECEIPT = "docs/evidence/pr74_shinhong_qni_driver_20261008.json"
EXPECTED = {
    "kdm6_source": "1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819",
    "kdm6_transformed": "0575ece19473618adcfb1a937f92eb98a2f6155c8460452ac01c816760989981",
    "radar_source": "aa99da858be41efa579966680708d230123a7417560af0eb2e24f4c94e253688",
    "base_archive": "747fab43af5d46187d549fe45d8501bbb88d744d358a8a423ec948a276633f26",
    "base_executable": "618b0bac7ce39b6c3ab686bf795d0503a5fed688ecab4dcbec7ab004b50b86f2",
    "base_kdm6_object": "0b36a3d6ae2fe4d5ea4561fb456ff3961886dec9a1f1549d3b0eec95753d7cd5",
    "base_radar_object": "f6fafab46acba7136834c2b5957b3db85acef3b71e1ed1be50de8f35eb5334df",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_hash(label: str, path: Path, expected: str) -> str:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"{label} hash mismatch: {path} ({actual})")
    return actual


def archive_member(archive: Path, name: str, cwd: Path) -> bytes:
    return subprocess.run(["/usr/bin/ar", "p", str(archive), name], cwd=cwd,
                          check=True, capture_output=True).stdout


def run_command(argv: list[str], cwd: Path, log_path: Path) -> None:
    with log_path.open("wb") as log:
        subprocess.run(argv, cwd=cwd, check=True, stdout=log,
                       stderr=subprocess.STDOUT)


def stage_inputs(repo: Path, run_dir: Path, receipt: dict) -> dict[str, str]:
    before = {}
    for entry in receipt["input_hashes_before_after"]:
        original = Path(entry["path"])
        if original.name == "wrf.exe":
            continue
        require_hash(f"input {original.name}", original, entry["sha256_before"])
        if original.name in before:
            raise ValueError(f"duplicate input basename: {original.name}")
        target = run_dir / original.name
        shutil.copy2(original, target)
        before[original.name] = sha256(target)
    return before


def compile_candidate(repo: Path, root: Path, free_flags: list[str]) -> dict:
    require_hash("KDM6 source", SOURCE, EXPECTED["kdm6_source"])
    require_hash("radar source", HOST / "phys/module_mp_radar.F", EXPECTED["radar_source"])
    require_hash("base archive", BASE_ARCHIVE, EXPECTED["base_archive"])
    require_hash("base executable", BASE / "wrf.exe", EXPECTED["base_executable"])

    link_dir = root / "build/link/main"
    compile_dir = root / "compile"
    link_dir.mkdir(parents=True)
    compile_dir.mkdir()
    shutil.copytree(BASE / "build/link/main", link_dir, dirs_exist_ok=True,
                    copy_function=shutil.copy2)
    archive = link_dir / BASE_ARCHIVE.name
    for label, member in (("KDM6", "module_mp_kdm6.o"),
                          ("radar", "module_mp_radar.o")):
        member_hash = hashlib.sha256(archive_member(archive, member, link_dir)).hexdigest()
        if member_hash != EXPECTED[f"base_{label.lower()}_object"]:
            raise ValueError(f"base archive {member} differs from native receipt")

    radar_source = compile_dir / "module_mp_radar.F"
    shutil.copy2(HOST / "phys/module_mp_radar.F", radar_source)
    source_text = transform_kdm6(SOURCE.read_text())
    if hashlib.sha256(source_text.encode()).hexdigest() != EXPECTED["kdm6_transformed"]:
        raise ValueError("KDM6 baseline transformation differs from PR77 compiled source")
    kdm6_source = compile_dir / "module_mp_kdm6.F"
    kdm6_source.write_text(source_text)

    patch_path = repo / "patches/kdm6_variable_graupel_radar_abi.patch"
    run_command(["patch", "--fuzz=0", "-p1", "-i", str(patch_path)],
                compile_dir, compile_dir / "patch.log")
    patched_radar = radar_source.read_text()
    patched_kdm6 = kdm6_source.read_text()
    if "subroutine radar_init_variable_graupel" not in patched_radar:
        raise ValueError("variable-graupel entry is missing")
    if "LOGICAL, OPTIONAL" in patched_radar.upper():
        raise ValueError("optional argument would change the legacy entry ABI")
    if "call radar_init_variable_graupel" not in patched_kdm6:
        raise ValueError("KDM6 does not select the variable-coefficient entry")
    if "DBLE((1./xam_g(k))**xobmg)" not in patched_kdm6:
        raise ValueError("wet-graupel path does not consume the local mass coefficient")

    include_args = [f"-I{compile_dir}", f"-I{HOST / 'phys'}", f"-I{HOST / 'frame'}"]
    radar_obj = compile_dir / "module_mp_radar.o"
    radar_argv = [os.environ["CLOUD_BAL_FC"], *free_flags, "-free", "-fpp", "-convert",
                  "big_endian", *include_args, "-c", str(radar_source),
                  "-o", str(radar_obj)]
    run_command(radar_argv, compile_dir, compile_dir / "radar_compile.log")

    kdm6_obj = compile_dir / "module_mp_kdm6.o"
    kdm6_argv = [os.environ["CLOUD_BAL_FC"], *free_flags, "-fpp", "-qopenmp",
                 "-convert", "big_endian", *include_args, "-free", "-c",
                 str(kdm6_source), "-o", str(kdm6_obj)]
    run_command(kdm6_argv, compile_dir, compile_dir / "kdm6_compile.log")

    before_archive = sha256(archive)
    subprocess.run(["/usr/bin/ar", "r", str(archive), str(radar_obj), str(kdm6_obj)],
                   cwd=link_dir, check=True)
    for name, obj in (("module_mp_radar.o", radar_obj), ("module_mp_kdm6.o", kdm6_obj)):
        if hashlib.sha256(archive_member(archive, name, link_dir)).hexdigest() != sha256(obj):
            raise ValueError(f"replacement archive member differs from compile output: {name}")

    nm = subprocess.run(["/usr/bin/nm", "-A", str(archive)], cwd=link_dir,
                        check=True, text=True, capture_output=True).stdout
    required_symbols = (
        "T module_mp_radar_mp_radar_init_",
        "T module_mp_radar_mp_radar_init_variable_graupel_",
        "U module_mp_radar_mp_radar_init_variable_graupel_",
    )
    missing = [symbol for symbol in required_symbols if symbol not in nm]
    if missing:
        raise ValueError(f"archive symbol contract failed: {missing}")
    if "module_mp_lin.o:                 U module_mp_radar_mp_radar_init_" not in nm:
        raise ValueError("legacy zero-argument scheme caller is absent from archive")

    pr74 = json.loads((repo / PR74_RECEIPT).read_text())
    link_argv = list(pr74["profiles"]["O0"]["actual_link"]["argv"])
    old_executable = link_argv[link_argv.index("-o") + 1]
    executable = root / "wrf.exe"
    link_argv[link_argv.index(old_executable)] = str(executable)
    link_argv.append("-qopenmp")
    run_command(link_argv, link_dir, link_dir / "link.log")
    if not any(Path(arg).name == archive.name and (link_dir / arg).resolve() == archive.resolve()
               for arg in link_argv):
        raise ValueError("linked executable did not select copied candidate archive")
    return {
        "base_archive_sha256": before_archive,
        "candidate_archive_sha256": sha256(archive),
        "candidate_executable_sha256": sha256(executable),
        "source_sha256": {"radar_original": sha256(HOST / "phys/module_mp_radar.F"),
                          "kdm6_original": sha256(SOURCE),
                          "kdm6_pr77_transformed_before_patch": EXPECTED["kdm6_transformed"],
                          "radar_patched": sha256(radar_source),
                          "kdm6_patched": sha256(kdm6_source),
                          "patch": sha256(patch_path)},
        "object_sha256": {"radar": sha256(radar_obj), "kdm6": sha256(kdm6_obj)},
        "compile_argv": {"radar": radar_argv, "kdm6": kdm6_argv},
        "link_argv": link_argv,
        "link_added_flag": "-qopenmp (required by inherited OpenMP objects; all other link inputs pinned)",
        "legacy_zero_argument_symbol_preserved": True,
        "inactive_legacy_callers_recompiled_or_run": False,
        "archive_path": str(archive),
        "executable_path": str(executable),
        "compile_directory": str(compile_dir),
        "link_directory": str(link_dir),
        "compile_logs": {"radar": sha256(compile_dir / "radar_compile.log"),
                         "kdm6": sha256(compile_dir / "kdm6_compile.log"),
                         "patch": sha256(compile_dir / "patch.log"),
                         "link": sha256(link_dir / "link.log")},
    }


def run_consumer_contract(repo: Path, root: Path, build: dict, free_flags: list[str]) -> dict:
    compile_dir = Path(build["compile_directory"])
    link_dir = Path(build["link_directory"])
    source = repo / "tests/test_kdm6_radar_graupel_consumer.f90"
    driver_obj = compile_dir / "test_kdm6_radar_graupel_consumer.o"
    compile_argv = [os.environ["CLOUD_BAL_FC"], *free_flags, "-free", "-fpp", "-convert",
                    "big_endian", f"-I{compile_dir}", f"-I{HOST / 'phys'}",
                    f"-I{HOST / 'frame'}", "-c", str(source), "-o", str(driver_obj)]
    run_command(compile_argv, compile_dir, compile_dir / "consumer_compile.log")

    pr74 = json.loads((repo / PR74_RECEIPT).read_text())
    link_argv = list(pr74["profiles"]["O0"]["actual_link"]["argv"])
    link_argv[link_argv.index("-o") + 1] = str(root / "consumer_contract.exe")
    link_argv.remove("wrf.o")
    link_argv[link_argv.index("../main/module_wrf_top.o")] = str(driver_obj)
    link_argv.append("-qopenmp")
    link_argv.append("-fpe0")
    run_command(link_argv, link_dir, link_dir / "consumer_link.log")

    consumer_dir = root / "consumer"
    consumer_dir.mkdir()
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE"})
    output_path = consumer_dir / "stdout.raw"
    result = subprocess.run([str(root / "consumer_contract.exe")], cwd=consumer_dir,
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=60, check=False)
    output_path.write_bytes(result.stdout)
    stdout = result.stdout.decode(errors="replace")
    passed = result.returncode == 0 and "KDM6_RADAR_CONSUMER_PASS" in stdout
    if not passed:
        raise RuntimeError(f"focused KDM6 radar wet-branch contract failed: {stdout[-3000:]}")
    return {
        "pass": passed,
        "scope": "actual refl10cm_kdm6 dry and wet graupel consumer with ProgB_param QG/BG state",
        "global_xam_g_before_variable_init": 0.0,
        "density_states_kg_m3": [200.0, 700.0],
        "absent_graupel_zero_coefficient_column_checked": True,
        "legacy_zero_argument_symbol_preserved": build["legacy_zero_argument_symbol_preserved"],
        "inactive_legacy_callers_recompiled_or_run": False,
        "driver_source_sha256": sha256(source),
        "driver_object_sha256": sha256(driver_obj),
        "executable_sha256": sha256(root / "consumer_contract.exe"),
        "stdout_sha256": sha256(output_path),
        "stdout": stdout[-1500:],
        "compile_argv": compile_argv,
        "compile_log_sha256": sha256(compile_dir / "consumer_compile.log"),
        "link_log_sha256": sha256(link_dir / "consumer_link.log"),
        "run_directory": str(consumer_dir),
    }


def run_candidate(repo: Path, root: Path, build: dict, receipt: dict) -> dict:
    run_dir = root / "run"
    run_dir.mkdir()
    before = stage_inputs(repo, run_dir, receipt)
    executable = Path(build["executable_path"])
    staged_executable = run_dir / "wrf.exe"
    shutil.copy2(executable, staged_executable)
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE"})
    log = run_dir / "stdout.raw"
    try:
        with log.open("wb") as output:
            result = subprocess.run([str(staged_executable)], cwd=run_dir, env=env,
                                    stdout=output, stderr=subprocess.STDOUT, timeout=900)
        status: int | str = result.returncode
    except subprocess.TimeoutExpired:
        status = "TIMEOUT_900S"
    after = {name: sha256(run_dir / name) for name in before}
    stdout = log.read_text(errors="replace")
    error_path = run_dir / "rsl.error.0000"
    error_text = error_path.read_text(errors="replace") if error_path.is_file() else ""
    markers = ("kdm6 invalid ", "kdm6 orphan ", "error stop", "forrtl: error", "fatal")
    first_failure = next((line.strip() for line in (error_text + "\n" + stdout).splitlines()
                          if any(marker in line.lower() for marker in markers)), None)
    wrf_outputs = sorted(path.name for path in run_dir.glob("wrfout_d01_*"))
    failure_text = (error_text + "\n" + stdout).lower()
    radar_xam_divide_by_zero = ("divide by zero" in failure_text and
                                ("radar_init" in failure_text or "xam_g" in failure_text))
    stack_addresses = []
    for line in error_text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "wrf.exe" and fields[1].startswith("0"):
            stack_addresses.append(fields[1])
    address_map = {}
    if stack_addresses:
        mapped = subprocess.run(["/usr/bin/addr2line", "-f", "-C", "-e",
                                 str(staged_executable), *stack_addresses],
                                check=True, text=True, capture_output=True).stdout.splitlines()
        for address, function, location in zip(stack_addresses, mapped[0::2], mapped[1::2]):
            address_map[address] = {"function": function, "source_location": location}
    return {
        "status": status,
        "first_failure_line": first_failure,
        "input_before_sha256": before,
        "input_after_sha256": after,
        "input_preservation_passed": before == after,
        "stdout_sha256": sha256(log),
        "stdout_tail": stdout[-2500:],
        "rsl_error_sha256": sha256(error_path) if error_path.is_file() else None,
        "rsl_error_tail": error_text[-3500:],
        "initial_wrf_outputs": wrf_outputs,
        "startup_passed_radar_init": bool(wrf_outputs) and not radar_xam_divide_by_zero,
        "radar_xam_divide_by_zero": radar_xam_divide_by_zero,
        "first_failure_stack_symbol_map": address_map,
        "run_directory": str(run_dir),
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    pr73 = json.loads((repo / PR73_RECEIPT).read_text())
    free_flags = os.environ["PR80_FREE_FLAGS"].splitlines()
    build = compile_candidate(repo, root, free_flags)
    consumer = run_consumer_contract(repo, root, build, free_flags)
    runtime = run_candidate(repo, root, build, pr73)
    result = {
        "schema": "kdm6_graupel_radar_contract_native_v1",
        "scope": "fresh copied partial host; fixed strict O0/no-vec Noah archive; one rank and thread",
        "baseline": {"archive_sha256": EXPECTED["base_archive"],
                     "executable_sha256": EXPECTED["base_executable"],
                     "noah_profile": "both Noah objects rebuilt together, strict O0 plus -no-vec, -fpe0 retained",
                     "fp_policy": "same gradual scalar baseline; no trap mask changes"},
        "toolchain": {"ifx_path": os.environ["CLOUD_BAL_FC"],
                      "ifx_version": subprocess.run([os.environ["CLOUD_BAL_FC"], "--version"],
                          check=True, text=True, capture_output=True).stdout.splitlines()[0]},
        "build": build,
        "focused_consumer_contract": consumer,
        "runtime": runtime,
        "coefficient_contract_scoped_pass": consumer["pass"] and
                                             build["legacy_zero_argument_symbol_preserved"] and
                                             runtime["input_preservation_passed"] and
                                             runtime["startup_passed_radar_init"],
        "limits": ["Legacy zero-argument caller symbols remain in the inherited archive; inactive schemes were not run.",
                   "Focused consumer testing verifies the compiled physical call domain; it does not establish a physical initial field or forecast.",
                   "KDM6 QG/BG/N/B state from the 12 UTC startup output is not the 13 UTC Cloud analysis state; REFL_10CM remained zero in the case run, so actual-case wet-branch consumption was not observed.",
                   "A graph refresh or successful radar_init does not establish a physical initial field or forecast."],
        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "work_root": str(root),
    }
    out = root / "kdm6_radar_contract_native.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"KDM6_RADAR_NATIVE_RECEIPT {out}")
    print(f"KDM6_RADAR_NATIVE_STATUS {runtime['status']} {runtime['first_failure_line']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
