#!/usr/bin/env python3
"""Build the composed PR71 KDM6 in a fresh partial-host research copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

EXPECTED_IFX_SHA256 = "909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef"
EXPECTED_IFX_VERSION = "ifx (IFX) 2026.0.0 20260331"
EXPECTED_HOST_OBJECTS = {
    "wrf.o": "9efa6ff4e33e30c5df9500188c6899a6c70b15ee64b81fa42798143d45a193a3",
    "module_wrf_top.o": "c6be23b7d27b6fe0f0a23671e61ccc6d276f1f7dc0b1d010bc5a0f1d25637537",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_one_link(source: Path, target: Path, expected: str | None = None) -> str:
    stat = source.lstat()
    if source.is_symlink() or not source.is_file() or stat.st_nlink != 1:
        raise ValueError(f"source must be a regular one-link file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if target.is_symlink() or target.stat().st_nlink != 1:
        raise ValueError(f"copy is not a regular one-link file: {target}")
    digest = sha256(target)
    if expected is not None and digest != expected:
        raise ValueError(f"source hash mismatch for {source}: {digest}")
    return digest


def run(argv: list[str], cwd: Path, log_path: Path) -> None:
    with log_path.open("xb") as stream:
        result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}); see {log_path}: {argv}")


def build(source: Path, base: Path, receipt_path: Path,
          build_reference: Path, retained_link_main: Path) -> dict[str, Any]:
    if base.exists() or base.is_symlink():
        raise ValueError(f"refusing to reuse build tree: {base}")
    if receipt_path.exists() or receipt_path.is_symlink():
        raise ValueError(f"refusing to overwrite build receipt: {receipt_path}")
    if not source.is_file() or source.is_symlink():
        raise ValueError("composed source must be a regular non-symlink file")

    reference = json.loads(build_reference.read_text(encoding="utf-8"))
    compiler = Path(os.environ["CLOUD_BAL_FC"])
    compiler_version = subprocess.run(
        [str(compiler), "--version"], text=True, capture_output=True, check=True
    ).stdout.splitlines()[0]
    compiler_hash = sha256(compiler)
    if compiler_version != EXPECTED_IFX_VERSION or compiler_hash != EXPECTED_IFX_SHA256:
        raise ValueError("pinned Intel ifx does not match the required profile")

    compile_dir = base / "compile"
    source_dir = base / "source"
    link_dir = base / "link" / "main"
    executable_dir = base / "executable"
    for directory in (compile_dir, source_dir, link_dir, executable_dir):
        directory.mkdir(parents=True)

    source_name = "module_mp_kdm6.f90"
    source_copy = source_dir / source_name
    source_hash = copy_one_link(source, source_copy)
    compile_copy = compile_dir / source_name
    copy_one_link(source_copy, compile_copy, source_hash)
    compile_argv = list(reference["compile"]["argv"])
    compile_argv[0] = str(compiler)
    # Retain all pinned flags and replace only the source/object basenames.
    compile_argv[compile_argv.index("-c") + 1] = source_name
    object_path = compile_dir / "module_mp_kdm6.o"
    compile_argv[compile_argv.index("-o") + 1] = object_path.name
    run(compile_argv, compile_dir, compile_dir / "compile.log")
    object_hash = sha256(object_path)
    copy_one_link(object_path, link_dir / object_path.name, object_hash)

    retained_archive = retained_link_main / "libwrflib_pr65.a"
    archive = link_dir / retained_archive.name
    archive_reference_hash = reference["archive"]["source_sha256"]
    archive_hash = copy_one_link(retained_archive, archive, archive_reference_hash)
    host_hashes = {}
    for name, expected_hash in EXPECTED_HOST_OBJECTS.items():
        host_hashes[name] = copy_one_link(
            retained_link_main / name, link_dir / name, expected_hash
        )
    ar = shutil.which("ar")
    if ar is None:
        raise ValueError("ar is required for the isolated host archive update")
    archive_before_hash = sha256(archive)
    archive_update_argv = [ar, "r", archive.name, object_path.name]
    run(archive_update_argv, link_dir, base / "archive_update.log")
    members = subprocess.run(
        [ar, "t", archive.name], cwd=link_dir, text=True, capture_output=True, check=True
    ).stdout.splitlines()
    if members.count(object_path.name) != 1:
        raise ValueError("fresh partial-host archive must contain one KDM6 object")
    member_bytes = subprocess.run(
        [ar, "p", archive.name, object_path.name], cwd=link_dir,
        capture_output=True, check=True,
    ).stdout
    member_path = link_dir / "archive_member.o"
    with member_path.open("xb") as stream:
        stream.write(member_bytes)
    member_hash = sha256(member_path)
    if member_hash != object_hash:
        raise ValueError("fresh archive member differs from compiled KDM6 object")

    link_argv = list(reference["link"]["argv"])
    output_index = link_argv.index("-o") + 1
    executable = executable_dir / "wrf.exe"
    link_argv[output_index] = str(executable)
    run(link_argv, link_dir, base / "link.log")
    if executable.is_symlink() or executable.stat().st_nlink != 1:
        raise ValueError("fresh native executable is not a one-link regular file")

    receipt = {
        "schema": "pr71_partialhost_native_build_v1",
        "host_scope": "partialhost: selected KDM6 recompiled and inserted into a fresh copy of retained host objects/archive",
        "base": str(base),
        "source": {"path": str(source_copy), "sha256": source_hash},
        "toolchain": {"ifx": str(compiler), "version": compiler_version, "sha256": compiler_hash},
        "compile": {"argv": compile_argv, "cwd": str(compile_dir), "log": str(compile_dir / "compile.log"), "object_sha256": object_hash},
        "host_objects": host_hashes,
        "archive": {
            "retained_source": str(retained_archive),
            "retained_source_sha256": archive_hash,
            "fresh_before_sha256": archive_before_hash,
            "fresh_after_sha256": sha256(archive),
            "member_name": object_path.name,
            "member_count": members.count(object_path.name),
            "member_sha256": member_hash,
            "update_argv": archive_update_argv,
        },
        "link": {"argv": link_argv, "cwd": str(link_dir), "log": str(base / "link.log"),
                 "executable": str(executable), "executable_sha256": sha256(executable)},
        "limitations": "Partial-host research build; it does not establish a clean full-physics host build or production-source equivalence.",
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--build-reference", type=Path, required=True)
    parser.add_argument("--retained-link-main", type=Path, required=True)
    args = parser.parse_args()
    receipt = build(args.source, args.base, args.receipt,
                    args.build_reference, args.retained_link_main)
    print(f"PARTIALHOST_SOURCE_SHA256 {receipt['source']['sha256']}")
    print(f"PARTIALHOST_OBJECT_SHA256 {receipt['compile']['object_sha256']}")
    print(f"PARTIALHOST_EXECUTABLE_SHA256 {receipt['link']['executable_sha256']}")
    print(f"PARTIALHOST_BUILD_RECEIPT {args.receipt}")


if __name__ == "__main__":
    main()
