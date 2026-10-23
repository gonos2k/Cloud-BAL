#!/usr/bin/env python3
"""Run a hash-bound diagnostic once, in a new directory outside checkouts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import shutil
import subprocess
from datetime import datetime, timezone


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_pin(pin: dict) -> Path:
    path = Path(pin["path"])
    if not path.is_absolute() or not path.is_file() or sha256(path) != pin["sha256"]:
        raise ValueError(f"missing or changed pinned file: {path}")
    return path


def file_name(name: str) -> str:
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError(f"expected a single output/input filename: {name}")
    return name


def unlimited_stack() -> None:
    resource.setrlimit(resource.RLIMIT_STACK, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))


def has_marker(path: Path, marker: str) -> bool:
    token, tail = marker.encode("ascii"), b""
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            joined = tail + block
            if token in joined:
                return True
            tail = joined[-len(token):]
    return False


def run(manifest: Path) -> dict:
    manifest_bytes = manifest.read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    spec = json.loads(manifest_bytes)
    if spec.get("schema") != "pr101_guarded_replay_v1":
        raise ValueError("unsupported replay manifest")
    for key in ("case", "scope"):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise ValueError(f"missing replay {key}")
    arguments = spec.get("arguments")
    if (not isinstance(arguments, list) or any(not isinstance(value, str)
            or Path(value).is_absolute() or ".." in Path(value).parts for value in arguments)):
        raise ValueError("arguments must use staged relative filenames, not external paths")
    directory = Path(spec["directory"])
    if (not directory.is_absolute() or directory.resolve() != directory
            or directory.exists() or directory.is_symlink()
            or any((parent / ".git").exists() for parent in directory.parents)):
        raise ValueError("replay requires a new absolute scratch directory outside checkouts")
    executable = check_pin(spec["executable"])
    inputs = {file_name(name): check_pin(pin) for name, pin in spec["inputs"].items()}
    reserved = {"replay.exe", "launch_manifest.json", "run.log", "receipt.json"}
    if set(inputs) & reserved:
        raise ValueError("staged input name conflicts with a guard artifact")
    expected = {file_name(name): digest for name, digest in spec["expected_outputs"].items()}
    if (not expected or set(expected) & (set(inputs) | reserved)
            or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                   for value in expected.values())):
        raise ValueError("expected outputs must be separate from staged inputs and guard artifacts")
    pins = [spec["executable"], *spec["inputs"].values(), *spec.get("bindings", []),
            {"path": str(manifest.resolve()), "sha256": manifest_sha}]
    for pin in pins:
        check_pin(pin)
    if (not isinstance(spec.get("completion_markers"), list) or not spec["completion_markers"]
            or any(not isinstance(value, str) or not value or not value.isascii()
                   for value in spec["completion_markers"])):
        raise ValueError("at least one nonempty completion marker is required")
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(executable, directory / "replay.exe")
    (directory / "replay.exe").chmod(0o700)
    for name, source in inputs.items():
        shutil.copyfile(source, directory / name)
    (directory / "launch_manifest.json").write_text(json.dumps(spec, indent=2) + "\n")
    if sha256(directory / "replay.exe") != spec["executable"]["sha256"]:
        raise ValueError("staged executable changed before launch")
    for name in inputs:
        if sha256(directory / name) != spec["inputs"][name]["sha256"]:
            raise ValueError(f"staged input changed before launch: {name}")
    environment = {**os.environ, "OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE"}
    argv = [str(directory / "replay.exe"), *arguments]
    started = datetime.now(timezone.utc).isoformat()
    returncode, execution_error = None, None
    with (directory / "run.log").open("xb") as log:
        try:
            completed = subprocess.run(argv, cwd=directory, env=environment,
                stdout=log, stderr=subprocess.STDOUT, check=False, preexec_fn=unlimited_stack)
            returncode = completed.returncode
        except (OSError, subprocess.SubprocessError) as error:
            execution_error = str(error)
    issues = []
    for path in directory.iterdir():
        if path.is_symlink():
            issues.append(f"unexpected symlink artifact: {path.name}")
    for pin in pins:
        try:
            check_pin(pin)
        except (OSError, ValueError) as error:
            issues.append(str(error))
    for name, pin in {"replay.exe": spec["executable"], **spec["inputs"]}.items():
        if not (directory / name).is_file() or sha256(directory / name) != pin["sha256"]:
            issues.append(f"staged file changed during replay: {name}")
    outputs = {name: not (directory / name).is_symlink()
               and (directory / name).is_file() and sha256(directory / name) == digest
               for name, digest in expected.items()}
    markers = {value: has_marker(directory / "run.log", value)
               for value in spec["completion_markers"]}
    record = {"schema": "pr101_guarded_replay_receipt_v1", "case": spec["case"],
        "scope": spec["scope"], "directory": str(directory), "argv": argv,
        "start_utc": started, "end_utc": datetime.now(timezone.utc).isoformat(),
        "returncode": returncode, "execution_error": execution_error,
        "manifest_sha256": manifest_sha,
        "guard_sha256": sha256(Path(__file__)), "expected_outputs": outputs,
        "completion_markers": markers, "preservation_issues": issues,
        "environment": {key: environment.get(key) for key in
                        ("OMP_NUM_THREADS", "OMP_DYNAMIC", "LD_LIBRARY_PATH")},
        "artifacts": {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)}
                      for p in sorted(directory.iterdir()) if p.is_file() and not p.is_symlink()}}
    record["status"] = ("COMPLETE" if returncode == 0 and not execution_error and not issues
                        and all(outputs.values()) and all(markers.values()) else "INCOMPLETE")
    with (directory / "receipt.json").open("x") as stream:
        json.dump(record, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = run(args.manifest)
    print(Path(result["directory"]) / "receipt.json")
    return 0 if result["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
