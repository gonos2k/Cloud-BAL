#!/usr/bin/env python3
"""Copy hash-pinned WRF source/build closure into a fresh Lustre input tree."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
WORKTREE = EVIDENCE.parents[2]
TASK_ROOT = WORKTREE.parent
PLAN = EVIDENCE / "native_build_plan.json"
SOURCE_MANIFEST = WORKTREE / "docs/evidence/cp02_initial_boundaries_20261105/native/sourcepins/manifest.json"
BUILD_RECEIPT = WORKTREE / "docs/evidence/cp02_rain_number_process_20261104/native/build/build_cp03_receipt.json"
OLD_EXPRESSION = "al(i,k,j) = (ph(i,k+1,j)-ph(i,k,j)+phb(i,k+1,j)-phb(i,k,j))/phm/LOG(pfd/pfu)-alb(i,k,j)"
GROUPED_EXPRESSION = "al(i,k,j) = ((ph(i,k+1,j)-ph(i,k,j))+(phb(i,k+1,j)-phb(i,k,j)))/phm/LOG(pfd/pfu)-alb(i,k,j)"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def identity(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {"path": str(path), "device": stat.st_dev, "inode": stat.st_ino,
            "size_bytes": stat.st_size, "sha256": digest(path)}


def add_copy(source: Path, destination: Path, expected_hash: str, kind: str,
             input_root: Path, files: list[dict[str, object]]) -> None:
    if digest(source) != expected_hash:
        raise RuntimeError(f"frozen source hash mismatch: {source}")
    target = input_root / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    os.chmod(target, 0o444)
    source_id, target_id = identity(source), identity(target)
    if source_id["sha256"] != target_id["sha256"] or (source_id["device"], source_id["inode"]) == (target_id["device"], target_id["inode"]):
        raise RuntimeError(f"copy identity/independence check failed: {source}")
    files.append({"kind": kind, "source": source_id,
                  "relative_path": str(target.relative_to(input_root)),
                  "copy": target_id, "sha256": target_id["sha256"], "same_inode": False})


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: prepare_native_inputs.py FRESH_INPUT_ROOT", file=sys.stderr)
        return 2
    input_root = Path(sys.argv[1]).resolve()
    expected_root = TASK_ROOT / "runtime/native_build/inputs"
    if input_root != expected_root or input_root.exists():
        raise RuntimeError(f"input root must be fresh and exact: {expected_root}")
    input_root.mkdir(parents=True)
    plan = json.loads(PLAN.read_text())
    source_manifest = json.loads(SOURCE_MANIFEST.read_text())
    build = json.loads(BUILD_RECEIPT.read_text())
    files: list[dict[str, object]] = []

    target_pin = next(item for item in source_manifest["files"]
                      if item["unit"] == "dyn_em/module_big_step_utilities_em")
    target_source = Path(target_pin["source_path"])
    old_text = target_source.read_text()
    if digest(target_source) != plan["source_freeze"]["old_source_sha256"] or old_text.count(OLD_EXPRESSION) != 1:
        raise RuntimeError("OLD_SHAM source or exact replacement anchor drifted")
    grouped_text = old_text.replace(OLD_EXPRESSION, GROUPED_EXPRESSION, 1)
    for variant, content in (("OLD_SHAM", old_text), ("GROUPED", grouped_text)):
        destination = input_root / "source" / variant / target_source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)
        os.chmod(destination, 0o444)
        actual_hash = digest(destination)
        expected_hash = (plan["source_freeze"]["old_source_sha256"] if variant == "OLD_SHAM"
                         else plan["source_freeze"]["grouped_source_sha256_after_single_exact_replacement"])
        if actual_hash != expected_hash:
            raise RuntimeError(f"{variant} source hash mismatch")
        source_id, copy_id = identity(target_source), identity(destination)
        if (source_id["device"], source_id["inode"]) == (copy_id["device"], copy_id["inode"]):
            raise RuntimeError(f"{variant} source aliases the archived host inode")
        files.append({"kind": "fortran_target_" + variant, "source": source_id,
                      "relative_path": str(destination.relative_to(input_root)),
                      "copy": copy_id, "sha256": copy_id["sha256"], "same_inode": False,
                      "single_expression_replacement_count": 0 if variant == "OLD_SHAM" else 1})

    for item in source_manifest["files"]:
        if item["unit"] == target_pin["unit"]:
            continue
        source = Path(item["source_path"])
        relative = Path("source/lineage") / (item["unit"].replace("/", "_") + ".f90")
        add_copy(source, relative, item["sha256"], "fortran_lineage", input_root, files)

    for item in plan["compile_module_dependencies"]["module_files"]:
        source = Path(item["path"])
        add_copy(source, Path("modules") / source.name, item["sha256"],
                 "ifx_module_dependency", input_root, files)

    archive_root = Path("/var/tmp/firsthour-runtime-plan-20261030/experiment")
    for item in plan["ten_link_input_freeze"]["link_inputs"]:
        source = Path(item["path"])
        relative = Path("experiment") / source.relative_to(archive_root)
        add_copy(source, relative, item["sha256"], item["role"], input_root, files)
    for item in plan["implicit_link_libraries"]["library_files"]:
        source = Path(item["path"])
        if source.is_relative_to(archive_root):
            relative = Path("experiment") / source.relative_to(archive_root)
        else:
            relative = Path("netcdf") / source.name
        add_copy(source, relative, item["sha256"], "implicit_link_library", input_root, files)

    input_manifest = {
        "schema": "cp02_grouped_native_frozen_input_copy_v1",
        "status": "PASS_HASHED_PRIVATE_COPIES",
        "worktree_commit": plan["worktree_commit"],
        "prep_recipe": identity(Path(__file__)),
        "source_lineage_sha256": digest(WORKTREE / "docs/evidence/cp02_initial_boundaries_20261105/native/source_lineage.json"),
        "sourcepins_manifest_sha256": digest(SOURCE_MANIFEST),
        "build_receipt_sha256": digest(BUILD_RECEIPT),
        "files": files,
        "summary": {"fortran_units": 6, "target_variants": 2,
                    "direct_module_dependencies": len(plan["compile_module_dependencies"]["direct_use_module_names"]),
                    "copied_module_files": len(plan["compile_module_dependencies"]["module_files"]),
                    "explicit_link_inputs": 10, "implicit_link_archives": 4,
                    "total_files": len(files), "all_hashes_match": True,
                    "all_copies_have_independent_inodes": True},
        "scope_limit": "Hash-frozen inputs copied; no compiler invocation or model execution."
    }
    manifest_path = input_root / "copy_manifest.json"
    manifest_path.write_text(json.dumps(input_manifest, indent=2) + "\n")
    receipt_path = EVIDENCE / "input_copy_receipt.json"
    receipt_path.write_text(json.dumps({"status": "PASS", "input_root": str(input_root),
                                        "copy_manifest": identity(manifest_path),
                                        "summary": input_manifest["summary"],
                                        "files": files,
                                        "scope_limit": input_manifest["scope_limit"]}, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "input_root": str(input_root),
                      "copy_manifest_sha256": digest(manifest_path),
                      "copy_receipt_sha256": digest(receipt_path),
                      "files": len(files)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
