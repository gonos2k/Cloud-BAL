#!/usr/bin/env python3
"""Run a native research command with declared write targets in a fresh tree.

Inputs are hash-monitored references. This helper does not chmod them or claim
that a running process cannot modify them. It checks only declared input and
output paths; it is not a sandbox and does not protect undeclared writes.
Mutable outputs must be new files under the run root, with no symlink or
pre-existing inode alias.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


class IsolationError(ValueError):
    """The requested run tree can overwrite or alias retained artifacts."""


def _regular_file_identity(path: Path) -> tuple[int, int, int]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise IsolationError(f"file is unavailable: {path}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise IsolationError(f"expected a regular non-symlink file: {path}")
    return info.st_dev, info.st_ino, info.st_nlink


def _single_link_input(path: Path) -> tuple[int, int, int]:
    identity = _regular_file_identity(path)
    if identity[2] != 1:
        raise IsolationError(f"input must be a detached single-link file: {path}")
    return identity


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise IsolationError(f"path is no longer a regular file: {path}")
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(descriptor)
        named = path.lstat()
        identity_before = (before.st_dev, before.st_ino, before.st_size,
                           before.st_mtime_ns, before.st_ctime_ns, before.st_nlink)
        identity_after = (after.st_dev, after.st_ino, after.st_size,
                          after.st_mtime_ns, after.st_ctime_ns, after.st_nlink)
        if identity_before != identity_after or \
                (named.st_dev, named.st_ino) != (after.st_dev, after.st_ino):
            raise IsolationError(f"file changed while hashing: {path}")
    except OSError as exc:
        raise IsolationError(f"cannot hash input: {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return digest.hexdigest()


def _run_root(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    try:
        current = Path(absolute.anchor)
        for component in absolute.parts[1:]:
            current = current / component
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise IsolationError(f"run root contains a symlink component: {current}")
        root = absolute.resolve(strict=True)
    except OSError as exc:
        raise IsolationError("run root must already exist") from exc
    if root != absolute or not root.is_dir():
        raise IsolationError("run root is not a directory")
    return root


def _output_parent(root: Path, candidate: Path) -> None:
    current = root
    for part in candidate.parts[:-1]:
        current = current / part
        try:
            info = current.lstat()
        except OSError as exc:
            raise IsolationError(f"output parent is unavailable: {current}") from exc
        if not stat.S_ISDIR(info.st_mode):
            raise IsolationError(f"output parent is not a real directory: {current}")


def _output_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise IsolationError(f"output must be relative to run root: {value}")
    if not candidate.parts or ".." in candidate.parts:
        raise IsolationError(f"output path is not a clean relative path: {value}")
    _output_parent(root, candidate)

    output = root.joinpath(candidate)
    try:
        output.lstat()
    except FileNotFoundError:
        return output
    except OSError as exc:
        raise IsolationError(f"cannot inspect output path: {output}") from exc
    raise IsolationError(f"mutable output already exists: {output}")


def validate_layout(run_root: Path, inputs: list[Path], outputs: list[str]) -> tuple[
    Path, list[Path], list[Path]
]:
    """Check input identities and reserve only new, detached output names."""
    root = _run_root(run_root)
    if not outputs:
        raise IsolationError("at least one mutable output must be declared")
    normalized_outputs = [os.path.normpath(name) for name in outputs]
    if len(set(normalized_outputs)) != len(normalized_outputs):
        raise IsolationError("duplicate mutable output path")

    for path in inputs:
        _single_link_input(path)
    input_paths = [path.resolve(strict=True) for path in inputs]
    if len(set(input_paths)) != len(input_paths):
        raise IsolationError("duplicate input path")
    input_names = {path.resolve(strict=True) for path in input_paths}
    for name in outputs:
        candidate = Path(name)
        if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
            raise IsolationError(f"output path is not a clean relative path: {name}")
        if root.joinpath(candidate).resolve(strict=False) in input_names:
            raise IsolationError(f"mutable output aliases an input path: {name}")
    output_paths = [_output_path(root, name) for name in outputs]
    normalized = [path.relative_to(root).as_posix() for path in output_paths]
    for index, name in enumerate(normalized):
        for other in normalized[index + 1:]:
            if other.startswith(name + "/") or name.startswith(other + "/"):
                raise IsolationError("one mutable output is a parent of another")
    return root, input_paths, output_paths


def run_isolated(
    run_root: Path,
    inputs: list[Path],
    outputs: list[str],
    command: list[str],
    reserved_outputs: list[str] | None = None,
) -> dict[str, object]:
    if not command:
        raise IsolationError("command is required")
    reserved_outputs = reserved_outputs or []
    root, input_paths, declared_paths = validate_layout(
        run_root, inputs, [*outputs, *reserved_outputs]
    )
    output_paths = declared_paths[:len(outputs)]
    input_before = {
        str(path): _sha256(path) for path in input_paths
    }
    completed = subprocess.run(command, cwd=root, check=False)
    output_records = []
    output_issues = []
    for path in output_paths:
        try:
            _output_parent(root, path.relative_to(root))
            _regular_file_identity(path)
            digest = _sha256(path)
            dev, ino, nlink = _regular_file_identity(path)
            output_records.append({
                "path": str(path.relative_to(root)),
                "sha256": digest,
                "device": dev,
                "inode": ino,
                "nlink": nlink,
            })
            if nlink != 1:
                output_issues.append(f"mutable output became hardlinked: {path}")
        except IsolationError as exc:
            output_issues.append(str(exc))

    input_after = {}
    input_read_issues = []
    for path in input_paths:
        try:
            _single_link_input(path)
            input_after[str(path)] = _sha256(path)
        except IsolationError as exc:
            input_read_issues.append(str(exc))
    input_before = {str(path): input_before[str(path)] for path in input_paths}
    changed_inputs = [
        path for path in input_before
        if input_before[path] != input_after.get(path)
    ]
    return {
        "run_root": str(root),
        "command": command,
        "returncode": completed.returncode,
        "inputs": [
            {"path": path, "sha256_before": input_before[path],
             "sha256_after": input_after.get(path)}
            for path in input_before
        ],
        "changed_inputs": changed_inputs,
        "input_read_issues": input_read_issues,
        "outputs": output_records,
        "output_issues": output_issues,
        "input_integrity": "PASS" if not changed_inputs and not input_read_issues else "FAIL",
        "output_isolation": "PASS" if not output_issues and len(output_records) == len(output_paths) else "FAIL",
        "limitations": "Only declared paths are checked. Input hashes are checked before and after execution; this is not an OS sandbox or write-protection boundary and undeclared writes are not protected.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--output", action="append", default=[],
                        help="required new output path relative to --run-root")
    parser.add_argument("--receipt", required=True,
                        help="new receipt path relative to --run-root")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="command after --")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        result = run_isolated(args.run_root, args.input, args.output, command,
                              reserved_outputs=[args.receipt])
        root = _run_root(args.run_root)
        receipt = _output_path(root, args.receipt)
        payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
        descriptor = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        print(json.dumps(result, sort_keys=True))
        if result["returncode"]:
            return int(result["returncode"])
        return 0 if (result["input_integrity"] == "PASS" and
                     result["output_isolation"] == "PASS") else 3
    except (IsolationError, OSError) as exc:
        print(f"run isolation rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
