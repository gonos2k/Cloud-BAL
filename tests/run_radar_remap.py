#!/usr/bin/env python3
"""Run the isolated radar remapper against one private GSN input set."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time

import netCDF4


def inventory(root: Path) -> dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def verify_manifest(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing build manifest: {path}")
    result = subprocess.run(
        ["sha256sum", "-c", path.name],
        cwd=path.parent,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"build manifest verification failed: {path}\n{result.stdout}{result.stderr}"
        )


def manifest_digest(path: Path) -> str:
    fields = path.read_text().split()
    if not fields:
        raise RuntimeError(f"empty executable digest manifest: {path}")
    return fields[0]


def validate_tilt_files(
    radar_root: Path, radar_time: str, expected_tilts: int
) -> list[Path]:
    if expected_tilts < 1 or expected_tilts > 20:
        raise RuntimeError("expected tilt count must be between 1 and 20")
    expected_names = {
        f"{radar_time}_elev{tilt:02d}" for tilt in range(1, expected_tilts + 1)
    }
    radar_files = sorted(radar_root.glob("*_elev??"))
    actual_names = {path.name for path in radar_files}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        raise RuntimeError(
            "radar input must contain one contiguous tilt sequence; "
            f"missing={missing} unexpected={unexpected}"
        )
    return radar_files


def parse_args(repo: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path)
    parser.add_argument("--radar-root", type=Path, required=True)
    parser.add_argument(
        "--base-snapshot",
        type=Path,
        default=repo / "scratch/cp02_traced13_9qidm_8b/input_snapshot",
    )
    parser.add_argument(
        "--expected-tilts",
        type=int,
        default=9,
        help="number of contiguous elevXX files required for this GSN run",
    )
    parser.add_argument(
        "--max-times",
        type=int,
        default=1,
        help="number of volumes requested from one remapper process",
    )
    parser.add_argument(
        "--second-first-gate-m",
        type=float,
        help="change every tilt's first-gate metadata after volume one",
    )
    return parser.parse_args()


def set_first_gate(root: Path, first_gate_m: float) -> None:
    for path in sorted(root.glob("*_elev??")):
        with netCDF4.Dataset(path, "r+") as dataset:
            dataset.variables["firstGateRangeV"][...] = first_gate_m
            dataset.variables["firstGateRangeZ"][...] = first_gate_m


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    workspace = repo.parent
    args = parse_args(repo)
    if args.max_times < 1:
        raise RuntimeError("max-times must be positive")
    if args.second_first_gate_m is not None and args.max_times < 2:
        raise RuntimeError("second-first-gate-m requires max-times >= 2")
    build = args.build
    if build is None:
        build = Path((repo / "scratch/radar_remap_build.path").read_text().strip())
    build = build.resolve()
    radar_root = args.radar_root.resolve()
    base = args.base_snapshot.resolve()
    for name in ("inputs.sha256", "runtime.sha256", "launcher.sha256"):
        verify_manifest(build / name)
    isolated = repo / "src/upstream/radar/remap"
    ncgen_bin = (
        workspace
        / "klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/bin"
    )

    for name in ("static", "cdl", "time"):
        if not (base / name).is_dir():
            raise RuntimeError(f"missing input snapshot directory: {base / name}")

    evidence = Path(tempfile.mkdtemp(prefix="radar_remap_gsn_", dir=repo / "scratch"))
    private = Path(tempfile.mkdtemp(prefix="radar_remap."))
    root = private / "runroot"
    root.mkdir()
    for name in ("static", "cdl", "time"):
        shutil.copytree(base / name, root / name)
    radar_time = next(
        line.strip()
        for line in (root / "time/systime.dat").read_text().splitlines()
        if line.strip().isdigit() and len(line.strip()) == 9
    )

    radar_files = validate_tilt_files(radar_root, radar_time, args.expected_tilts)
    shutil.copyfile(workspace / "ANAL/NE57/DABA/cdl/v00.cdl", root / "cdl/v00.cdl")
    shutil.copyfile(workspace / "ANAL/NE57/DABA/cdl/vrc.cdl", root / "cdl/vrc.cdl")
    shutil.copyfile(isolated / "cdl/v00.cdl", root / "cdl/v00.cdl")
    shutil.copytree(radar_root, private / "radar")

    for name in ("v04", "vrc", "log", "tmp"):
        (root / "lapsprd" / name).mkdir(parents=True)
    (root / "static/vxx").mkdir()
    (root / "static/remap.nl").write_text(
        f""" &remap_nl
 N_RADARS_REMAP=1, MAX_TIMES={args.max_times}, PATH_TO_VRC_NL='rdr',
 ref_min=0., MIN_REF_SAMPLES=4, MIN_VEL_SAMPLES=4, DGR=1.1,
 PATH_TO_RADAR_A='{private / 'radar'}', LAPS_RADAR_EXT_A='v04',
 /\n"""
    )

    before = inventory(private)
    (evidence / "inputs.json").write_text(json.dumps(before, indent=2) + "\n")
    shutil.copytree(private, evidence / "input_snapshot")

    executable = build / "klps_radr_ingt.exe"
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    manifest = evidence / "executable.sha256"
    manifest.write_text(f"{digest}  {executable}\n")

    command = (
        f"set -euo pipefail\n"
        f". {shlex.quote(str(repo / 'tests/intel_toolchain.sh'))}\n"
        f"ulimit -s unlimited\n"
        f"export OMP_NUM_THREADS=1 OMP_DYNAMIC=false\n"
        f"export LAPS_DATA_ROOT={shlex.quote(str(root))} TMPDIR={shlex.quote(str(private))}\n"
        f"export PATH={shlex.quote(str(ncgen_bin))}:$PATH\n"
        f"cd {shlex.quote(str(private))}\n"
        f"python3 {shlex.quote(str(repo / 'tools/landlock_run.py'))} "
        f"{shlex.quote(str(private))} timeout 300 python3 "
        f"{shlex.quote(str(repo / 'tools/run_bound_executable.py'))} "
        f"--sha256-file {shlex.quote(str(manifest))} {shlex.quote(str(executable))}\n"
    )
    invocation = {
        "argv": ["bash", "-c", command],
        "started": time.time(),
        "scope": "ISOLATED_REMAP_GSN_RAW_INPUT_NO_DEALIAS_NO_TARGET_AUTHORITY",
        "raw_input": str(radar_root),
        "source_cdl": str(isolated / "cdl/v00.cdl"),
    }
    (evidence / "invocation.json").write_text(json.dumps(invocation, indent=2) + "\n")
    output = root / "lapsprd/v04" / f"{radar_time}.v04"
    log_path = evidence / "run.log"
    second_geometry_applied = False
    with log_path.open("w") as log:
        if args.second_first_gate_m is None:
            result = subprocess.run(
                ["bash", "-c", command], stdout=log, stderr=subprocess.STDOUT
            )
        else:
            process = subprocess.Popen(
                ["bash", "-c", command], stdout=log, stderr=subprocess.STDOUT
            )
            while process.poll() is None:
                first_volume_ready = output.is_file()
                completed_marker = "Volume completed, return from remap_sub" in log_path.read_text(
                    errors="replace"
                )
                if first_volume_ready or completed_marker:
                    set_first_gate(private / "radar", args.second_first_gate_m)
                    second_geometry_applied = True
                    break
                time.sleep(0.01)
            return_code = process.wait()
            result = subprocess.CompletedProcess(
                ["bash", "-c", command], return_code
            )

    after = inventory(private)
    second_geometry_required = args.second_first_gate_m is not None
    accepted = (
        result.returncode == 0
        and output.is_file()
        and (not second_geometry_required or second_geometry_applied)
    )
    receipt = {
        "exit": result.returncode,
        "private": str(private),
        "build": str(build),
        "build_inputs_sha256": str(build / "inputs.sha256"),
        "build_runtime_sha256": str(build / "runtime.sha256"),
        "build_launcher_sha256": str(build / "launcher.sha256"),
        "build_executable_sha256": str(build / "executable.sha256"),
        "common_build": (build / "common_build.path").read_text().strip()
        if (build / "common_build.path").is_file()
        else None,
        "common_archive_sha256": str(build / "common_archive.sha256"),
        "common_archive": str(
            Path((build / "common_build.path").read_text().strip()) / "libcommon.a"
        ),
        "common_archive_digest": manifest_digest(build / "common_archive.sha256"),
        "link_map": str(build / "link.map"),
        "executable_digest": digest,
        "raw_input": str(radar_root),
        "radar_time": radar_time,
        "expected_tilts": args.expected_tilts,
        "max_times": args.max_times,
        "second_first_gate_m": args.second_first_gate_m,
        "second_geometry_applied": second_geometry_applied,
        "base_snapshot": str(base),
        "output": str(output),
        "output_exists": output.is_file(),
        "accepted": accepted,
        "status_contract": (
            "accepted only when process exit is zero and the complete output exists"
        ),
        "added": sorted(after.keys() - before.keys()),
        "changed": sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
        "content_validation": "RUN test_radar_remap.py --output <copied output>",
        "authority": "PROVISIONAL_RAW_DECODER_BINDING_ONLY",
    }
    (evidence / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if output.is_file():
        shutil.copytree(root / "lapsprd", evidence / "final_lapsprd")
    print(json.dumps({"evidence": str(evidence), **receipt}, indent=2))
    if result.returncode == 0 and second_geometry_required \
            and not second_geometry_applied:
        return 1
    if result.returncode == 0 and not output.is_file():
        return 1
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
