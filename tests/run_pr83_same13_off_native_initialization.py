#!/usr/bin/env python3
"""Run the shared detached native initializer for the MODE_OFF control."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from run_pr82_same13_native_initialization import (
    build_parser, initialization_receipt_contract, run_initialization,
    write_initialization_receipt,
)

WORKSPACE = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL")
EXPECTED_OFF_INPUT_SHA256 = "6ed69cbd2bdb8d128dbd7273ac8de216fe4537748a0e4ca474213ac408060730"
EXPECTED_OFF_SOURCE_NAMELIST_SHA256 = "59e949a1a9feffec06204f8abc9b090b3c294e1a501e9f9599cbfc10503646f6"
OFF_CHAIN_ARTIFACTS = {
    "off_wps": Path("/var/tmp/pr83_same13_off_20261013c/build/same13_off.wps"),
    "off_wps_readback": Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr83_same13_off_20261013f/build/readback.json"),
    "off_wps_mapped_witness": Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr83_same13_off_20261013f/build/canonical_mapped_witness.raw"),
    "off_metgrid": WORKSPACE / "scratch/pr83_same13_off_metgrid_20261013c/met_em.d01.2026-08-16_13:00:00.nc",
    "off_metgrid_readback": WORKSPACE / "scratch/pr83_same13_off_metgrid_20261013c/readback.json",
    "off_real_boundary_wrfinput": WORKSPACE / "scratch/pr83_same13_off_real_boundary_20261013a/wrfinput_d01",
    "off_real_boundary_wrfbdy": WORKSPACE / "scratch/pr83_same13_off_real_boundary_20261013a/wrfbdy_d01",
    "off_real_boundary_contract": WORKSPACE / "scratch/pr83_same13_off_real_boundary_20261013a/input_contract.json",
    "off_real_boundary_readback": WORKSPACE / "scratch/pr83_same13_off_real_boundary_20261013a/boundary_readback.json",
}


def validate_off_source_namelist(source: Path) -> str:
    """Pin the retained MODE_OFF start configuration before any native launch."""
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != EXPECTED_OFF_SOURCE_NAMELIST_SHA256:
        raise ValueError("MODE_OFF native control requires the reviewed same13 source namelist")
    return actual


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_initialization(
        args,
        required_baseline_input=EXPECTED_OFF_INPUT_SHA256,
        control_role="MODE_OFF_MASS_ONLY",
        required_source_namelist_sha=EXPECTED_OFF_SOURCE_NAMELIST_SHA256,
        allow_prior=False,
        chain_artifacts=OFF_CHAIN_ARTIFACTS,
        runner_source=Path(__file__),
    )


if __name__ == "__main__":
    raise SystemExit(main())
