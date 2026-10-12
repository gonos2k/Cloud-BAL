#!/usr/bin/env python3
"""Build once, then compare two FP choices on identical PR77 native inputs."""

from __future__ import annotations

import hashlib
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from pr76_native_fp_run import checked_hash, compile_profile, sha256
from pr78_native_fp_runtime_choice import transform_host_main, transform_kdm6


PR73_PATH = "docs/evidence/pr73_native_first_violation_20261008_attempt2/native_receipt.json"
PR74_PATH = "docs/evidence/pr74_shinhong_qni_driver_20261008.json"
SOURCE = "/var/tmp/pr73_native_first_violation.x3bvfn/build/source/module_mp_kdm6.f90"
HOST_MAIN = "/var/tmp/pr61_ccn_origin_20261006/hostcopy/main/wrf.f90"
NOAH_FK_ANCHOR = "              FK=(( (HLICE/(GRAV*(-PSISAT))) *                              &\n"


def add_noah_operand_observer(source: str) -> str:
    module_anchor = "MODULE module_sf_noahdrv\n"
    if not source.startswith(module_anchor) or source.count(NOAH_FK_ANCHOR) != 1:
        raise ValueError("Noah driver source does not match the pinned FK expression anchor")
    source = source.replace(
        module_anchor,
        module_anchor + "USE, INTRINSIC :: ieee_arithmetic, only : ieee_is_finite\n",
        1,
    )
    observer = """              BLOCK
                INTEGER :: PR78_UNIT, PR78_IOS
                LOGICAL :: PR78_FINITE, PR78_NONPOSITIVE_BASE
                PR78_FINITE = ieee_is_finite(TSLB(I,NS,J)) .AND. &
                     ieee_is_finite(T0) .AND. ieee_is_finite(BX) .AND. &
                     ieee_is_finite(PSISAT) .AND. ieee_is_finite(SMCMAX) .AND. &
                     ieee_is_finite(HLICE) .AND. ieee_is_finite(GRAV)
                PR78_NONPOSITIVE_BASE = .FALSE.
                IF (PR78_FINITE) THEN
                  IF (TSLB(I,NS,J) > 0.0 .AND. PSISAT /= 0.0) THEN
                    IF (PSISAT > 0.0 .AND. TSLB(I,NS,J) >= T0) &
                         PR78_NONPOSITIVE_BASE = .TRUE.
                    IF (PSISAT < 0.0 .AND. TSLB(I,NS,J) <= T0) &
                         PR78_NONPOSITIVE_BASE = .TRUE.
                  END IF
                END IF
                OPEN(NEWUNIT=PR78_UNIT, FILE='pr78_noah_fk_operands.raw', &
                     STATUS='UNKNOWN', POSITION='APPEND', ACTION='WRITE', IOSTAT=PR78_IOS)
                IF (PR78_IOS == 0) THEN
                  WRITE(PR78_UNIT,'(A,3(",",I0),7(",",ES24.16E3),2(",",L1),7(",",Z8.8))') &
                       'PR78_NOAH_FK', I, NS, J, TSLB(I,NS,J), T0, BX, PSISAT, &
                       SMCMAX, HLICE, GRAV, PR78_FINITE, PR78_NONPOSITIVE_BASE, &
                       TRANSFER(TSLB(I,NS,J),0), TRANSFER(T0,0), TRANSFER(BX,0), &
                       TRANSFER(PSISAT,0), TRANSFER(SMCMAX,0), TRANSFER(HLICE,0), &
                       TRANSFER(GRAV,0)
                  FLUSH(PR78_UNIT)
                  CLOSE(PR78_UNIT)
                END IF
              END BLOCK
"""
    return source.replace(NOAH_FK_ANCHOR, observer + NOAH_FK_ANCHOR, 1)


def copy_inputs(run_dir: Path, pr73: dict) -> dict[str, str]:
    hashes = {}
    for entry in pr73["input_hashes_before_after"]:
        original = Path(entry["path"])
        if original.name == "wrf.exe":
            continue
        if sha256(original) != entry["sha256_before"]:
            raise ValueError(f"protected input changed before staging: {original}")
        staged = run_dir / original.name
        if staged.name in hashes:
            raise ValueError(f"duplicate staged input basename: {staged.name}")
        shutil.copy2(original, staged)
        hashes[staged.name] = sha256(staged)
    return hashes


def build_once(repo: Path, work: Path, pr73: dict, pr74: dict,
               ifx: Path, icx: Path, flags: list[str]) -> dict:
    source = Path(SOURCE)
    archive_source = Path(pr74["profiles"]["O0"]["archive_path"])
    host_source = Path(HOST_MAIN)
    pins = {
        "pr73_receipt": repo / PR73_PATH,
        "archive_receipt_source": Path(pr73["build_artifacts"]["archive_path"]),
        "kdm6_source": source,
        "native_archive_o0": archive_source,
        "host_main_source": host_source,
    }
    for name in ("pr73_receipt", "kdm6_source", "native_archive_o0"):
        checked_hash(name, pins[name])
    if sha256(host_source) != "1ed575364433b64749086edee3a64b317febefbac9eb1a8c72011d13a69627ca":
        raise ValueError("native main source differs from retained host source")

    compile_dir = work / "compile"
    link_dir = work / "build/link/main"
    compile_dir.mkdir(parents=True)
    link_dir.mkdir(parents=True)
    shutil.copytree(archive_source.parent, link_dir, dirs_exist_ok=True, copy_function=shutil.copy2)
    archive = link_dir / archive_source.name
    generated = compile_dir / "module_mp_kdm6.f90"
    generated.write_text(transform_kdm6(source.read_text()))
    main_source = compile_dir / "wrf.f90"
    main_source.write_text(transform_host_main(host_source.read_text()))

    include_args = ["-I/var/tmp/pr61_ccn_origin_20261006/hostcopy/phys",
                    "-I/var/tmp/pr61_ccn_origin_20261006/hostcopy/frame"]
    compile_argv = [str(ifx), *flags, "-fpp", "-qopenmp", "-convert", "big_endian",
                    *include_args, "-free", "-c", str(generated)]
    pinned_compile_argv = pr73["build_artifacts"]["compile_argv"]
    prefix = compile_argv[:compile_argv.index("-c")]
    additions = {"-fpp", "-qopenmp"}
    if [arg for arg in prefix if arg not in additions] != pinned_compile_argv[:pinned_compile_argv.index("-c")]:
        raise ValueError("KDM6 compile options differ from pinned O0 profile outside recorded additions")
    helper = repo / "tests/pr76_native_fp_policy.c"
    helper_object = compile_dir / "pr76_native_fp_policy.o"
    helper_argv = [str(icx), "-O0", "-c", str(helper), "-o", str(helper_object)]
    main_includes = [arg for arg in pr74["profiles"]["O0"]["compile_argv"][1]
                     if arg.startswith("-I")]
    main_object = link_dir / "wrf.o"
    main_argv = [str(ifx), *flags, "-qopenmp", "-free", *main_includes,
                 "-c", str(main_source), "-o", str(main_object)]
    preprocessed_source = compile_dir / "module_mp_kdm6.preprocessed.f90"
    preprocess_argv = [str(ifx), *flags, "-fpp", "-qopenmp", "-E", "-convert",
                       "big_endian", *include_args, "-free", str(generated)]
    with preprocessed_source.open("wb") as output, (compile_dir / "preprocess.log").open("wb") as log:
        subprocess.run(preprocess_argv, cwd=compile_dir, check=True, stdout=output,
                       stderr=log)
    with (compile_dir / "compile.log").open("wb") as log:
        subprocess.run(compile_argv, cwd=compile_dir, check=True, stdout=log,
                       stderr=subprocess.STDOUT)
        subprocess.run(helper_argv, cwd=compile_dir, check=True, stdout=log,
                       stderr=subprocess.STDOUT)
    with (compile_dir / "main_compile.log").open("wb") as log:
        subprocess.run(main_argv, cwd=compile_dir, check=True, stdout=log,
                       stderr=subprocess.STDOUT)

    object_hashes = {"module_mp_kdm6.o": sha256(compile_dir / "module_mp_kdm6.o"),
                     "pr76_native_fp_policy.o": sha256(helper_object),
                     "wrf.o": sha256(main_object)}
    subprocess.run(["/usr/bin/ar", "r", str(archive), str(compile_dir / "module_mp_kdm6.o"),
                    str(helper_object)], cwd=link_dir, check=True)
    for member in ("module_mp_kdm6.o", "pr76_native_fp_policy.o"):
        payload = subprocess.run(["/usr/bin/ar", "p", str(archive), member], cwd=link_dir,
                                 check=True, capture_output=True).stdout
        if hashlib.sha256(payload).hexdigest() != object_hashes[member]:
            raise ValueError(f"archive payload differs from compiled object: {member}")

    inherited = list(pr74["profiles"]["O0"]["actual_link"]["argv"])
    link_argv = list(inherited)
    executable = work / "wrf.exe"
    old_output = link_argv[2]
    link_argv[link_argv.index(old_output)] = str(executable)
    link_argv.append("-qopenmp")
    normalized_link_argv = link_argv[:-1]
    normalized_link_argv[normalized_link_argv.index(str(executable))] = old_output
    if normalized_link_argv != inherited:
        raise ValueError("link arguments changed beyond scratch output and recorded OpenMP flag")
    with (link_dir / "link.log").open("wb") as log:
        subprocess.run(link_argv, cwd=link_dir, check=True, stdout=log, stderr=subprocess.STDOUT)
    if not any(Path(arg).name == archive.name and (link_dir / arg).resolve() == archive.resolve()
               for arg in link_argv):
        raise ValueError("linked executable did not select the copied diagnostic archive")
    return {
        "pins": {name: {"path": str(path), "sha256": sha256(path)} for name, path in pins.items()},
        "sources": {"kdm6_transformed_sha256": sha256(generated),
                    "host_main_transformed_sha256": sha256(main_source),
                    "kdm6_preprocessed_sha256": sha256(preprocessed_source),
                    "preprocessor_macros": [arg for arg in preprocess_argv if arg.startswith("-D")]},
        "objects_sha256": object_hashes,
        "archive": {"path": str(archive), "sha256": sha256(archive)},
        "link_directory": str(link_dir),
        "executable": {"path": str(executable), "sha256": sha256(executable)},
        "compile_argv": compile_argv,
        "preprocess_argv": preprocess_argv,
        "main_compile_argv": main_argv,
        "helper_compile_argv": helper_argv,
        "link_argv": link_argv,
        "log_sha256": {"preprocess": sha256(compile_dir / "preprocess.log"),
                       "compile": sha256(compile_dir / "compile.log"),
                       "main_compile": sha256(compile_dir / "main_compile.log"),
                       "link": sha256(link_dir / "link.log")},
        "link_arguments_match_inherited_except_output_and_openmp": True,
    }


def parse_fp_trace(text: str, mode: str, expected_threads: int) -> dict:
    rows = [row.split(",") for row in text.splitlines() if row]
    parsed = []
    for row in rows:
        if len(row) != 5 or row[0] != "PR77_HOST_FP":
            raise ValueError(f"malformed startup FP record: {row}")
        before, after, thread = int(row[2], 16), int(row[3], 16), int(row[4])
        if thread <= 0:
            raise ValueError("invalid Linux thread id in FP record")
        if mode == "PRESERVE" and after != before:
            raise ValueError("PRESERVE changed MXCSR")
        if mode == "CLEAR_FTZ_DAZ" and after != (before & ~0x8040):
            raise ValueError("CLEAR_FTZ_DAZ changed MXCSR outside FTZ/DAZ")
        parsed.append({"stage": row[1], "before": f"0x{before:08X}",
                       "after": f"0x{after:08X}", "thread_id": thread})
    main = [row for row in parsed if row["stage"] == "MAIN_STARTUP"]
    team = [row for row in parsed if row["stage"] == "OMP_STARTUP_TEAM"]
    if len(main) != 1 or len(team) != expected_threads or len({r["thread_id"] for r in team}) != expected_threads:
        raise ValueError("startup main and expected OpenMP team were not completely observed")
    return {"records": parsed, "main_thread_id": main[0]["thread_id"],
            "startup_team_size": len(team), "only_ftz_daz_choice_applied": True}


def parse_noah_operand_trace(text: str) -> list[dict]:
    parsed = []
    for line in text.splitlines():
        row = line.split(",")
        if len(row) != 20 or row[0] != "PR78_NOAH_FK":
            raise ValueError(f"malformed Noah operand record: {row}")
        values = [float(value) for value in row[4:11]]
        tslb, t0, bx, psisat, smcmax, hlice, grav = values
        record = {
            "i": int(row[1]), "soil_layer": int(row[2]), "j": int(row[3]),
            "tslb": tslb, "t0": t0, "bx": bx, "psisat": psisat,
            "smcmax": smcmax, "hlice": hlice, "grav": grav,
            "all_operands_finite": row[11].strip().upper() == "T",
            "base_nonpositive_by_sign": row[12].strip().upper() == "T",
            "binary32_bits": {name: value.strip().upper()
                              for name, value in zip(
                                  ("tslb", "t0", "bx", "psisat", "smcmax", "hlice", "grav"),
                                  row[13:20])},
        }
        if (record["all_operands_finite"] and tslb > 0 and grav != 0 and psisat != 0):
            coefficient = hlice / (grav * -psisat)
            ratio = (tslb - t0) / tslb
            base = coefficient * ratio
            record["base_from_captured_values"] = base
            record["coefficient_from_captured_values"] = coefficient
            record["temperature_ratio_from_captured_values"] = ratio
            record["base_sign_matches_observer"] = (base <= 0) == record["base_nonpositive_by_sign"]
        parsed.append(record)
    return parsed


def run_case(root: Path, mode: str, executable: Path, expected_inputs: dict,
             pr74: dict) -> dict:
    case = root / mode.lower()
    run_dir = case / "run"
    run_dir.mkdir(parents=True)
    inputs = copy_inputs(run_dir, {"input_hashes_before_after": [
        {"path": path, "sha256_before": digest}
        for path, digest in expected_inputs.items()]})
    exe = run_dir / "wrf.exe"
    shutil.copy2(executable, exe)
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE", "PR78_FP_MODE": mode})
    log_path = run_dir / "stdout.raw"
    with log_path.open("wb") as log:
        try:
            process = subprocess.run([str(exe)], cwd=run_dir, env=env, stdout=log,
                                     stderr=subprocess.STDOUT, timeout=900)
            status: int | str = process.returncode
        except subprocess.TimeoutExpired:
            status = "TIMEOUT_900S"
    after = {name: sha256(run_dir / name) for name in inputs}
    startup_trace = run_dir / "pr77_host_fp.raw"
    startup_check = parse_fp_trace(startup_trace.read_text(), mode, 1) if startup_trace.is_file() else None
    entry_trace = run_dir / "pr76_thread_entry.raw"
    kdm6_entry = entry_trace.read_text(errors="replace") if entry_trace.is_file() else None
    required = pr74["profiles"]["O0"]["required_post_call_outputs"]
    missing = [name for name in required if not (run_dir / name).is_file()]
    error_log = run_dir / "rsl.error.0000"
    stdout = log_path.read_text(errors="replace")
    errtext = error_log.read_text(errors="replace") if error_log.is_file() else ""
    failure_markers = ("kdm6 invalid ", "kdm6 orphan ", "error stop", "fatal", "forrtl: error")
    first_failure = next((line.strip() for line in (errtext + "\n" + stdout).splitlines()
                          if any(marker in line.lower() for marker in failure_markers)), None)
    return {
        "mode": mode, "run_exit_status": status, "first_failure_line": first_failure,
        "same_executable_sha256": sha256(exe), "inputs_before": inputs,
        "inputs_after": after, "input_preservation_passed": inputs == after,
        "startup_fp_choice_check": startup_check,
        "kdm6_entry_trace": kdm6_entry,
        "native_species_trace": ((run_dir / "pr77_native_species.raw").read_text(errors="replace")
                                 if (run_dir / "pr77_native_species.raw").is_file() else None),
        "required_post_call_outputs": required, "missing_post_call_outputs": missing,
        "rsl_error_sha256": sha256(error_log) if error_log.is_file() else None,
        "rsl_error_tail": errtext[-3000:],
        "stdout_sha256": sha256(log_path), "stdout_tail": stdout[-3000:],
        "run_directory": str(run_dir),
    }


def debug_noah_diagnostic(root: Path, build: dict, pr73: dict, pr74: dict,
                          ifx: Path, mode: str = "PRESERVE") -> dict:
    """Rebuild only the inherited Noah driver with line tables, then stop at SIGFPE."""
    gdb = shutil.which("gdb")
    if not gdb:
        return {"status": "UNAVAILABLE", "reason": "gdb not installed"}
    host_root = Path("/var/tmp/pr61_ccn_origin_20261006/hostcopy")
    sources = [host_root / "phys/module_sf_noahlsm.f90",
               host_root / "phys/module_sf_noahdrv.f90"]
    if not all(source.is_file() for source in sources):
        return {"status": "SOURCE_UNAVAILABLE",
                "source_paths": [str(source) for source in sources]}
    case = root / "noah_strict_diagnostic"
    link_dir = case / "build/link/main"
    link_dir.mkdir(parents=True)
    original_link_dir = Path(build["link_directory"])
    shutil.copytree(original_link_dir, link_dir, dirs_exist_ok=True, copy_function=shutil.copy2)
    archive = link_dir / Path(pr74["profiles"]["O0"]["archive_path"]).name
    original_objects = {}
    for source in sources:
        object_name = f"{source.stem}.o"
        archived = subprocess.run(["/usr/bin/ar", "p", str(archive), object_name],
                                   cwd=link_dir, check=True, capture_output=True).stdout
        object_path = host_root / "phys" / object_name
        if hashlib.sha256(archived).hexdigest() != sha256(object_path):
            raise ValueError(f"source host object and selected archive member differ: {object_name}")
        original_objects[object_name] = sha256(object_path)
    archive_before = sha256(archive)
    compile_dir = case / "compile"
    compile_dir.mkdir()
    compile_log = compile_dir / "noah_debug_compile.raw"
    object_paths = []
    compile_argvs = []
    with compile_log.open("wb") as log:
        for source in sources:
            object_path = compile_dir / f"{source.stem}.o"
            compile_argv = [str(ifx), "-g", "-c", "-O3", "-ip", "-fp-model", "precise",
                            "-w", "-ftz", "-align", "all", "-fno-alias", "-FR",
                            "-convert", "big_endian",
                            f"-I{host_root / 'dyn_em'}",
                            f"-I{host_root / 'external/esmf_time_f90'}",
                            f"-I{host_root / 'main'}",
                            f"-I{host_root / 'external/io_netcdf'}",
                            f"-I{host_root / 'external/io_int'}",
                            f"-I{host_root / 'frame'}", f"-I{host_root / 'share'}",
                            f"-I{host_root / 'phys'}", f"-I{host_root / 'wrftladj'}",
                            f"-I{host_root / 'chem'}", f"-I{host_root / 'inc'}",
                            "-I/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel/include",
                            "-I/include", "-real-size", "32", "-i4", str(source),
                            "-o", str(object_path)]
            subprocess.run(compile_argv, cwd=compile_dir, check=True, stdout=log,
                           stderr=subprocess.STDOUT)
            object_paths.append(object_path)
            compile_argvs.append(compile_argv)
    subprocess.run(["/usr/bin/ar", "r", str(archive), *map(str, object_paths)],
                   cwd=link_dir, check=True)
    executable = case / "wrf_noah_debug.exe"
    link_argv = list(build["link_argv"])
    old_executable = build["executable"]["path"]
    link_argv[link_argv.index(old_executable)] = str(executable)
    diag_link_argv = link_argv[:-1]
    diag_link_argv[diag_link_argv.index(str(executable))] = old_executable
    if diag_link_argv != build["link_argv"][:-1]:
        raise ValueError("strict diagnostic changed inherited link inputs")
    with (link_dir / "noah_debug_link.raw").open("wb") as log:
        subprocess.run(link_argv, cwd=link_dir, check=True, stdout=log,
                       stderr=subprocess.STDOUT)
    run_dir = case / "run"
    run_dir.mkdir(parents=True)
    copy_inputs(run_dir, pr73)
    exe = run_dir / "wrf.exe"
    shutil.copy2(executable, exe)
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE", "PR78_FP_MODE": mode})
    argv = [gdb, "--batch", "-ex", "set debuginfod enabled off",
            "-ex", "handle SIGFPE stop print pass", "-ex", "run",
            "-ex", "frame 0", "-ex", "info locals", "-ex", "p i", "-ex", "p ns",
            "-ex", "p j", "-ex", "p bx", "-ex", "p smcmax", "-ex", "p psisat",
            "-ex", "p t0", "-ex", "p tslb(i,ns,j)", "-ex", "bt 32",
            "-ex", "info registers mxcsr", "--args", str(exe)]
    result = subprocess.run(argv, cwd=run_dir, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    trace = run_dir / "gdb_noah_invalid.raw"
    trace.write_text(result.stdout)
    source_lines = sources[1].read_text().splitlines()
    excerpt = [{"line": number, "text": source_lines[number - 1]}
               for number in range(1839, 1842)]
    operand_names = ["I", "NS", "J", "TSLB(I,NS,J)", "T0", "BX", "SMCMAX", "PSISAT"]
    observer = run_noah_operand_observer(case, link_dir, archive, executable, link_argv,
                                         compile_dir, compile_argvs[1], sources[1],
                                         pr73, mode)
    return {"status": "TRAP_CAPTURED" if "Program received signal SIGFPE" in result.stdout else "NO_SIGFPE_CAPTURED",
            "exit_status": result.returncode, "argv": argv, "thread_count": 1,
            "runtime_fp_mode": mode, "trap_delivery": "SIGFPE stop print pass; debugger records stack before delivery",
            "trace_path": str(trace), "trace_sha256": sha256(trace),
            "trace_text": result.stdout[-10000:],
            "debug_symbols_or_source_line_available": any(f"{source.name}:" in result.stdout for source in sources),
            "noah_sources": [{"path": str(source), "sha256": sha256(source)} for source in sources],
            "noah_objects": [{"path": str(path), "sha256": sha256(path)} for path in object_paths],
            "noah_original_objects_sha256": original_objects,
            "diagnostic_archive_sha256_before": archive_before,
            "diagnostic_archive_sha256_after": sha256(archive),
            "diagnostic_optimization": "original host -O3 -ip -fp-model precise -ftz plus -g; inherited non-Noah objects stay unchanged",
            "trap_source_excerpt": excerpt,
            "operand_capture": {"requested": operand_names,
                                "gdb_queries": ["info locals", *[f"p {name.lower()}" for name in operand_names]],
                                "limitation": "O3 optimized most scalar operands out of GDB locals; captured output retains each query result"},
            "debug_compile_argv": compile_argvs,
            "debug_compile_log_sha256": sha256(compile_log),
            "diagnostic_executable_sha256": sha256(executable),
            "physics_scheme_or_lsm_changed": False,
            "fpe_trap_policy_changed": False,
            "operand_observer": observer}


def run_noah_operand_observer(case: Path, link_dir: Path, archive: Path,
                              executable: Path, link_argv: list[str], compile_dir: Path,
                              base_compile_argv: list[str], source: Path,
                              pr73: dict, mode: str) -> dict:
    """Run an observer-only Noah source copy in its own one-thread strict build."""
    observer_root = case / "operand_observer"
    observer_link = observer_root / "build/link/main"
    observer_link.mkdir(parents=True)
    shutil.copytree(link_dir, observer_link, dirs_exist_ok=True, copy_function=shutil.copy2)
    observer_archive = observer_link / archive.name
    observed_source = compile_dir / "module_sf_noahdrv_observed.f90"
    observed_source.write_text(add_noah_operand_observer(source.read_text()))
    source_diff = compile_dir / "module_sf_noahdrv_observer.diff"
    source_diff.write_text("".join(difflib.unified_diff(
        source.read_text().splitlines(keepends=True),
        observed_source.read_text().splitlines(keepends=True),
        fromfile=str(source), tofile=str(observed_source))))
    observed_object = compile_dir / "module_sf_noahdrv_observed.o"
    compile_argv = list(base_compile_argv)
    source_index = compile_argv.index(str(source))
    compile_argv[source_index] = str(observed_source)
    output_index = compile_argv.index("-o") + 1
    compile_argv[output_index] = str(observed_object)
    compile_argv.insert(compile_argv.index(f"-I{source.parent}"), f"-I{compile_dir}")
    compile_log = observer_root / "observer_compile.raw"
    compile_log.parent.mkdir(parents=True, exist_ok=True)
    with compile_log.open("wb") as log:
        subprocess.run(compile_argv, cwd=compile_dir, check=True, stdout=log,
                       stderr=subprocess.STDOUT)
    before_archive = sha256(observer_archive)
    subprocess.run(["/usr/bin/ar", "r", str(observer_archive), str(observed_object)],
                   cwd=observer_link, check=True)
    observer_executable = observer_root / "wrf_noah_operand_observer.exe"
    observer_link_argv = list(link_argv)
    old_output = str(executable)
    observer_link_argv[observer_link_argv.index(old_output)] = str(observer_executable)
    with (observer_link / "observer_link.raw").open("wb") as log:
        subprocess.run(observer_link_argv, cwd=observer_link, check=True,
                       stdout=log, stderr=subprocess.STDOUT)
    observer_run = observer_root / "run"
    observer_run.mkdir()
    copy_inputs(observer_run, pr73)
    staged_exe = observer_run / "wrf.exe"
    shutil.copy2(observer_executable, staged_exe)
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE", "PR78_FP_MODE": mode})
    stdout = observer_run / "stdout.raw"
    with stdout.open("wb") as log:
        try:
            process = subprocess.run([str(staged_exe)], cwd=observer_run, env=env,
                                     stdout=log, stderr=subprocess.STDOUT, timeout=900)
            status: int | str = process.returncode
        except subprocess.TimeoutExpired:
            status = "TIMEOUT_900S"
    operand_path = observer_run / "pr78_noah_fk_operands.raw"
    operand_text = operand_path.read_text(errors="replace") if operand_path.is_file() else ""
    operand_records = parse_noah_operand_trace(operand_text) if operand_text else []
    return {
        "run_exit_status": status,
        "thread_count": 1,
        "runtime_fp_mode": mode,
        "same_trap_policy": True,
        "observer_applies_no_physics_or_scheme_changes": True,
        "original_equation_preserved": observed_source.read_text().count(NOAH_FK_ANCHOR) == 1,
        "source_sha256": sha256(observed_source),
        "source_diff_path": str(source_diff),
        "source_diff_sha256": sha256(source_diff),
        "object_sha256": sha256(observed_object),
        "archive_sha256_before": before_archive,
        "archive_sha256_after": sha256(observer_archive),
        "executable_sha256": sha256(observer_executable),
        "compile_argv": compile_argv,
        "link_argv": observer_link_argv,
        "compile_log_sha256": sha256(compile_log),
        "operand_trace_path": str(operand_path) if operand_path.is_file() else None,
        "operand_trace_sha256": sha256(operand_path) if operand_path.is_file() else None,
        "operand_trace_text": operand_text,
        "records": operand_records,
        "record_count": len(operand_records),
        "stdout_path": str(stdout),
        "stdout_sha256": sha256(stdout),
        "stdout_tail": stdout.read_text(errors="replace")[-2500:],
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    pr73 = json.loads((repo / PR73_PATH).read_text())
    pr74 = json.loads((repo / PR74_PATH).read_text())
    _, ifx, icx, _, ifx_version, icx_version = compile_profile()
    flags = os.environ["PR76_FP_FLAGS"].splitlines()
    build = build_once(repo, root / "build", pr73, pr74, ifx, icx, flags)
    reference_inputs = {}
    for entry in pr73["input_hashes_before_after"]:
        original = Path(entry["path"])
        if original.name != "wrf.exe":
            reference_inputs[str(original)] = entry["sha256_before"]
    profiles = {}
    exe = Path(build["executable"]["path"])
    for mode in ("PRESERVE", "CLEAR_FTZ_DAZ"):
        profile = run_case(root, mode, exe, reference_inputs, pr74)
        profiles[mode] = profile
        print(f"PR78_NATIVE_CASE {mode} {profile['run_exit_status']} {profile['first_failure_line']}", flush=True)
    same_executable = len({profile["same_executable_sha256"] for profile in profiles.values()}) == 1
    same_inputs = all(profile["input_preservation_passed"] for profile in profiles.values())
    noah = debug_noah_diagnostic(root, build, pr73, pr74, ifx)
    receipt = {
        "schema": "pr78_native_fp_runtime_choice_v1",
        "scope": "single copied O0 partialhost build, one MPI rank, one OpenMP thread; runtime choice changes only FTZ/DAZ bits at host startup and KDM6 entry",
        "toolchain": {"ifx_path": str(ifx), "ifx_version": ifx_version,
                      "ifx_sha256": sha256(ifx), "icx_path": str(icx),
                      "icx_version": icx_version, "icx_sha256": sha256(icx)},
        "build": build,
        "runtime_environment_delta": {"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE",
                                      "PR78_FP_MODE": ["PRESERVE", "CLEAR_FTZ_DAZ"],
                                      "MPI_rank_count": 1,
                                      "exception_trap_policy": "same inherited -fpe0; no mask changes"},
        "profiles": profiles,
        "comparison": {"same_executable": same_executable,
                       "same_executable_sha256": profiles["PRESERVE"]["same_executable_sha256"],
                       "same_staged_inputs": profiles["PRESERVE"]["inputs_before"] == profiles["CLEAR_FTZ_DAZ"]["inputs_before"],
                       "all_inputs_unchanged": same_inputs,
                       "startup_state_observed_in_both": all(profile["startup_fp_choice_check"] is not None
                                                              for profile in profiles.values()),
                       "noah_invalid_diagnostic": noah,
                       "native_candidate_accepted": False,
                       "ftz_daz_causality_claimed": False},
        "limits": ["The comparison records startup and KDM6-entry MXCSR only; it does not prove all host threads retain the selected state.",
                   "A failure before KDM6 entry cannot be attributed to KDM6 conversion behavior.",
                   "A caught SIGFPE backtrace locates the first trap site only when debug symbols/source lines are present."],
        "work_root": str(root),
    }
    path = root / "pr78_native_fp_runtime_choice.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"PR78_NATIVE_RECEIPT {path}")
    print(f"PR78_NATIVE_NOAH_DIAGNOSTIC {noah['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
