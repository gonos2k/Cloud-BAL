#!/usr/bin/env python3
"""Build a small source-mapped ifx overlay from the recorded PR85 candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "tests/intel_toolchain.sh"
PARENT_BUILD = Path("/var/tmp/pr85_native_joint_candidate_20261015v17")
PARENT_RECEIPT = PARENT_BUILD / "pr85_native_transport_build.json"
PARENT_RECEIPT_SHA256 = "a2c09db99d3b934a6de677c30901434ce75012fb2fd9020f19c800ee19954353"
ZEROOUT_MEMBER = "module_microphysics_zero_out.o"
# Compiler-generated interface for the replaced external helper is stale in
# the parent build. The current source declares its interface explicitly.
REPLACED_EXTERNAL_INTERFACE = "pr85_kdm6_paired_sediment_column__genmod.mod"
ZEROOUT_SOURCE = Path(
    "/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/phys/"
    "module_microphysics_zero_out.F")
ZEROOUT_SOURCE_SHA256 = "a57268701b424b07a604ce93f733314183a29bfb39e7e6283f92f8668808fa4f"
ZEROOUT_PARENT_MEMBER_SHA256 = "e551f5df36cd3ab2a719a2b9a74375261142bc2af1d3ddb45a57e878d9776dc5"
REPRO_PROFILE_NAME = "CLOUD_BAL_REPRO_FLAGS"
FREE_COMPILE_PREFIX = (
    "-stand", "f08", "-warn", "all", "-fpe0", "-traceback", "-O0",
    "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz",
)
CHECKED_COMPILE_PREFIXES = (
    FREE_COMPILE_PREFIX[:4] + ("-check", "all") + FREE_COMPILE_PREFIX[4:],
    FREE_COMPILE_PREFIX[:4] + ("-check", "all", "-check", "noarg_temp_created") + FREE_COMPILE_PREFIX[4:],
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or sha256(path) != expected:
        raise ValueError(f"{label} identity mismatch: {path}")


def load_reproduction_flags(profile: Path = PROFILE) -> list[str]:
    command = ("source " + shlex.quote(str(profile)) +
               "; printf '%s\\0' \"${CLOUD_BAL_REPRO_FLAGS[@]}\"")
    result = subprocess.run(["bash", "-lc", command], text=False,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise ValueError(f"could not source {REPRO_PROFILE_NAME} from {profile}: " +
                         result.stderr.decode(errors="replace"))
    flags = [item.decode() for item in result.stdout.split(b"\0") if item]
    if not flags or "-O2" not in flags or "-fp-model" not in flags or "strict" not in flags:
        raise ValueError(f"{REPRO_PROFILE_NAME} is missing its pinned optimized strict profile")
    return flags


def reproduction_compile_argv(argv: list[str], flags: list[str]) -> list[str]:
    """Replace one known audit prefix, leaving compile and ABI arguments intact."""
    prefixes = (FREE_COMPILE_PREFIX, *CHECKED_COMPILE_PREFIXES)
    matches = []
    for prefix in prefixes:
        for start in range(len(argv) - len(prefix) + 1):
            if tuple(argv[start:start + len(prefix)]) == prefix:
                matches.append((start, len(prefix)))
    if len(matches) != 1:
        raise ValueError("compile argv does not contain exactly one known Intel audit profile prefix")
    start, length = matches[0]
    return argv[:start] + flags + argv[start + length:]


def load_overrides(value: str) -> dict[str, Path]:
    path = Path(value)
    payload = json.loads(path.read_text() if path.is_file() else value)
    if not isinstance(payload, dict) or not payload:
        raise ValueError("--source-overrides must be a non-empty JSON object")
    overrides = {}
    for member, source in payload.items():
        if not isinstance(member, str) or not member.endswith(".o") or not isinstance(source, str):
            raise ValueError("source overrides must map object member names to source paths")
        overrides[member] = Path(source).resolve()
    return overrides


def run_pinned(argv: list[str], cwd: Path, log: Path, profile: Path = PROFILE) -> None:
    command = "source " + shlex.quote(str(profile)) + "; exec \"$@\""
    result = subprocess.run(["bash", "-lc", command, "pr87", *argv], cwd=cwd,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {argv[0]} ({log})")


def validate_parent(receipt: dict) -> dict[str, dict]:
    if receipt.get("schema") != "pr85_joint_moment_native_build_v1" or \
            receipt.get("status") != "PASS_SCOPED_BUILD" or receipt.get("model_run") is not False:
        raise ValueError("parent receipt is not a scoped PR85 build without a model run")
    recorded_profile = Path(receipt["compiler_profile_path"])
    if sha256(PROFILE) != receipt["compiler_profile_sha256"]:
        raise ValueError(f"workspace Intel profile differs from parent: {PROFILE}")
    require_hash(recorded_profile, receipt["compiler_profile_sha256"], "recorded Intel profile")
    compiler = Path(receipt["compiler_path"])
    require_hash(compiler, receipt["compiler_sha256"], "pinned ifx compiler")
    version = subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0]
    if version != receipt["compiler_version"]:
        raise ValueError("pinned ifx compiler version differs from parent receipt")

    require_hash(Path(receipt["candidate_archive_path"]), receipt["candidate_archive_sha256"],
                 "parent PR85 archive")
    executable = Path(receipt["candidate_executable_path"])
    require_hash(executable, receipt["candidate_executable_sha256"], "parent PR85 executable")
    if executable.open("rb").read(4) != b"\x7fELF":
        raise ValueError("parent PR85 executable is not ELF")

    records = {row["member"]: row for row in receipt["compiled_objects"]}
    for row in records.values():
        require_hash(Path(row["source_path"]), row["source_sha256"], f"parent source {row['member']}")
        require_hash(Path(row["generated_source_path"]), row["generated_source_sha256"],
                     f"parent generated source {row['member']}")
        require_hash(Path(row["object_path"]), row["object_sha256"], f"parent object {row['member']}")
    require_hash(Path(receipt["observer_source_path"]), receipt["observer_source_sha256"],
                 "parent observer source")
    require_hash(Path(receipt["observer_object_path"]), receipt["observer_object_sha256"],
                 "parent observer object")
    for path, expected in receipt["link_inputs_sha256"].items():
        require_hash(Path(path), expected, "parent link input")
    return records


def validate_zeroout_parent(receipt: dict) -> None:
    require_hash(ZEROOUT_SOURCE, ZEROOUT_SOURCE_SHA256, "pinned microphysics zero-out source")
    archive = Path(receipt["candidate_archive_path"])
    member = subprocess.check_output(["ar", "p", str(archive), ZEROOUT_MEMBER])
    if hashlib.sha256(member).hexdigest() != ZEROOUT_PARENT_MEMBER_SHA256:
        raise ValueError("parent microphysics zero-out archive member identity mismatch")


def stage_modules(parent: Path, compile_dir: Path) -> list[dict]:
    staged = []
    for source_dir in (parent / "compile", parent / "kdm6_compile"):
        for source in sorted(source_dir.glob("*.mod")):
            if source.name.lower() == REPLACED_EXTERNAL_INTERFACE:
                continue
            target = compile_dir / source.name
            if target.exists():
                if sha256(target) != sha256(source):
                    raise ValueError(f"conflicting parent module files: {source.name}")
                continue
            shutil.copy2(source, target)
            staged.append({"path": str(target), "sha256": sha256(target),
                           "parent_path": str(source), "parent_sha256": sha256(source)})
    return staged


def final_modules(compile_dir: Path, staged: list[dict]) -> list[dict]:
    """Bind compiler outputs separately from the parent interfaces staged in."""
    inputs = {Path(row['path']).name: row for row in staged}
    for row in staged:
        require_hash(Path(row['parent_path']), row['parent_sha256'], 'parent module')
        if not Path(row['path']).is_file():
            raise ValueError(f"staged module disappeared: {row['path']}")
    result = []
    for path in sorted(compile_dir.glob('*.mod')):
        current = {'path': str(path), 'sha256': sha256(path)}
        parent = inputs.get(path.name)
        if parent:
            current.update(parent_path=parent['parent_path'],
                           parent_sha256=parent['parent_sha256'],
                           staged_sha256=parent['sha256'],
                           regenerated=current['sha256'] != parent['sha256'])
        else:
            current['generated_in_build'] = True
        result.append(current)
    return result


def with_overlay_paths(argv: list[str], source_paths: set[Path], generated_source: Path | None,
                       generated_output: Path | None, object_path: Path, compile_dir: Path,
                       quiet_arg_temporaries: bool, compile_source: Path | None = None) -> list[str]:
    result = list(argv)
    for index, value in enumerate(result):
        if Path(value) in source_paths and compile_source is not None:
            result[index] = str(compile_source)
        elif generated_source is not None and Path(value) == generated_source:
            result[index] = str(generated_output)
        elif value == "-o" and index + 1 < len(result):
            result[index + 1] = str(object_path)
        elif value.startswith("-o") and len(value) > 2:
            result[index] = "-o" + str(object_path)
        elif value == "-module" and index + 1 < len(result):
            result[index + 1] = str(compile_dir)
    result.insert(1, f"-I{compile_dir}")
    if "-module" in result:
        result[result.index("-module") + 1] = str(compile_dir)
    elif "-c" in result:
        result[1:1] = ["-module", str(compile_dir)]
    if quiet_arg_temporaries and "-check" in result:
        check_index = result.index("-check")
        if check_index + 1 < len(result) and result[check_index + 1] == "all":
            result[check_index + 2:check_index + 2] = ["-check", "noarg_temp_created"]
    return result


def preprocess_and_compile(row: dict, source: Path, scratch: Path, compile_dir: Path,
                           quiet_arg_temporaries: bool,
                           reproduction_flags: list[str] | None = None) -> dict:
    member = row["member"]
    generated = scratch / "preprocessed" / f"{Path(member).stem}.f90"
    obj = compile_dir / member
    source_paths = {Path(row[key]) for key in ("source_path", "patched_source_path") if row.get(key)}
    preprocess_argv = with_overlay_paths(row["preprocess_argv"], source_paths, None, None, obj,
                                         compile_dir, False, source)
    result = subprocess.run(
        ["bash", "-lc", "source " + shlex.quote(str(PROFILE)) + "; exec \"$@\"",
         "pr87", *preprocess_argv], cwd=scratch, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    preprocess_log = scratch / "logs" / f"{Path(member).stem}.preprocess.log"
    preprocess_log.write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f"preprocess failed for {member}; see {preprocess_log}")
    generated.write_text(result.stdout)

    compile_argv = with_overlay_paths(row["compile_argv"], source_paths,
                                      Path(row["generated_source_path"]), generated, obj, compile_dir,
                                      quiet_arg_temporaries)
    if reproduction_flags is not None:
        compile_argv = reproduction_compile_argv(compile_argv, reproduction_flags)
    compile_log = scratch / "logs" / f"{Path(member).stem}.compile.log"
    run_pinned(compile_argv, scratch, compile_log)
    if not obj.is_file():
        raise RuntimeError(f"compiler did not create {obj}")
    return {"member": member, "source_path": str(source), "source_sha256": sha256(source),
            "parent_source_paths": [str(path) for path in sorted(source_paths)],
            "parent_preprocess_argv": row["preprocess_argv"],
            "parent_compile_argv": row["compile_argv"],
            "generated_source_path": str(generated), "generated_source_sha256": sha256(generated),
            "preprocess_argv": preprocess_argv, "preprocess_log": str(preprocess_log),
            "preprocess_log_sha256": sha256(preprocess_log), "compile_argv": compile_argv,
            "compile_log": str(compile_log), "compile_log_sha256": sha256(compile_log),
            "object_path": str(obj), "object_sha256": sha256(obj)}


def compile_extra_source(source: Path, receipt: dict, scratch: Path, compile_dir: Path,
                         quiet_arg_temporaries: bool,
                         reproduction_flags: list[str] | None = None) -> dict:
    source_dir = scratch / "source"
    staged_source = source_dir / source.name
    shutil.copy2(source, staged_source)
    obj = compile_dir / "pr87_extra_observer.o"
    argv = with_overlay_paths(receipt["observer_compile_argv"],
                              {Path(receipt["observer_source_path"])}, None, None, obj,
                              compile_dir, quiet_arg_temporaries, staged_source)
    if reproduction_flags is not None:
        argv = reproduction_compile_argv(argv, reproduction_flags)
    log = scratch / "logs/extra_observer.compile.log"
    run_pinned(argv, scratch, log)
    if not obj.is_file():
        raise RuntimeError(f"compiler did not create {obj}")
    return {"source_path": str(staged_source), "source_sha256": sha256(staged_source),
            "requested_source_path": str(source.resolve()), "requested_source_sha256": sha256(source),
            "parent_observer_source_path": receipt["observer_source_path"],
            "parent_compile_argv": receipt["observer_compile_argv"],
            "compile_argv": argv, "compile_log": str(log), "compile_log_sha256": sha256(log),
            "object_path": str(obj), "object_sha256": sha256(obj)}


def build_link_argv(receipt: dict, executable: Path, archive: Path,
                    staged_link_inputs: dict[str, dict], extra: dict | None) -> list[str]:
    argv = list(receipt["link_argv"])
    for index, arg in enumerate(argv):
        if arg == receipt["candidate_executable_path"]:
            argv[index] = str(executable)
        elif arg == receipt["candidate_archive_path"]:
            argv[index] = str(archive)
        elif arg in staged_link_inputs:
            argv[index] = staged_link_inputs[arg]["path"]
    if extra:
        observer_index = argv.index(receipt["observer_object_path"])
        argv.insert(observer_index + 1, extra["object_path"])
    return argv


def build_overlay(args: argparse.Namespace) -> dict:
    scratch = args.scratch.resolve()
    if scratch.exists():
        raise ValueError(f"scratch already exists: {scratch}")
    overrides = load_overrides(args.source_overrides)
    extra_source = args.extra_source.resolve() if args.extra_source else None
    if not overrides and extra_source is None:
        raise ValueError("provide --source-overrides or --extra-source")
    for source in [*overrides.values(), *([extra_source] if extra_source else [])]:
        if not source.is_file():
            raise ValueError(f"source file is missing: {source}")

    require_hash(PARENT_RECEIPT, PARENT_RECEIPT_SHA256, "parent build receipt")
    parent_receipt = json.loads(PARENT_RECEIPT.read_text())
    records = validate_parent(parent_receipt)
    repro_flags = load_reproduction_flags() if args.reproduction_profile else None
    unknown = sorted(set(overrides) - set(records))
    unknown = [member for member in unknown if member != ZEROOUT_MEMBER]
    if unknown:
        raise ValueError(f"source override members are absent from parent receipt: {unknown}")
    if ZEROOUT_MEMBER in overrides:
        validate_zeroout_parent(parent_receipt)
        if "solve_em.o" in overrides and \
                list(overrides).index(ZEROOUT_MEMBER) > list(overrides).index("solve_em.o"):
            raise ValueError(f"{ZEROOUT_MEMBER} must precede solve_em.o in the source override JSON")

    scratch.mkdir(parents=True)
    compile_dir, generated_dir, link_dir = scratch / "compile", scratch / "preprocessed", scratch / "link/main"
    for directory in (compile_dir, generated_dir, link_dir, scratch / "source/overrides", scratch / "logs"):
        directory.mkdir(parents=True, exist_ok=True)
    modules = stage_modules(PARENT_BUILD, compile_dir)
    staged_overrides = {}
    for member, source in overrides.items():
        target = scratch / "source/overrides" / f"{Path(member).stem}{source.suffix}"
        shutil.copy2(source, target)
        staged_overrides[member] = target

    compiled = []
    for member, source in staged_overrides.items():
        if member == ZEROOUT_MEMBER:
            recipe = dict(records["solve_em.o"])
            recipe["member"] = ZEROOUT_MEMBER
            row = preprocess_and_compile(recipe, source, scratch, compile_dir,
                                         args.quiet_arg_temporaries, repro_flags)
            row.update({"compile_recipe_derived_from_member": "solve_em.o",
                        "compile_recipe_derivation": (
                            "parent solve_em preprocess/compile argv with source, generated-source, "
                            "object, and module-output paths mapped to this new member"),
                        "parent_recorded_source_or_object_identity": False,
                        "pinned_original_source_path": str(ZEROOUT_SOURCE),
                        "pinned_original_source_sha256": ZEROOUT_SOURCE_SHA256,
                        "parent_archive_member_sha256": ZEROOUT_PARENT_MEMBER_SHA256})
            compiled.append(row)
        else:
            compiled.append(preprocess_and_compile(records[member], source, scratch, compile_dir,
                                                   args.quiet_arg_temporaries, repro_flags))

    extra = compile_extra_source(extra_source, parent_receipt, scratch, compile_dir,
                                 args.quiet_arg_temporaries, repro_flags) if extra_source else None
    parent_link_dir = Path(parent_receipt["link_cwd"])
    staged_link_inputs = {}
    for name in ("wrf.o", "module_wrf_top.o"):
        source = parent_link_dir / name
        target = link_dir / name
        shutil.copy2(source, target)
        staged_link_inputs[str(source)] = {"path": str(target), "sha256": sha256(target),
                                           "parent_sha256": sha256(source)}
    parent_archive = Path(parent_receipt["candidate_archive_path"])
    overlay_archive = link_dir / "libwrflib_pr87_overlay.a"
    shutil.copy2(parent_archive, overlay_archive)
    archive_command = ["ar", "r", str(overlay_archive), *[row["object_path"] for row in compiled]]
    run_pinned(archive_command, scratch, scratch / "logs/archive.log")
    archive_members = {}
    for row in compiled:
        data = subprocess.check_output(["ar", "p", str(overlay_archive), row["member"]])
        archive_members[row["member"]] = hashlib.sha256(data).hexdigest()
        if archive_members[row["member"]] != row["object_sha256"]:
            raise ValueError(f"archive member does not match overlay object: {row['member']}")

    executable = scratch / "wrf_pr87_overlay.exe"
    overlay_link_argv = build_link_argv(parent_receipt, executable, overlay_archive,
                                        staged_link_inputs, extra)
    link_log = scratch / "logs/link.log"
    run_pinned(overlay_link_argv, link_dir, link_log)
    if not executable.is_file() or executable.open("rb").read(4) != b"\x7fELF":
        raise RuntimeError("overlay link did not produce an ELF executable")

    receipt = {
        "schema": "pr87_native_overlay_build_v1", "status": "PASS_OVERLAY_BUILD",
        "identity": "PR87 source-mapped partial native overlay; not a clean build",
        "full_clean_build": False, "model_run": False,
        "scratch": str(scratch), "parent_receipt_path": str(PARENT_RECEIPT),
        "parent_receipt_sha256": sha256(PARENT_RECEIPT),
        "parent_candidate_executable_path": str(parent_receipt["candidate_executable_path"]),
        "parent_candidate_executable_sha256": parent_receipt["candidate_executable_sha256"],
        "parent_candidate_archive_path": str(parent_archive),
        "parent_candidate_archive_sha256": parent_receipt["candidate_archive_sha256"],
        "compiler_profile_path": str(PROFILE), "compiler_profile_sha256": sha256(PROFILE),
        "compiler_path": parent_receipt["compiler_path"], "compiler_sha256": parent_receipt["compiler_sha256"],
        "compiler_version": parent_receipt["compiler_version"],
        "staged_parent_modules": modules,
        "modules": final_modules(compile_dir, modules),
        "excluded_parent_generated_interface": REPLACED_EXTERNAL_INTERFACE,
        "compiled_overrides": compiled, "extra_observer": extra,
        "source_overrides": {member: {
            "requested_path": str(overrides[member]), "requested_sha256": sha256(overrides[member]),
            "staged_path": str(path), "staged_sha256": sha256(path),
        } for member, path in staged_overrides.items()},
        "quiet_arg_temporaries": args.quiet_arg_temporaries,
        "compile_profile": {
            "name": REPRO_PROFILE_NAME if repro_flags is not None else "parent-recorded-audit-argv",
            "enabled": repro_flags is not None,
            "flags": repro_flags,
        },
        "parent_archive_copy": str(overlay_archive), "archive_sha256": sha256(overlay_archive),
        "archive_command": archive_command, "replaced_member_sha256": archive_members,
        "staged_link_inputs": staged_link_inputs, "link_argv": overlay_link_argv,
        "link_cwd": str(link_dir), "link_log": str(link_log),
        "link_log_sha256": sha256(link_log), "executable_path": str(executable),
        "executable_sha256": sha256(executable),
    }
    receipt_path = scratch / "pr87_native_overlay_build.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True,
                        help="new output directory; an existing path is rejected")
    parser.add_argument("--source-overrides", required=True,
                        help="JSON object or JSON file mapping archive .o members to source paths")
    parser.add_argument("--extra-source", type=Path,
                        help="optional additional observer source compiled with its recorded ifx recipe")
    parser.add_argument("--quiet-arg-temporaries", action="store_true",
                        help="add -check noarg_temp_created to check-all ifx compiles")
    parser.add_argument("--reproduction-profile", action="store_true",
                        help="compile mapped sources with the pinned CLOUD_BAL_REPRO_FLAGS profile")
    args = parser.parse_args()
    try:
        receipt = build_overlay(args)
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": receipt["status"], "scratch": receipt["scratch"],
                      "compiled_members": [row["member"] for row in receipt["compiled_overrides"]],
                      "extra_observer": bool(receipt["extra_observer"]),
                      "archive_sha256": receipt["archive_sha256"],
                      "executable_path": receipt["executable_path"],
                      "executable_sha256": receipt["executable_sha256"],
                      "receipt": str(Path(receipt["scratch"]) / "pr87_native_overlay_build.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
