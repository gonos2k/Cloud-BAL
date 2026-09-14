#!/usr/bin/env python3
"""Run two volumes in one process and verify LUT geometry changes at the boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import numpy as np

from test_radar_remap_lut import read_fortran_record
from test_radar_remap import check_output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--radar-root", type=Path, required=True)
    parser.add_argument("--base-snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    command = [
        "python",
        str(Path(__file__).with_name("run_radar_remap.py")),
        "--build",
        str(args.build.resolve()),
        "--radar-root",
        str(args.radar_root.resolve()),
        "--base-snapshot",
        str(args.base_snapshot.resolve()),
        "--max-times",
        "2",
        "--second-first-gate-m",
        "200",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    receipt = json.loads(result.stdout) if result.stdout.strip() else None
    if result.returncode != 0 or not receipt or not receipt.get("accepted"):
        raise AssertionError(f"two-volume run failed: {result.returncode}\n{result.stderr}")
    if not receipt.get("second_geometry_applied"):
        raise AssertionError("second-volume geometry mutation was not observed")

    evidence = Path(receipt["evidence"])
    output_summary = check_output(
        evidence / "final_lapsprd/v04/262281300.v04"
    )
    log = (evidence / "run.log").read_text(errors="replace")
    geometry_lines = [
        line for line in log.splitlines() if "LUT geometry first gate / spacing" in line
    ]
    if len(geometry_lines) != 2:
        raise AssertionError(f"expected two LUT geometry records, got {geometry_lines}")
    if "125.0000" not in geometry_lines[0] or "200.0000" not in geometry_lines[1]:
        raise AssertionError(f"unexpected geometry sequence: {geometry_lines}")

    root = Path(receipt["private"]) / "runroot"
    geometry = (root / "static/vxx/radar_lut_geometry.GSN").read_text()
    if "200.0000" not in geometry or "250.0000" not in geometry:
        raise AssertionError(f"final LUT geometry is not second-volume metadata: {geometry!r}")

    lut_path = root / "static/vxx/gate_elev_to_projran_lut.GSN"
    values = read_fortran_record(lut_path)
    expected = np.floor((200.0 + np.arange(3) * 250.0) / 500.0).astype(np.int32)
    if not np.array_equal(values[:3], expected):
        raise AssertionError(f"second-volume LUT {values[:3].tolist()} != {expected.tolist()}")

    report = {
        "status": "PASS",
        "receipt": receipt,
        "geometry_lines": geometry_lines,
        "final_geometry": geometry.strip(),
        "final_gate_1_to_3": values[:3].tolist(),
        "expected_gate_1_to_3": expected.tolist(),
        "final_output": output_summary,
        "scope": "same-process two-volume LUT regeneration; time remains provisional",
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"RADAR_REMAP_TWO_VOLUME_PASS {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
