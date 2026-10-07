#!/usr/bin/env python3
"""Run one observer executable with copied, hash-checked inputs and a receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

RUN_COMMAND = (
    "set -eo pipefail; "
    "source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/env/vars.sh --force >/dev/null 2>&1 "
    "|| { source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/env/vars.sh >/dev/null 2>&1 || exit 1; }; "
    "export LD_LIBRARY_PATH=/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib:${LD_LIBRARY_PATH:-}; "
    "source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh >/dev/null 2>&1 || exit 1; "
    "set -u; "
    "ulimit -s unlimited; export OMP_NUM_THREADS=68; env > launch_environment.txt; "
    "ldd ./wrf.exe > runtime_libraries.txt; exec ./wrf.exe > candidate_run.log 2>&1"
)
REQUIRED_OUTPUTS = frozenset({
    "candidate_run.log", "launch_environment.txt", "runtime_libraries.txt",
    "pr69_water.raw", "pr63_geometry.raw", "kdm6_first_call_pre.raw",
    "kdm6_first_call_post.raw", "pr67_kdm6_process.raw",
    "wrfout_d01_2026-08-16_12:00:00",
})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_regular_one_link(path: Path) -> bool:
    try:
        item = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISREG(item.st_mode) and item.st_nlink == 1


def is_real_directory_tree(path: Path) -> bool:
    """Reject symlinked directory components for the run directory path."""
    current = path.absolute()
    components = [current, *current.parents]
    for item in components:
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(info.st_mode):
            return False
    return True


def run(inputs_receipt: Path, executable: Path, run_dir: Path) -> dict[str, Any]:
    if run_dir.exists() or run_dir.is_symlink():
        raise ValueError(f"refusing to reuse run directory: {run_dir}")
    if not is_real_directory_tree(run_dir.parent):
        raise ValueError("run directory parent tree must contain only real directories")
    if not is_regular_one_link(inputs_receipt):
        raise ValueError("input receipt must be a regular one-link file")
    if not is_regular_one_link(executable):
        raise ValueError("observer executable must be a regular one-link file")
    prior = json.loads(inputs_receipt.read_text(encoding="utf-8"))
    if not prior.get("inputs"):
        raise ValueError("input receipt has no declared inputs")
    run_dir.mkdir(parents=True)
    inputs = []
    seen: set[str] = set()
    for row in prior.get("inputs", []):
        source = Path(row["path"])
        if source.name == "wrf.exe":
            continue
        if source.name in seen:
            raise ValueError(f"duplicate input basename: {source.name}")
        if not is_regular_one_link(source):
            raise ValueError(f"source input is not a regular one-link file: {source}")
        seen.add(source.name)
        destination = run_dir / source.name
        shutil.copy2(source, destination)
        digest = sha256(destination)
        if digest != row.get("sha256_before") or not is_regular_one_link(destination):
            raise ValueError(f"staged input does not match prior receipt: {source.name}")
        inputs.append({"path": source.name, "source": str(source), "sha256_before": digest})
    if not inputs:
        raise ValueError("input receipt has no physical run inputs after excluding wrf.exe")
    exe = run_dir / "wrf.exe"
    shutil.copy2(executable, exe)
    executable_sha = sha256(exe)
    if not is_regular_one_link(exe):
        raise ValueError("staged executable is not a regular one-link file")

    result = subprocess.run(["bash", "-c", RUN_COMMAND], cwd=run_dir, check=False)
    input_after = []
    for row in inputs:
        path = run_dir / row["path"]
        valid_file = is_regular_one_link(path)
        digest = sha256(path) if valid_file else ""
        input_after.append({"path": row["path"], "sha256_after": digest,
                            "same": valid_file and digest == row["sha256_before"],
                            "regular_one_link": valid_file,
                            "nlink": path.lstat().st_nlink if path.exists() or path.is_symlink() else 0})
    exe_valid_after = is_regular_one_link(exe)
    exe_after = sha256(exe) if exe_valid_after else ""
    output_paths = [path for path in sorted(run_dir.iterdir())
                    if path.name not in seen and path.name != "wrf.exe" and path.name != "run_receipt.json"]
    outputs = []
    for path in output_paths:
        regular_one_link = is_regular_one_link(path)
        outputs.append({"path": path.name,
                        "sha256": sha256(path) if regular_one_link else "",
                        "regular_one_link": regular_one_link,
                        "nlink": path.lstat().st_nlink if path.exists() or path.is_symlink() else 0,
                        "size_bytes": path.stat().st_size if regular_one_link else 0})
    executable_input = {"path": str(exe), "sha256_before": executable_sha,
                        "sha256_after": exe_after,
                        "regular_one_link": exe_valid_after,
                        "nlink": exe.lstat().st_nlink if exe.exists() or exe.is_symlink() else 0}
    output_names = {row["path"] for row in outputs if row["regular_one_link"] and row["size_bytes"] > 0}
    outputs_valid = (REQUIRED_OUTPUTS <= output_names and len(outputs) > 0 and
                     all(row["regular_one_link"] and row["size_bytes"] > 0 for row in outputs))
    receipt = {
        "schema": "pr69_water_observer_run_receipt_v1",
        "run_root": str(run_dir),
        "command": ["bash", "-c", RUN_COMMAND],
        "returncode": result.returncode,
        "input_integrity": "PASS" if all(row["same"] and row["regular_one_link"] and row["nlink"] == 1 for row in input_after)
                          and exe_valid_after and exe_after == executable_sha else "FAIL",
        "output_isolation": "PASS" if outputs_valid else "FAIL",
        "inputs": [*inputs, executable_input],
        "input_after": input_after,
        "executable": {"source": str(executable), **executable_input},
        "outputs": outputs,
    }
    receipt_path = run_dir / "run_receipt.json"
    with receipt_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if not is_regular_one_link(receipt_path):
        raise ValueError("run receipt is not a regular one-link file")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs-receipt", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = run(args.inputs_receipt, args.executable, args.run_dir)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({key: receipt[key] for key in
                      ("returncode", "input_integrity", "output_isolation", "run_root")}, indent=2))
    return 0 if receipt["returncode"] == 0 and receipt["input_integrity"] == "PASS" and receipt["output_isolation"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
