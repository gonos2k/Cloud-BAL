#!/usr/bin/env python3
"""Run one frozen full-tile C1 call in a clean directory and bind its outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

C1_DIAGNOSTIC_REPLAY_EXE = "94d3d35b1c204d00cc4df548521dc6ad4088b76e7d37db1a9a5d86da975bebd5"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def row_count(path: Path, prefix: str) -> int:
    with path.open(encoding="ascii") as source:
        return sum(line.startswith(prefix) for line in source)


def run(executable_source: Path, pre: Path, native_post: Path,
        run_dir: Path) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    if any(run_dir.iterdir()):
        raise ValueError("isolated replay directory must start empty")
    executable = run_dir / "replay.exe"
    shutil.copy2(executable_source, executable)
    before_exe = sha256(executable)
    if before_exe != C1_DIAGNOSTIC_REPLAY_EXE:
        raise ValueError("replay executable is not the frozen C1 executable")
    with (run_dir / "replay.log").open("wb") as log:
        completed = subprocess.run([str(executable), str(pre.resolve())], cwd=run_dir,
            env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT, check=False)
    after_exe = sha256(executable)
    if after_exe != before_exe:
        raise ValueError("replay executable changed during its invocation")
    replay_post = run_dir / "replay_post.raw"
    if completed.returncode != 0:
        raise ValueError(f"frozen replay returned {completed.returncode}; see replay.log")
    if not replay_post.is_file() or sha256(replay_post) != sha256(native_post):
        raise ValueError("replay post state does not equal the receipt-bound native post")
    outputs = {
        "liquid_columns": run_dir / "pr97_liquid_columns.raw",
        "cutoff_rows": run_dir / "pr85_kdm6_cutoff_budget.raw",
        "rain_rows": run_dir / "pr87_rain_sedimentation_budget.raw",
        "ice_rows": run_dir / "pr85_ice_sedimentation_budget.raw",
    }
    if any(not path.is_file() for path in outputs.values()):
        raise ValueError("replay did not emit every required source ledger")
    manifest = {
        "schema": "pr98_isolated_c1_t1_replay_v1", "returncode": completed.returncode,
        "executable_source": str(executable_source.resolve()),
        "executable_before_sha256": before_exe, "executable_after_sha256": after_exe,
        "input_pre_sha256": sha256(pre), "native_post_sha256": sha256(native_post),
        "replay_post_sha256": sha256(replay_post),
        "liquid_columns_sha256": sha256(outputs["liquid_columns"]),
        "cutoff_rows_sha256": sha256(outputs["cutoff_rows"]),
        "rain_rows_sha256": sha256(outputs["rain_rows"]),
        "ice_rows_sha256": sha256(outputs["ice_rows"]),
        "row_counts": {
            "liquid_columns": row_count(outputs["liquid_columns"], "LIQCOL"),
            "cutoff_events": row_count(outputs["cutoff_rows"], "PR85_KDM6_CUTOFF"),
            "rain_sedimentation": row_count(outputs["rain_rows"], "PR87_RAIN_SED"),
            "ice_sedimentation": row_count(outputs["ice_rows"], "PR85_ICE_SED")},
        "profile": "tests/intel_toolchain.sh",
        "profile_sha256": sha256(Path(__file__).resolve().parents[1] / "tests/intel_toolchain.sh"),
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"), "unlimited_stack": True,
        "scratch_directory": str(run_dir.resolve()),
    }
    manifest_path = run_dir / "pr98_replay_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable-source", type=Path, required=True)
    parser.add_argument("--pre", type=Path, required=True)
    parser.add_argument("--native-post", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = run(args.executable_source, args.pre, args.native_post, args.run_dir)
    print(json.dumps({"status": "COMPLETE", "manifest": str(args.run_dir / "pr98_replay_manifest.json"),
                      "row_counts": manifest["row_counts"]}, indent=2))


if __name__ == "__main__":
    main()
