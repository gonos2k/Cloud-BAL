#!/usr/bin/env python3
"""Fresh-copy build and link the PR70 observer with the pinned Intel profile."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

EXPECTED_SOURCE_SHA256 = "5278f2df07216a3b6ba180d1e732cdaa7e7bc1194bac2e2e3261d338c12dfe5e"
EXPECTED_INTEL_VERSION = "ifx (IFX) 2026.0.0 20260331"
EXPECTED_IFX_SHA256 = "909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_one_link(source: Path, target: Path, expected: str | None = None) -> str:
    info = source.lstat()
    if not source.is_file() or source.is_symlink() or info.st_nlink != 1:
        raise ValueError(f"source must be regular one-link file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target_info = target.lstat()
    digest = sha256(target)
    if target_info.st_nlink != 1 or target.is_symlink() or (expected and digest != expected):
        raise ValueError(f"copy failed integrity check: {target}")
    return digest


def run(argv: list[str], cwd: Path, stdout_path: Path) -> None:
    with stdout_path.open("xb") as stream:
        result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {argv}; see {stdout_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--compile-argv", type=Path, required=True)
    parser.add_argument("--link-argv-json", type=Path, required=True)
    parser.add_argument("--retained-link-main", type=Path, required=True)
    parser.add_argument("--output-receipt", type=Path, required=True)
    args = parser.parse_args()

    if args.base.exists() or args.base.is_symlink():
        raise SystemExit(f"refusing to reuse build root: {args.base}")
    if sha256(args.source) != EXPECTED_SOURCE_SHA256:
        raise SystemExit("instrumented source hash mismatch")
    fc = Path(os.environ["CLOUD_BAL_FC"])
    fc_version = subprocess.run([str(fc), "--version"], text=True, capture_output=True, check=True).stdout.splitlines()[0]
    if fc_version != EXPECTED_INTEL_VERSION or sha256(fc) != EXPECTED_IFX_SHA256:
        raise SystemExit("pinned Intel ifx mismatch")

    compile_dir = args.base / "compile"
    link_dir = args.base / "link" / "main"
    executable_dir = args.base / "executable"
    source_dir = args.base / "source"
    for folder in (compile_dir, link_dir, executable_dir, source_dir):
        folder.mkdir(parents=True)
    source_copy = source_dir / "module_mp_kdm6.f90"
    source_hash = copy_one_link(args.source, source_copy, EXPECTED_SOURCE_SHA256)
    compile_copy = compile_dir / "module_mp_kdm6.f90"
    copy_one_link(source_copy, compile_copy, source_hash)

    compile_argv = args.compile_argv.read_text(encoding="utf-8").strip().split()
    compile_argv[0] = str(fc)
    compile_argv[-1] = "module_mp_kdm6.o"
    run(compile_argv, compile_dir, compile_dir / "compile.log")
    object_path = compile_dir / "module_mp_kdm6.o"
    object_hash = sha256(object_path)
    shutil.copy2(object_path, link_dir / "module_mp_kdm6.o")
    if (link_dir / "module_mp_kdm6.o").stat().st_nlink != 1:
        raise ValueError("compiled object copy is not one-link")

    retained_archive = args.retained_link_main / "libwrflib_pr65.a"
    archive = link_dir / "libwrflib_pr65.a"
    archive_original_hash = sha256(retained_archive)
    shutil.copy2(retained_archive, archive)
    if archive.is_symlink() or archive.stat().st_nlink != 1:
        raise ValueError("fresh archive copy is not one-link")
    archive_before_hash = sha256(archive)
    for basename, expected in (
        ("wrf.o", "9efa6ff4e33e30c5df9500188c6899a6c70b15ee64b81fa42798143d45a193a3"),
        ("module_wrf_top.o", "c6be23b7d27b6fe0f0a23671e61ccc6d276f1f7dc0b1d010bc5a0f1d25637537"),
    ):
        copy_one_link(args.retained_link_main / basename, link_dir / basename, expected)

    ar = shutil.which("ar")
    if not ar:
        raise SystemExit("ar is unavailable")
    ar_argv = [ar, "r", archive.name, "module_mp_kdm6.o"]
    run(ar_argv, link_dir, args.base / "archive_update.log")
    member_list = subprocess.run([ar, "t", archive.name], cwd=link_dir, text=True, capture_output=True, check=True).stdout.splitlines()
    if member_list.count("module_mp_kdm6.o") != 1:
        raise ValueError("fresh archive does not contain exactly one KDM6 member")
    member_bytes = subprocess.run([ar, "p", archive.name, "module_mp_kdm6.o"], cwd=link_dir, capture_output=True, check=True).stdout
    member_path = link_dir / "archive_member.o"
    member_path.write_bytes(member_bytes)
    if sha256(member_path) != object_hash or member_path.stat().st_nlink != 1:
        raise ValueError("archive member does not match instrumented object")

    argv_info = json.loads(args.link_argv_json.read_text(encoding="utf-8"))
    link_argv = argv_info["argv"]
    output_index = link_argv.index("-o") + 1
    link_argv[output_index] = str(executable_dir / "wrf.exe")
    run(link_argv, link_dir, args.base / "link.log")
    executable = executable_dir / "wrf.exe"
    if executable.is_symlink() or executable.stat().st_nlink != 1:
        raise ValueError("fresh executable is not one-link")

    receipt = {
        "schema": "pr70_native_volume_observer_build_v1",
        "base": str(args.base),
        "source": {"path": str(source_copy), "sha256": source_hash},
        "toolchain": {"ifx": str(fc), "version": fc_version, "sha256": sha256(fc)},
        "compile": {"argv": compile_argv, "cwd": str(compile_dir), "log": str(compile_dir / "compile.log"), "source_sha256": sha256(compile_copy), "object_sha256": object_hash},
        "archive": {"source": str(retained_archive), "source_sha256": archive_original_hash, "fresh_before_sha256": archive_before_hash, "fresh_after_sha256": sha256(archive), "member_name": "module_mp_kdm6.o", "member_count": member_list.count("module_mp_kdm6.o"), "member_sha256": sha256(member_path), "update_argv": ar_argv},
        "link": {"argv": link_argv, "cwd": str(link_dir), "log": str(args.base / "link.log"), "executable": str(executable), "executable_sha256": sha256(executable)},
    }
    args.output_receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"source_sha256": source_hash, "object_sha256": object_hash, "archive_sha256": receipt["archive"]["fresh_after_sha256"], "executable_sha256": receipt["link"]["executable_sha256"], "receipt": str(args.output_receipt)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
