#!/usr/bin/env python3
"""Build, bind and probe the PR84 KDM6 guard in a fresh isolated /var/tmp tree."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_member_hashes import archive_member_hashes

ROOT = Path(__file__).resolve().parents[1]
BASE_SOURCE = Path("/var/tmp/pr80_kdm6_radar_contract.nsUNuj/compile/module_mp_kdm6.F")
BASE_COMPILE = BASE_SOURCE.parent
BASE_ARCHIVE = Path("/var/tmp/pr81_native_ksas_smallstep_build1/link/main/libwrflib_pr81.a")
BASE_EXE = Path("/var/tmp/pr81_native_ksas_smallstep_build1/wrf_pr81.exe")
BASE_LINK_ARGV = Path("/var/tmp/pr81_native_ksas_smallstep_build1/link_argv.json")
BASE_LINK_CWD = Path("/var/tmp/pr81_native_ksas_smallstep_build1/link/main")
BASE_RECEIPT = Path("/var/tmp/pr81_native_ksas_smallstep_build1/pr81_native_build.json")
PATCH = ROOT / "patches/pr84_ice_entry_psd_guard.patch"
PROFILE = ROOT / "tests/intel_toolchain.sh"
MPI_VARS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh")
MPIIFX = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpiifx")
HOST_PHYS = Path("/var/tmp/pr61_ccn_origin_20261006/hostcopy/phys")
HOST_FRAME = Path("/var/tmp/pr61_ccn_origin_20261006/hostcopy/frame")
EXPECTED = {
    str(BASE_SOURCE): "a5e8ce7a05d147b05556aa7521c22c0991812711fe675409feec889e43a761e7",
    str(BASE_ARCHIVE): "ac1366ac4574e2667196cac3c960907db52aedce6dfa137178d7254fa5eb37dd",
    str(BASE_EXE): "a805a1afff42021f322337c69d4e0818faf30e677f625f9a9d1b308728b32c00",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(argv, cwd=cwd, env=env, check=True, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return completed.stdout


def profile_value(command: str) -> str:
    result = subprocess.run(["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; {command}"],
                            check=True, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    return result.stdout.strip().splitlines()[-1]


def compiler_call(argv: list[str], cwd: Path, log_path: Path, *, mpi: bool = False) -> str:
    setup = f"source {shlex.quote(str(PROFILE))}; "
    if mpi:
        setup += f"source {shlex.quote(str(MPI_VARS))}; "
    shell = setup + "exec " + " ".join(shlex.quote(x) for x in argv)
    result = subprocess.run(["bash", "-lc", shell], cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log_path.write_text(result.stdout)
    if result.returncode:
        raise SystemExit(result.stdout)
    return result.stdout


def compiler_flags(compile_dir: Path, source: Path, output: Path) -> list[str]:
    return ["-stand", "f08", "-warn", "all", "-check", "all", "-fpe0", "-traceback",
            "-O0", "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz",
            "-fpp", "-qopenmp", "-convert", "big_endian", f"-I{compile_dir}",
            f"-I{HOST_PHYS}", f"-I{HOST_FRAME}", "-free", "-c", str(source), "-o", str(output)]


def copy_fresh_tree() -> Path:
    return Path(tempfile.mkdtemp(prefix="pr84_ice_entry_guard_final_", dir="/var/tmp"))


def source_with_accessor(source_text: str) -> str:
    accessor = '''
  public :: pr84_test_dump_initialized_parameters
'''
    contains = "    contains\n"
    if contains not in source_text:
        raise SystemExit("could not locate KDM6 module CONTAINS")
    source_text = source_text.replace(contains, accessor + "\n" + contains, 1)
    end_module = "END MODULE module_mp_kdm6"
    dump = '''
  subroutine pr84_test_dump_initialized_parameters
    call kdm6init(1.0,1000.0,100.0,1004.0,1870.0,1.0e8,0,.false.)
    write(*,'(A,"|",ES24.16E3,"|",Z8.8)') 'PR84_PIDNI',pidni,transfer(pidni,0)
    write(*,'(A,"|",ES24.16E3,"|",Z8.8)') 'PR84_LAMBDA_MIN',lamdaimin,transfer(lamdaimin,0)
    write(*,'(A,"|",ES24.16E3,"|",Z8.8)') 'PR84_DMI',dmi,transfer(dmi,0)
    write(*,'(A,"|",ES24.16E3,"|",Z8.8)') 'PR84_MUI',mui,transfer(mui,0)
    write(*,'(A,"|",ES24.16E3,"|",Z8.8)') 'PR84_PI',pi,transfer(pi,0)
    write(*,'(A,"|",ES24.16E3,"|",Z8.8)') 'PR84_CMI',cmi,transfer(cmi,0)
    write(*,'(A,"|",ES24.16E3,"|",Z8.8)') 'PR84_G1PDIMI',g1pdimi,transfer(g1pdimi,0)
    write(*,'(A,"|",ES24.16E3,"|",Z8.8)') 'PR84_G1PMI',g1pmi,transfer(g1pmi,0)
  end subroutine pr84_test_dump_initialized_parameters

'''
    if end_module not in source_text:
        raise SystemExit("could not locate KDM6 END MODULE")
    return source_text.replace(end_module, dump + end_module, 1)


def parse_parameter_dump(output: str) -> dict[str, dict[str, str | float]]:
    values: dict[str, dict[str, str | float]] = {}
    for line in output.splitlines():
        fields = line.strip().split("|")
        if len(fields) == 3 and fields[0].startswith("PR84_"):
            values[fields[0][5:].lower()] = {"real32": float(fields[1]), "bits": "0x" + fields[2].upper()}
    required = {"pidni", "lambda_min", "dmi", "mui", "pi", "cmi", "g1pdimi", "g1pmi"}
    if set(values) != required:
        raise SystemExit(f"actual KDM6 initialization dump incomplete: {output}")
    return values


def main() -> None:
    for path, expected in EXPECTED.items():
        actual = sha256(Path(path))
        if actual != expected:
            raise SystemExit(f"pinned input mismatch: {path}: {actual}")
    if len(archive_member_hashes(BASE_ARCHIVE)) != 373:
        raise SystemExit("pinned PR81 archive inventory is not 373 rows")

    scratch = copy_fresh_tree()
    compile_dir = scratch / "compile"
    test_dir = scratch / "parameter_test"
    link_dir = scratch / "link" / "main"
    compile_dir.mkdir(parents=True)
    test_dir.mkdir()
    link_dir.mkdir(parents=True)
    shutil.copytree(BASE_COMPILE, compile_dir, dirs_exist_ok=True)
    shutil.copytree(BASE_COMPILE, test_dir, dirs_exist_ok=True)
    precompile_inventory = {str(path.relative_to(compile_dir)): sha256(path)
                            for path in compile_dir.rglob("*") if path.is_file()}
    external_compile_inputs = {str(path): sha256(path)
                               for directory in (HOST_PHYS, HOST_FRAME)
                               for path in directory.rglob("*") if path.is_file()
                               and path.suffix.lower() in {".mod", ".h", ".inc"}}
    source = compile_dir / "module_mp_kdm6.F"
    source.write_bytes(BASE_SOURCE.read_bytes())
    run(["patch", "-d", str(compile_dir), "-p2", "-i", str(PATCH)])
    production_source_hash = sha256(source)
    env_script = PROFILE
    ifx = Path(profile_value('printf "%s" "$CLOUD_BAL_FC"'))
    ifx_version = profile_value('"$CLOUD_BAL_FC" --version 2>&1 | sed -n "1p"')
    compiler_hash = sha256(ifx)

    compile_argv = [str(ifx), *compiler_flags(compile_dir, source, compile_dir / "module_mp_kdm6.o")]
    compile_source = compiler_call(compile_argv, compile_dir, scratch / "production_compile.log")
    production_source_snapshot = (scratch / "module_mp_kdm6.production.F")
    shutil.copy2(source, production_source_snapshot)
    compile_nul = b"\0".join(os.fsencode(x) for x in compile_argv) + b"\0"
    (scratch / "production_compile_argv.nul").write_bytes(compile_nul)
    copied_after_compile = {str(path.relative_to(compile_dir)): sha256(path)
                            for path in compile_dir.rglob("*") if path.is_file()}
    unchanged_precompile = {key: value for key, value in precompile_inventory.items()
                            if key not in {"module_mp_kdm6.F", "module_mp_kdm6.o", "module_mp_kdm6.mod"}}
    if any(copied_after_compile.get(key) != value for key, value in unchanged_precompile.items()):
        raise SystemExit("a copied compile input changed unexpectedly")
    external_compile_after = {str(path): sha256(path)
                              for directory in (HOST_PHYS, HOST_FRAME)
                              for path in directory.rglob("*") if path.is_file()
                              and path.suffix.lower() in {".mod", ".h", ".inc"}}
    if external_compile_after != external_compile_inputs:
        raise SystemExit("external compile module/header inputs changed")

    # Temporary test-only public accessor calls the actual source kdm6init and dumps saved constants.
    test_source = test_dir / "module_mp_kdm6.F"
    test_source.write_text(source_with_accessor(source.read_text()))
    test_source_hash = sha256(test_source)
    test_argv = [str(ifx), *compiler_flags(test_dir, test_source, test_dir / "module_mp_kdm6.o")]
    compiler_call(test_argv, test_dir, scratch / "parameter_accessor_compile.log")
    driver = test_dir / "pr84_parameter_dump.f90"
    driver.write_text('''program pr84_parameter_dump
  use module_mp_kdm6, only : pr84_test_dump_initialized_parameters
  implicit none
  call pr84_test_dump_initialized_parameters
end program pr84_parameter_dump
''')
    driver_obj = test_dir / "pr84_parameter_dump.o"
    driver_argv = [str(ifx), "-stand", "f08", "-warn", "all", "-check", "all", "-fpe0",
                   "-traceback", "-O0", "-fp-model", "strict", "-fimf-arch-consistency=true",
                   "-no-ftz", f"-I{test_dir}", f"-I{HOST_PHYS}", f"-I{HOST_FRAME}",
                   "-c", str(driver), "-o", str(driver_obj)]
    compiler_call(driver_argv, test_dir, scratch / "parameter_driver_compile.log")

    base_link_argv = json.loads(BASE_LINK_ARGV.read_text())
    shutil.copy2(BASE_LINK_CWD / "wrf.o", link_dir / "wrf.o")
    shutil.copy2(BASE_LINK_CWD / "module_wrf_top.o", link_dir / "module_wrf_top.o")
    base_archive_copy = link_dir / "libwrflib_pr81.a"
    shutil.copy2(BASE_ARCHIVE, base_archive_copy)
    archive = link_dir / "libwrflib_pr84.a"
    shutil.copy2(base_archive_copy, archive)
    base_rows = [name for name, _ in archive_member_hashes(base_archive_copy)]
    run(["ar", "r", str(archive), str(compile_dir / "module_mp_kdm6.o")])
    candidate_rows = [name for name, _ in archive_member_hashes(archive)]
    if base_rows != candidate_rows or len(candidate_rows) != 373:
        raise SystemExit("PR84 archive changed member order or row count")
    base_member_hashes = archive_member_hashes(base_archive_copy)
    candidate_member_hashes = archive_member_hashes(archive)
    changed_members = [{"index": n, "name": before[0], "before_sha256": before[1], "after_sha256": after[1]}
                       for n, (before, after) in enumerate(zip(base_member_hashes, candidate_member_hashes))
                       if before != after]
    if len(changed_members) != 1 or changed_members[0]["name"] != "module_mp_kdm6.o":
        raise SystemExit(f"unexpected archive member delta {changed_members}")

    # Reuse the pinned PR81 linker inputs from the new scratch working directory.
    link_argv = list(base_link_argv)
    output_slot = link_argv.index("-o") + 1
    link_argv[output_slot] = str(scratch / "wrf_pr84.exe")
    link_argv = [str(archive) if x == str(BASE_ARCHIVE) else x for x in link_argv]
    link_argv = [str(link_dir / "wrf.o") if x == "wrf.o" else x for x in link_argv]
    link_argv = [str(link_dir / "module_wrf_top.o") if x == "module_wrf_top.o" else x for x in link_argv]
    link_dependencies = {}
    search_dirs = [Path(x[2:]) for x in link_argv if x.startswith("-L")]
    for index, item in enumerate(link_argv):
        candidate = Path(item) if Path(item).is_absolute() else link_dir / item
        if candidate.is_file():
            link_dependencies[str(candidate)] = sha256(candidate)
        if item.startswith("-l"):
            lib = item[2:]
            matches = [directory / filename for directory in search_dirs
                       for filename in (f"lib{lib}.so", f"lib{lib}.a", f"lib{lib}.so.5")
                       if (directory / filename).is_file()]
            for match in matches:
                link_dependencies[str(match)] = sha256(match)
    link_argv_nul = b"\0".join(os.fsencode(x) for x in link_argv) + b"\0"
    (scratch / "production_link_argv.nul").write_bytes(link_argv_nul)
    compiler_call(link_argv, scratch, scratch / "production_link.log", mpi=True)

    # Test-only module source links into the candidate archive without wrf.o/main and runs only kdm6init.
    main_object_index = base_link_argv.index("wrf.o")
    archive_index = base_link_argv.index(str(BASE_ARCHIVE))
    test_link_argv = [str(MPIIFX), "-o", str(scratch / "parameter_dump.exe"),
                      *base_link_argv[3:main_object_index], str(driver_obj),
                      str(test_dir / "module_mp_kdm6.o"), str(archive),
                      *base_link_argv[archive_index + 1:]]
    test_link_dependencies = dict(link_dependencies)
    test_link_dependencies[str(driver_obj)] = sha256(driver_obj)
    test_link_dependencies[str(test_dir / "module_mp_kdm6.o")] = sha256(test_dir / "module_mp_kdm6.o")
    test_link_dependencies[str(archive)] = sha256(archive)
    (scratch / "parameter_link_argv.nul").write_bytes(b"\0".join(os.fsencode(x) for x in test_link_argv) + b"\0")
    compiler_call(test_link_argv, scratch, scratch / "parameter_link.log", mpi=True)
    runtime_libs = "/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib:/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib:/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/lib"
    dump_run = subprocess.run(["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; source {shlex.quote(str(MPI_VARS))}; export LD_LIBRARY_PATH={shlex.quote(runtime_libs)}:${{LD_LIBRARY_PATH-}}; exec {shlex.quote(str(scratch / 'parameter_dump.exe'))}"],
                              cwd=scratch, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    dump = dump_run.stdout
    (scratch / "actual_parameter_dump.txt").write_text(dump)
    params = parse_parameter_dump(dump)
    ldd_run = subprocess.run(["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; source {shlex.quote(str(MPI_VARS))}; export LD_LIBRARY_PATH={shlex.quote(runtime_libs)}:${{LD_LIBRARY_PATH-}}; ldd {shlex.quote(str(scratch / 'parameter_dump.exe'))}"],
                            cwd=scratch, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    runtime_ldd = ldd_run.stdout
    if "not found" in runtime_ldd:
        raise SystemExit(f"parameter accessor has unresolved runtime dependency: {runtime_ldd}")
    (scratch / "parameter_runtime_dependencies.txt").write_text(runtime_ldd)
    if params["pidni"]["bits"] != "0x44C4597C" or params["lambda_min"]["bits"] != "0x460DE000":
        raise SystemExit(f"KDM6 actual initialized parameters differ from contract: {params}")

    # Compile the exact marked helper body extracted from the production patched source.
    body = source.read_text().split("    ! PR84_KDM6_ICE_ENTRY_CEILING_BEGIN\n", 1)[1].split(
        "    ! PR84_KDM6_ICE_ENTRY_CEILING_END", 1)[0]
    probe_module = compile_dir / "pr84_helper_probe.F90"
    probe_module.write_text("module pr84_probe_module\n  implicit none\ncontains\n" + body + "end module\n")
    pidni_literal = format(float(params["pidni"]["real32"]), ".17g")
    lambda_literal = format(float(params["lambda_min"]["real32"]), ".17g")
    probe_driver = compile_dir / "pr84_helper_probe_driver.F90"
    probe_driver.write_text(f'''program pr84_helper_probe_driver
  use, intrinsic :: ieee_arithmetic, only : ieee_value, ieee_quiet_nan
  use pr84_probe_module, only : pr84_ice_entry_ceiling
  implicit none
  real :: cap, rho, qi, lam, shape, pidni, candidate, reconstructed, qn_min
  logical :: ok
  integer :: failures
  failures = 0
  rho = 0.6824867725372314
  lam = {lambda_literal}
  shape = 3.0
  pidni = {pidni_literal}
  call pr84_ice_entry_ceiling(0.0, rho, lam, shape, pidni, cap, ok)
  call check(ok .and. cap == 1.0e6, 'zero-QI floor')
  call pr84_ice_entry_ceiling(1.0e-4, rho, lam, shape, pidni, cap, ok)
  call check(ok .and. cap == 1.0e6, 'low-IWC cap')
  qi = 0.0033685904927551746
  call pr84_ice_entry_ceiling(qi, rho, lam, shape, pidni, cap, ok, qn_min)
  call check(ok .and. cap > 1.0e6, 'actual high-IWC floor')
  print '(a,1x,z8.8,1x,z8.8,1x,es16.8)', 'ACTUAL_HIGH_QN_CAP', transfer(qn_min,0), transfer(cap,0), cap
  candidate = cap
  reconstructed = exp(log((pidni*candidate)/(rho*qi))*(1.0/shape))
  call check(reconstructed >= lam, 'source lambda_min reconstruction')
  call check(min(max(cap,0.0),cap) == cap, 'source-valid high-IWC NI is retained')
  call check(qi == 0.0033685904927551746, 'QI unchanged')
  call pr84_ice_entry_ceiling(1.0, rho, lam, 2.5, pidni, cap, ok)
  call check(ok .and. cap > 1.0e6, 'fractional source shape exponent')
  call pr84_ice_entry_ceiling(0.0007856728043407202,0.4555096924304962,lam,shape,pidni,cap,ok,qn_min)
  call check(ok .and. cap == 1.0e6, 'one-ULP case retains fixed cap')
  call check(transfer(qn_min,0) == int(z'48B6D4B2'), 'one-ULP public roundtrip advances once')
  print '(a,1x,z8.8,1x,z8.8)', 'ONE_ULP_QN_CAP', transfer(qn_min,0), transfer(cap,0)
  call pr84_ice_entry_ceiling(6.6648876781982835e-6,0.750110387802124,lam,shape,pidni,cap,ok,qn_min)
  call check(ok .and. cap == 1.0e6, 'low-IWC fixture retains fixed cap')
  print '(a,1x,z8.8,1x,z8.8,1x,es16.8)', 'LOW_FIXTURE_QN_CAP', transfer(qn_min,0), transfer(cap,0), cap
  call pr84_ice_entry_ceiling(1.0e-3,0.0,lam,shape,pidni,cap,ok)
  call check(.not. ok .and. cap == 0.0, 'invalid density fails closed')
  call pr84_ice_entry_ceiling(ieee_value(0.0,ieee_quiet_nan),rho,lam,shape,pidni,cap,ok)
  call check(.not. ok .and. cap == 0.0, 'nonfinite QI fails closed')
  if (failures /= 0) error stop 1
  print '(a)', 'PR84 helper cases PASS'
contains
  subroutine check(condition, label)
    logical, intent(in) :: condition
    character(len=*), intent(in) :: label
    if (.not. condition) then
      failures = failures + 1
      print '(a)', 'FAIL: '//label
    endif
  end subroutine check
end program pr84_helper_probe_driver
''')
    probe_argv = [str(ifx), "-stand", "f08", "-warn", "all", "-check", "all", "-fpe0", "-traceback",
                  "-O0", "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz",
                  str(probe_module), str(probe_driver), "-o", str(compile_dir / "pr84_helper_probe.exe")]
    compiler_call(probe_argv, compile_dir, scratch / "helper_probe_compile.log")
    probe_run = subprocess.run(["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; exec {shlex.quote(str(compile_dir / 'pr84_helper_probe.exe'))}"],
                               cwd=scratch, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    probe_output = probe_run.stdout
    (scratch / "focused_probe.log").write_text(probe_output)
    if "PR84 helper cases PASS" not in probe_output:
        raise SystemExit(f"focused helper probe failed: {probe_output}")

    test_compile_nul = b"\0".join(os.fsencode(x) for x in test_argv) + b"\0"
    driver_compile_nul = b"\0".join(os.fsencode(x) for x in driver_argv) + b"\0"
    test_link_nul = b"\0".join(os.fsencode(x) for x in test_link_argv) + b"\0"
    (scratch / "parameter_accessor_compile_argv.nul").write_bytes(test_compile_nul)
    (scratch / "parameter_driver_compile_argv.nul").write_bytes(driver_compile_nul)
    (scratch / "parameter_link_argv.nul").write_bytes(test_link_nul)
    setvars_path = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh")
    receipt = {
        "schema": "pr84_native_ice_entry_guard_build_v2",
        "scratch": str(scratch), "model_run": False,
        "input_sha256": EXPECTED,
        "patch_sha256": sha256(PATCH), "builder_sha256": sha256(Path(__file__)),
        "profile": {"path": str(PROFILE), "sha256": sha256(PROFILE), "ifx": str(ifx),
                    "ifx_version": ifx_version, "ifx_sha256": compiler_hash,
                    "setvars": str(setvars_path), "setvars_sha256": sha256(setvars_path),
                    "mpi_vars": str(MPI_VARS), "mpi_vars_sha256": sha256(MPI_VARS),
                    "mpiifx": str(MPIIFX), "mpiifx_sha256": sha256(MPIIFX),
                    "base_link_metadata": str(BASE_RECEIPT), "base_link_metadata_sha256": sha256(BASE_RECEIPT),
                    "base_link_argv_json": str(BASE_LINK_ARGV), "base_link_argv_json_sha256": sha256(BASE_LINK_ARGV),
                    "compile_optimization": "-O0 audit profile; inherits exact PR80 KDM6 build flags",
                    "preprocessor_defines": []},
        "production_source_sha256": production_source_hash,
        "production_object_sha256": sha256(compile_dir / "module_mp_kdm6.o"),
        "production_module_sha256": sha256(compile_dir / "module_mp_kdm6.mod"),
        "production_compile_argv": compile_argv,
        "production_compile_argv_nul_sha256": sha256_bytes(compile_nul),
        "precompile_copy_inventory_sha256": precompile_inventory,
        "external_compile_input_sha256": external_compile_inputs,
        "external_compile_inputs_unchanged": external_compile_after == external_compile_inputs,
        "precompile_dependencies_unchanged": all(copied_after_compile.get(k) == v for k, v in unchanged_precompile.items()),
        "test_accessor": {"runtime_library_path": runtime_libs,
                          "source_sha256": test_source_hash, "object_sha256": sha256(test_dir / "module_mp_kdm6.o"),
                          "compile_argv": test_argv, "compile_argv_nul_sha256": sha256_bytes(test_compile_nul),
                          "driver_sha256": sha256(driver), "driver_object_sha256": sha256(driver_obj),
                          "driver_compile_argv": driver_argv, "driver_compile_argv_nul_sha256": sha256_bytes(driver_compile_nul),
                          "executable_sha256": sha256(scratch / "parameter_dump.exe"),
                          "actual_kdm6init_output": params, "actual_parameter_dump_stdout_sha256": sha256_bytes(dump.encode()),
                          "runtime_dependencies": runtime_ldd},
        "native_source_parameters": params,
        "ordered_archive_rows": len(candidate_rows), "archive_order_unchanged": base_rows == candidate_rows,
        "ordered_archive_member_hashes_base": base_member_hashes,
        "ordered_archive_member_hashes_candidate": candidate_member_hashes,
        "changed_archive_members": changed_members,
        "candidate_archive_sha256": sha256(archive),
        "production_executable_sha256": sha256(scratch / "wrf_pr84.exe"),
        "production_link_dependencies_sha256": link_dependencies,
        "test_link_dependencies_sha256": test_link_dependencies,
        "production_link_argv": link_argv,
        "production_link_argv_nul_sha256": sha256_bytes(link_argv_nul),
        "parameter_test_link_argv": test_link_argv,
        "parameter_test_link_argv_nul_sha256": sha256_bytes(test_link_nul),
        "helper_probe_stdout": probe_output,
        "source_input_fixture": {"wrf_ijk": [195,73,17], "qi_real32": 0.0033685904927551746,
                                  "qi_bits": "0x3B5CC392", "source_rho_real32": 0.6824867725372314,
                                  "source_rho_bits": "0x3F2EB774"},
    }
    receipt_path = scratch / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
