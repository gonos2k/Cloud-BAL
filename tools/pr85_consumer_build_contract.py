#!/usr/bin/env python3
"""Validate the scoped PR85 executable/archive build receipt."""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from archive_member_hashes import archive_member_hashes

ROOT = Path(__file__).resolve().parents[1]
BASE_RECEIPT = ROOT / "docs/evidence/pr84_native_ice_guard_build_20261013.json"
BASE_RECEIPT_SHA256 = "0040ea6e86c08caac78526fb0db276dc045d150646b5ccb247d660679c3efce1"
PARENT_EXE_SHA256 = "4912d0f5c6b91d8e57bd0ff91adab2938ed4f74b9e8fa417903202dbf1c9d55a"
PARENT_ARCHIVE_SHA256 = "7c1ea24fb3baa4d7c4d977920378a6c53f929077b07300754f4d3844a2b3e7da"
PROFILE = ROOT / "tests/intel_toolchain.sh"
PROFILE_SHA256 = "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4"
IFX = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/ifx")
IFX_SHA256 = "909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef"
IFX_VERSION = "ifx (IFX) 2026.0.0 20260331"
CHANGED_ALLOWED = {
    "module_bl_shinhong.o", "module_pbl_driver.o", "module_advect_em.o",
    "module_em.o", "solve_em.o", "module_bl_fogdes.o",
    "module_first_rk_step_part2.o", "module_first_rk_step_part1.o",
    "module_mp_kdm6.o",
}
KDM6_MEMBER = "module_mp_kdm6.o"
KDM6_SOURCE_SHA256 = "f7fb216c82822162c30148829f207deeee5900e46e01ad9082ac58c802a181d9"
KDM6_MEMBER_SHA256 = "e097b7e70566275d5cd82c211d91e4658091c78ea1b41eb9ffef35bc1159d006"
OBSERVER_MEMBER = "pr85_joint_stage_observer.o"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_argv(argv: list[str]) -> str:
    return hashlib.sha256(b"\0".join(os.fsencode(arg) for arg in argv) + b"\0").hexdigest()


def require_file(path_value: Any, digest: Any, label: str) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"{label} path missing")
    path = Path(path_value)
    if not path.is_file() or not isinstance(digest, str) or sha256(path) != digest:
        raise ValueError(f"{label} identity mismatch")
    return path


def row_for_member(rows: list[tuple[str, str]], member: str) -> str:
    found = [digest for name, digest in rows if name == member]
    if len(found) != 1:
        raise ValueError(f"changed archive member must occur exactly once: {member}")
    return found[0]


def validate_kdm6_replacement(record: dict[str, Any], provenance: list[dict[str, Any]],
                              replaced: list[str], parent_rows: list[tuple[str, str]]) -> None:
    patch_path = record.get("kdm6_sedimentation_patch_path")
    patch_hash = record.get("kdm6_sedimentation_patch_sha256")
    if KDM6_MEMBER not in replaced:
        if patch_path is not None or patch_hash is not None:
            raise ValueError("KDM6 patch receipt is present without a KDM6 archive replacement")
        return
    if not isinstance(patch_path, str) or not patch_path:
        raise ValueError("KDM6 replacement requires an explicit sedimentation patch receipt")
    require_file(patch_path, patch_hash, "KDM6 sedimentation patch")
    if row_for_member(parent_rows, KDM6_MEMBER) != KDM6_MEMBER_SHA256:
        raise ValueError("retained KDM6 parent archive member identity mismatch")
    rows = [row for row in provenance if row.get("member") == KDM6_MEMBER]
    if len(rows) != 1:
        raise ValueError("KDM6 replacement provenance missing or duplicated")
    row = rows[0]
    if row.get("source_sha256") != KDM6_SOURCE_SHA256:
        raise ValueError("KDM6 replacement is not bound to the retained PR84 source")
    source_receipt = require_file(row.get("source_receipt_path"),
                                  row.get("source_receipt_sha256"),
                                  "KDM6 PR84 source receipt")
    if source_receipt.resolve() != BASE_RECEIPT.resolve() or \
            sha256(source_receipt) != BASE_RECEIPT_SHA256:
        raise ValueError("KDM6 source receipt is not the pinned PR84 build receipt")
    parent_build = json.loads(source_receipt.read_text())
    if (parent_build.get("production_source_sha256") != KDM6_SOURCE_SHA256 or
            parent_build.get("production_object_sha256") != KDM6_MEMBER_SHA256):
        raise ValueError("KDM6 PR84 source receipt does not bind retained source/object")
    recipe_path = require_file(row.get("compile_recipe_source_path"),
                               row.get("compile_recipe_source_sha256"),
                               "KDM6 compile recipe source")
    recipe = json.loads(recipe_path.read_text())
    original_argv = recipe.get("production_compile_argv")
    if not isinstance(original_argv, list) or not all(isinstance(arg, str) for arg in original_argv):
        raise ValueError("KDM6 retained production compile recipe is missing")
    source_path = row.get("source_path")
    patched_source_path = row.get("patched_source_path")
    generated_source_path = row.get("generated_source_path")
    object_path = row.get("object_path")
    if (not isinstance(source_path, str) or not isinstance(patched_source_path, str) or
            not isinstance(generated_source_path, str) or not isinstance(object_path, str) or
            original_argv.count(source_path) != 1 or original_argv.count("-c") != 1 or
            original_argv.count("-o") != 1):
        raise ValueError("KDM6 compile recipe source/object bindings are incomplete")
    require_file(patched_source_path, row.get("patched_source_sha256"), "KDM6 patched source")
    patch_row = row.get("patches", {}).get("kdm6_sedimentation", {})
    if (not patched_source_path.endswith("/phys/module_mp_kdm6.F") or
            patch_row.get("path") != patch_path or patch_row.get("sha256") != patch_hash):
        raise ValueError("KDM6 source/patch provenance is not explicitly bound")
    expected_ep = list(original_argv)
    expected_ep.remove("-c")
    output_index = expected_ep.index("-o")
    del expected_ep[output_index:output_index + 2]
    expected_ep[expected_ep.index(source_path)] = patched_source_path
    expected_ep.append("-EP")
    expected_compile = list(original_argv)
    if "-fpp" not in expected_compile:
        raise ValueError("KDM6 parent compile recipe omits the Fortran preprocessor")
    expected_compile.remove("-fpp")
    expected_compile[expected_compile.index(source_path)] = generated_source_path
    expected_compile[expected_compile.index("-o") + 1] = object_path
    if (row.get("preprocess_argv") != expected_ep or
            row.get("compile_argv") != expected_compile or
            row.get("preprocessor_defines") != [arg for arg in expected_ep if arg.startswith("-D")]):
        raise ValueError("KDM6 compile/preprocess argv differs from retained PR84 recipe")


def validate_link_recipe(record: dict[str, Any], base: dict[str, Any], exe: Path,
                         archive: Path, observer: Path) -> None:
    argv = record.get("link_argv")
    if not isinstance(argv, list) or not all(isinstance(arg, str) for arg in argv):
        raise ValueError("link_argv is missing or malformed")
    if sha256_argv(argv) != record.get("link_argv_nul_sha256"):
        raise ValueError("link argv digest mismatch")
    base_argv = base["production_link_argv"]
    if base_argv.count("-o") != 1 or argv.count("-o") != 1:
        raise ValueError("link recipe must contain exactly one -o")
    base_out = base_argv[base_argv.index("-o") + 1]
    if argv[argv.index("-o") + 1] != str(exe):
        raise ValueError("link -o does not name candidate executable")
    # The parent archive is the single .a argument carrying the pinned digest.
    parent_archive = next(path for path, digest in base["production_link_dependencies_sha256"].items()
                          if digest == PARENT_ARCHIVE_SHA256)
    if base_argv.count(parent_archive) != 1 or argv.count(str(archive)) != 1:
        raise ValueError("link recipe must contain the candidate archive exactly once")
    parent_cwd = str(Path(parent_archive).parent)
    replacements = {
        base_out: str(exe),
        parent_archive: str(archive),
        str(Path(parent_cwd) / "wrf.o"): str(archive.parent / "wrf.o"),
        str(Path(parent_cwd) / "module_wrf_top.o"): str(archive.parent / "module_wrf_top.o"),
    }
    expected = [replacements.get(arg, arg) for arg in base_argv]
    # The observer is inserted once next to the archive so it resolves symbols
    # exported by the linked WRF library without changing inherited flags.
    archive_slot = expected.index(str(archive)) + 1
    expected.insert(archive_slot, str(observer))
    if argv != expected:
        raise ValueError("link argv differs from pinned PR84 recipe beyond scoped inputs")
    input_hashes = record.get("link_inputs_sha256")
    if not isinstance(input_hashes, dict):
        raise ValueError("link input hash map missing")
    for arg in argv:
        path = Path(arg)
        if path.is_absolute() and path.is_file() and path.suffix in {".o", ".a"}:
            if input_hashes.get(str(path)) != sha256(path):
                raise ValueError(f"link input identity mismatch: {path}")
    parent_deps = base["production_link_dependencies_sha256"]
    for old_path, digest in parent_deps.items():
        if old_path in {parent_archive,
                        str(Path(parent_cwd) / "wrf.o"),
                        str(Path(parent_cwd) / "module_wrf_top.o")}:
            continue
        # The PR84 receipt also catalogs a few files resolved indirectly by
        # -l flags (for example libesmf_time.a). They are not argv inputs, so
        # this scoped check only compares concrete inherited argv paths.
        if old_path not in base_argv:
            continue
        if input_hashes.get(old_path) != digest:
            raise ValueError(f"inherited link input binding changed: {old_path}")
    for obj_name, old_name in (("wrf.o", "wrf.o"), ("module_wrf_top.o", "module_wrf_top.o")):
        old_path = str(Path(parent_cwd) / old_name)
        copied_path = str(archive.parent / obj_name)
        expected_hash = parent_deps.get(old_path)
        if not expected_hash or input_hashes.get(copied_path) != expected_hash:
            raise ValueError(f"copied parent {obj_name} identity changed")


def validate_consumer_build(receipt_path: Path, expected_executable: Path,
                            expected_parent_executable_sha256: str) -> dict[str, Any]:
    if sha256(BASE_RECEIPT) != BASE_RECEIPT_SHA256:
        raise ValueError("pinned PR84 link receipt changed")
    base = json.loads(BASE_RECEIPT.read_text())
    record = json.loads(receipt_path.read_text())
    if record.get("schema") != "pr85_joint_moment_native_build_v1" or \
            record.get("status") != "PASS_SCOPED_BUILD":
        raise ValueError("unsupported or failed native build receipt")
    parent_exe = require_file(record.get("parent_executable_path"),
                              record.get("parent_executable_sha256"), "parent executable")
    parent_archive = require_file(record.get("parent_archive_path"),
                                  record.get("parent_archive_sha256"), "parent archive")
    if sha256(parent_exe) != expected_parent_executable_sha256 or \
            sha256(parent_exe) != PARENT_EXE_SHA256 or sha256(parent_archive) != PARENT_ARCHIVE_SHA256:
        raise ValueError("pinned parent executable/archive identity mismatch")
    if record.get("compiler_profile_sha256") != PROFILE_SHA256 or sha256(PROFILE) != PROFILE_SHA256:
        raise ValueError("Intel compiler profile identity mismatch")
    if record.get("compiler_path") != str(IFX) or record.get("compiler_sha256") != IFX_SHA256 or \
            record.get("compiler_version") != IFX_VERSION:
        raise ValueError("pinned Intel compiler identity mismatch")

    exe = require_file(record.get("candidate_executable_path"),
                       record.get("candidate_executable_sha256"), "candidate executable")
    archive = require_file(record.get("candidate_archive_path"),
                           record.get("candidate_archive_sha256"), "candidate archive")
    if exe.resolve() != expected_executable.resolve():
        raise ValueError("candidate_executable identity/path mismatch")
    observer = require_file(record.get("observer_object_path"),
                            record.get("observer_object_sha256"), "observer object")
    source = require_file(record.get("observer_source_path"),
                          record.get("observer_source_sha256"), "observer source")
    observer_argv = record.get("observer_compile_argv")
    if not isinstance(observer_argv, list) or not all(isinstance(arg, str) for arg in observer_argv):
        raise ValueError("observer compile argv missing")
    if (observer_argv.count(str(source)) != 1 or observer_argv.count(str(observer)) != 1 or
            observer_argv.count("-c") != 1 or observer_argv.count("-o") != 1 or
            observer_argv[observer_argv.index("-o") + 1] != str(observer) or
            Path(observer_argv[0]) != IFX or "-O0" not in observer_argv or "-O2" in observer_argv):
        raise ValueError("observer compile argv is not bound to pinned Intel source/object")

    parent_rows = archive_member_hashes(parent_archive)
    candidate_rows = archive_member_hashes(archive)
    if record.get("ordered_parent_members") != [list(row) for row in parent_rows] or \
            record.get("ordered_candidate_members") != [list(row) for row in candidate_rows]:
        raise ValueError("archive member ledger mismatch")
    if [name for name, _ in parent_rows] != [name for name, _ in candidate_rows]:
        raise ValueError("candidate archive member order changed")
    replaced = record.get("replaced_members")
    if not isinstance(replaced, list) or len(replaced) != len(set(replaced)):
        raise ValueError("replacement member list missing or duplicated")
    if any(name not in CHANGED_ALLOWED for name in replaced):
        raise ValueError("undeclared archive member replacement")
    changed = [name for (name, before), (_, after) in zip(parent_rows, candidate_rows)
               if before != after]
    if sorted(changed) != sorted(replaced):
        raise ValueError("archive changes differ from replacement ledger")
    for member in replaced:
        row_for_member(parent_rows, member)
        row_for_member(candidate_rows, member)

    provenance = record.get("compiled_member_provenance")
    if not isinstance(provenance, list):
        provenance = record.get("compiled_objects", []) + record.get("supplemental_replacements", [])
    if not isinstance(provenance, list):
        raise ValueError("compiled member provenance missing")
    names = [row.get("member") for row in provenance]
    if Counter(names) != Counter(replaced):
        raise ValueError("compiled member provenance does not match changed members")
    for row in provenance:
        member = row["member"]
        require_file(row.get("source_path"), row.get("source_sha256"), f"{member} source")
        require_file(row.get("object_path"), row.get("object_sha256"), f"{member} object")
        if row.get("patched_source_path") is not None:
            require_file(row.get("patched_source_path"), row.get("patched_source_sha256"),
                         f"{member} patched source")
        for label in ("generated_source",):
            if row.get(label + "_path") is not None:
                require_file(row.get(label + "_path"), row.get(label + "_sha256"),
                             f"{member} {label.replace('_', '-')} bytes")
        compile_argv = row.get("compile_argv")
        compiled_source = (row.get("generated_source_path") or
                           row.get("patched_source_path") or row["source_path"])
        if (not isinstance(compile_argv, list) or not compile_argv or
                not all(isinstance(arg, str) for arg in compile_argv) or
                compile_argv[0] != str(IFX) or compile_argv.count("-c") != 1 or
                compile_argv.count("-o") != 1 or
                compile_argv[-1] == "-o" or
                compile_argv[compile_argv.index("-o") + 1] != row["object_path"] or
                compile_argv.count(row["object_path"]) != 1 or
                compile_argv.count(compiled_source) != 1):
            raise ValueError(f"{member} compile argv is not bound to pinned Intel source/object")
        if row.get("object_sha256") != row_for_member(candidate_rows, member):
            raise ValueError(f"{member} object does not match candidate archive member")
        baseline_path = row.get("baseline_archive_path")
        baseline_hash = row.get("baseline_archive_sha256")
        if baseline_path is not None or baseline_hash is not None:
            if baseline_path != str(parent_archive) or baseline_hash != sha256(parent_archive):
                raise ValueError(f"{member} baseline archive identity mismatch")
        baseline_member_hash = row.get("baseline_member_sha256")
        if baseline_member_hash is not None and baseline_member_hash != row_for_member(parent_rows, member):
            raise ValueError(f"{member} baseline archive member identity mismatch")

    validate_kdm6_replacement(record, provenance, replaced, parent_rows)
    validate_link_recipe(record, base, exe, archive, observer)
    return {
        "status": "PASS_SCOPED_BUILD",
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": sha256(receipt_path),
        "candidate_executable_path": str(exe.resolve()),
        "candidate_executable_sha256": sha256(exe),
        "candidate_archive_path": str(archive.resolve()),
        "candidate_archive_sha256": sha256(archive),
        "observer_source_path": str(source.resolve()),
        "observer_source_sha256": sha256(source),
        "observer_object_path": str(observer.resolve()),
        "observer_object_sha256": sha256(observer),
        "link_argv": record["link_argv"],
        "link_argv_nul_sha256": record["link_argv_nul_sha256"],
        "link_inputs_sha256": record["link_inputs_sha256"],
        "link_cwd": record.get("link_cwd"),
        "compiler_profile_sha256": record["compiler_profile_sha256"],
        "compiler_path": record["compiler_path"],
        "compiler_sha256": record["compiler_sha256"],
        "compiler_version": record["compiler_version"],
        "replaced_members": sorted(replaced),
        "physical_acceptance": "UNASSESSED",
        "scope": "receipt-bound link recipe and file identities; does not attest external execution or transitive libraries",
    }
