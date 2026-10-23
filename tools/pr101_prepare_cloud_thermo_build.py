#!/usr/bin/env python3
"""Stage a fresh IFX build directory and its precompile module inventory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


IFX = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/ifx")
MPIIFX = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpiifx")
FLAGS = ["-stand", "f08", "-warn", "all", "-fpe0", "-traceback", "-O2",
         "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz",
         "-qopenmp", "-convert", "big_endian"]
ADDITIONAL_MODULE_PINS = (
    ("module_mp_radar.mod", Path("/var/tmp/pr84_ice_entry_guard_final_1efgtcsn/compile/module_mp_radar.mod"),
     "30cd20540b43b3e96cb721e485a9e8e6fe693cc71d6814758e98033ed590a863"),
    ("module_model_constants.mod", Path("/var/tmp/pr61_ccn_origin_20261006/hostcopy/frame/module_model_constants.mod"),
     "262c94bfd198c60701a4fdceb8e85f30ae40c4a167fc5918cc7e73530d8bbe65"),
    ("module_wrf_error.mod", Path("/var/tmp/pr61_ccn_origin_20261006/hostcopy/frame/module_wrf_error.mod"),
     "a88b7ac0a69e4ee98b35728ba0093743af6eca35ba61738267c55c4aab54ee2e"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source: Path, module_pin_file: Path, module_root: Path,
            scratch: Path, profile: Path, old_link_argv_path: Path) -> dict:
    if scratch.exists() or scratch.is_symlink() or not scratch.is_absolute():
        raise ValueError("build directory must be a new absolute scratch path")
    if any((parent / ".git").exists() for parent in scratch.parents):
        raise ValueError("build directory must be outside git checkouts")
    pins = []
    for line in module_pin_file.read_text().splitlines():
        digest, name = line.split(None, 1)
        name = Path(name)
        if name.name != str(name) or name.name == "module_mp_kdm6.mod":
            raise ValueError(f"invalid or prohibited module seed name: {name}")
        source_mod = module_root / name
        if not source_mod.is_file() or sha256(source_mod) != digest:
            raise ValueError(f"module seed does not match retained source pin: {source_mod}")
        pins.append((name.name, digest, source_mod))
    if len(pins) != 27 or len({name for name, _, _ in pins}) != 27:
        raise ValueError("expected 27 unique retained PR100 module pins")
    for name, source_mod, digest in ADDITIONAL_MODULE_PINS:
        if not source_mod.is_file() or sha256(source_mod) != digest:
            raise ValueError(f"additional module dependency differs from exact pin: {source_mod}")
        pins.append((name, digest, source_mod))
    if len(pins) != 30 or len({name for name, _, _ in pins}) != 30:
        raise ValueError("expected 30 unique pinned module inputs")

    dirs = {name: scratch / name for name in ("src", "mod", "obj", "link", "logs")}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=False)
    source_copy = dirs["src"] / "module_mp_kdm6_pr101.f90"
    shutil.copyfile(source, source_copy)
    for name, _, path in pins:
        shutil.copyfile(path, dirs["mod"] / name)
    original_names = {line.split(None, 1)[1] for line in module_pin_file.read_text().splitlines()}
    inventory = [{"name": name, "seed_source": str(path), "staged_path": str(dirs["mod"] / name),
                  "sha256": sha256(dirs["mod"] / name),
                  "kind": "retained_PR100_module_pin" if name in original_names else "explicit_dependency_pin"}
                 for name, _, path in pins]
    inventory_path = scratch / "precompile_seed_inventory.json"
    inventory_path.write_text(json.dumps({"schema": "pr101_precompile_module_inventory_v1",
        "count": len(inventory), "exclude_own_kdm6_module": True, "modules": inventory},
        indent=2) + "\n")

    object_path = dirs["obj"] / "module_mp_kdm6_pr101.o"
    executable = dirs["link"] / "pr101_cloud_thermo_replay.exe"
    compile_argv = [str(IFX), "-module", str(dirs["mod"]), "-I" + str(dirs["mod"]),
                    *FLAGS, "-free", "-c", str(source_copy), "-o", str(object_path)]
    old_link = json.loads(old_link_argv_path.read_text())
    link_argv = (old_link.get("argv", old_link.get("link_argv"))
                 if isinstance(old_link, dict) else old_link)
    if not isinstance(link_argv, list):
        raise ValueError("retained link argv must be a JSON argument list")
    link_argv = [str(executable) if value.endswith("/pr100_qc_replay.exe") else
                 str(object_path) if value.endswith("/module_mp_kdm6_pr100.o") else value
                 for value in link_argv]
    if str(MPIIFX) not in link_argv or str(object_path) not in link_argv:
        raise ValueError("could not adapt the retained link argv to PR101 paths")
    output_index = link_argv.index(str(executable))
    link_argv[output_index + 1:output_index + 1] = ["-Wl,-Map," + str(dirs["link"] / "link.map")]
    plan = {
        "schema": "pr101_cloud_thermo_build_plan_v1",
        "scope": "staged only; no compilation or linking performed",
        "source": {"path": str(source), "sha256": sha256(source),
                   "staged_path": str(source_copy), "staged_sha256": sha256(source_copy)},
        "profile": {"path": str(profile), "sha256": sha256(profile),
                    "compiler": str(IFX), "mpi_compiler": str(MPIIFX)},
        "scratch": str(scratch), "module_seed_inventory": str(inventory_path),
        "module_seed_count": len(inventory), "module_seed_source_root": str(module_root),
        "module_search_paths": [str(dirs["mod"])],
        "compile": {"argv": compile_argv, "cwd": str(scratch), "returncode": None},
        "link": {"argv": link_argv, "cwd": str(scratch), "returncode": None,
                 "based_on": str(old_link_argv_path)},
        "required_recording": ["compile argv/cwd/rc", "link argv/cwd/rc", "object sha256",
            "executable sha256", "link map", "precompile module seed inventory",
            "profile environment sourced before each compiler invocation"],
    }
    plan_path = scratch / "build_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    (scratch / "compile_argv.json").write_text(json.dumps(compile_argv, indent=2) + "\n")
    (scratch / "link_argv.json").write_text(json.dumps(link_argv, indent=2) + "\n")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("module_pin_file", type=Path)
    parser.add_argument("module_root", type=Path)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("old_link_argv", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.module_pin_file, args.module_root,
                             args.scratch, args.profile, args.old_link_argv), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
