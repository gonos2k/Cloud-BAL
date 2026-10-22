#!/usr/bin/env python3
"""Run selected C1 columns through the read-only warm/cold stage observer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess

STAGE_FILES = (
    "pr85_kdm6_warm_budget.raw", "pr85_kdm6_cold_budget.raw",
    "pr85_kdm6_freezing_budget.raw", "pr85_kdm6_melt_budget.raw",
    "pr85_rain_freezing_budget.raw", "pr85_ice_transition_branch.raw",
    "pr85_kdm6_cutoff_budget.raw", "pr87_rain_sedimentation_budget.raw",
    "pr85_ice_sedimentation_budget.raw", "pr85_graupel_sedimentation_budget.raw",
    "pr87_qn_public_store.raw", "pr87_ice_extinction.raw",
    "pr87_ice_sublimation_pending.raw", "pr87_graupel_melt.raw",
    "pr85_kdm6_psd_boundary.raw",
    "pr67_kdm6_process.raw",
    "pr99_process_stage_compact.raw",
)
REUSED_STREAMS = (
    "pr97_liquid_columns.raw", "pr85_kdm6_cutoff_budget.raw",
    "pr87_rain_sedimentation_budget.raw", "pr85_ice_sedimentation_budget.raw",
    "pr98_sed_face.raw", "pr67_kdm6_process.raw",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def run_arm(executable: Path, source: Path, arm: str, pre: Path,
            native_post: Path, run_dir: Path, build: dict,
            build_manifest_path: Path, profile_path: Path) -> dict:
    run_dir.mkdir(parents=True, exist_ok=False)
    replay = run_dir / "replay.exe"
    shutil.copy2(executable, replay)
    if sha256(replay) != build.get("linked_executable_sha256"):
        raise ValueError("selected-process executable differs from its build receipt")
    stack_limit, _ = resource.getrlimit(resource.RLIMIT_STACK)
    if os.environ.get("OMP_NUM_THREADS") != "1" or stack_limit != resource.RLIM_INFINITY:
        raise ValueError("selected-process replay requires one thread and unlimited stack")
    log_path = run_dir / "replay.log"
    with log_path.open("wb") as log:
        completed = subprocess.run([str(replay), str(pre.resolve())], cwd=run_dir,
                                   env=os.environ.copy(), stdout=log,
                                   stderr=subprocess.STDOUT, check=False)
    replay_post = run_dir / "replay_post.raw"
    if completed.returncode != 0:
        raise RuntimeError(f"{arm} replay returned {completed.returncode}; see {log_path}")
    if not replay_post.is_file() or sha256(replay_post) != sha256(native_post):
        raise RuntimeError(f"{arm} replay did not reproduce native 17-field and XLAND state")
    log = log_path.read_text(errors="replace")
    if "REPLAY COMPLETED FULL ACTIVE TILE" not in log:
        raise RuntimeError(f"{arm} replay completion marker is missing")
    missing = [name for name in STAGE_FILES if not (run_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"{arm} replay omitted stage files: {missing}")
    reused_streams = {}
    for name in REUSED_STREAMS:
        original = pre.parent / name
        equal = original.is_file() and sha256(run_dir / name) == sha256(original)
        if not equal:
            raise RuntimeError(f"{arm} instrumentation replay changed existing stream: {name}")
        reused_streams[name] = sha256(run_dir / name)
    return {
        "schema": "pr99_selected_process_replay_v1", "arm": arm,
        "returncode": completed.returncode,
        "completion_marker_observed": True,
        "all_17_fields_and_XLAND_byte_equal": True,
        "executable_sha256": sha256(replay), "prepared_source_sha256": sha256(source),
        "build_manifest_sha256": sha256(build_manifest_path),
        "compiler_profile": "tests/intel_toolchain.sh (pinned Intel 2026.0 ifx)",
        "compiler_profile_sha256": sha256(profile_path),
        "pinned_ifx_sha256": build["pinned_ifx_sha256"],
        "pinned_mpiifx_sha256": build["pinned_mpiifx_sha256"],
        "omp_threads": 1, "unlimited_stack": True,
        "pre_sha256": sha256(pre), "native_post_sha256": sha256(native_post),
        "replay_post_sha256": sha256(replay_post),
        "stage_file_sha256": {name: sha256(run_dir / name) for name in STAGE_FILES},
        "reused_pr98_streams_byte_equal": reused_streams,
        "scratch_directory": str(run_dir.resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build-manifest", type=Path, required=True)
    parser.add_argument("--native-root", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if not args.scratch_root.is_dir() or any(args.scratch_root.iterdir()):
        raise ValueError("scratch root must exist and be empty")
    args.output_root.mkdir(parents=True, exist_ok=True)
    build = json.loads(args.build_manifest.read_text(encoding="utf-8"))
    manifests = {}
    for arm in ("OFF", "HYDRO", "COUPLED"):
        native = Path(str(args.native_root).format(arm=arm))
        manifest = run_arm(args.executable, args.source, arm,
            native / "kdm6_first_call_pre.raw", native / "kdm6_first_call_post.raw",
            args.scratch_root / arm, build, args.build_manifest,
            Path(__file__).resolve().parents[1] / "tests/intel_toolchain.sh")
        (args.output_root / f"{arm}_selected_process_replay.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        manifests[arm] = manifest
        print(f"{arm}: completed and byte-equal")


if __name__ == "__main__":
    main()
