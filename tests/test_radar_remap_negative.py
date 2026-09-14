#!/usr/bin/env python3
"""Actual fail-closed probes for malformed isolated radar remap inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import netCDF4
import numpy as np

from run_radar_remap import validate_tilt_files
from test_radar_remap import check_output


def clone_without_or_with_wrong_var(source: Path, target: Path, mode: str) -> None:
    with netCDF4.Dataset(source) as src, netCDF4.Dataset(
        target, "w", format="NETCDF4_CLASSIC"
    ) as dst:
        for name, dimension in src.dimensions.items():
            dst.createDimension(name, len(dimension) if not dimension.isunlimited() else None)
        for name in src.ncattrs():
            dst.setncattr(name, src.getncattr(name))
        for name, src_var in src.variables.items():
            if mode == "missing_nyquist" and name == "nyquist":
                continue
            dimensions = src_var.dimensions
            dtype = src_var.dtype
            if mode == "wrong_nyquist_type" and name == "nyquist":
                dtype = "i2"
            if mode == "wrong_velocity_shape" and name == "V":
                dimensions = ("radial",)
            fill_value = (
                src_var.getncattr("_FillValue")
                if "_FillValue" in src_var.ncattrs() and dtype != "i2"
                else None
            )
            if fill_value is None:
                dst_var = dst.createVariable(name, dtype, dimensions)
            else:
                dst_var = dst.createVariable(
                    name, dtype, dimensions, fill_value=fill_value
                )
            for attr in src_var.ncattrs():
                if attr != "_FillValue":
                    dst_var.setncattr(attr, src_var.getncattr(attr))
            if mode == "wrong_velocity_shape" and name == "V":
                dst_var[:] = np.zeros((len(src.dimensions["radial"]),), dtype=dtype)
            else:
                values = src_var[:]
                if mode == "wrong_nyquist_type" and name == "nyquist":
                    values = np.asarray(values, dtype=np.int16)
                if mode in {"short_gate_count", "short_final_gate_count"} \
                        and name in {"numGatesV", "numGatesZ"} \
                        and (mode == "short_gate_count" or source.name.endswith("elev09")):
                    values = np.asarray(values, dtype=src_var.dtype)
                    values[...] = 100
                if mode in {"zero_gate_count", "oversized_gate_count"} \
                        and name in {"numGatesV", "numGatesZ"}:
                    values = np.asarray(values, dtype=src_var.dtype)
                    values[...] = 0 if mode == "zero_gate_count" else 921
                dst_var[:] = values


def set_geometry(root: Path, first_gate_m: float | None, spacing_m: float | None) -> None:
    for path in sorted(root.glob("*_elev??")):
        with netCDF4.Dataset(path, "r+") as dataset:
            if first_gate_m is not None:
                dataset.variables["firstGateRangeV"][...] = first_gate_m
                dataset.variables["firstGateRangeZ"][...] = first_gate_m
            if spacing_m is not None:
                dataset.variables["gateSizeV"][...] = spacing_m
                dataset.variables["gateSizeZ"][...] = spacing_m


def run_case(
    mode: str, radar: Path, build: Path, base_snapshot: Path
) -> tuple[int, dict[str, object] | None, str]:
    command = [
        "python",
        str(Path(__file__).with_name("run_radar_remap.py")),
        "--build",
        str(build.resolve()),
        "--radar-root",
        str(radar),
        "--base-snapshot",
        str(base_snapshot.resolve()),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    receipt = json.loads(result.stdout) if result.stdout.strip() else None
    return result.returncode, receipt, result.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--radar-root", type=Path, required=True)
    parser.add_argument("--base-snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="radar_remap_negative_") as temp:
        work = Path(temp)
        cases: list[dict[str, object]] = []
        for mode in (
            "missing_nyquist",
            "wrong_nyquist_type",
            "wrong_velocity_shape",
            "zero_gate_count",
            "oversized_gate_count",
        ):
            radar = work / mode
            radar.mkdir()
            for source in sorted(args.radar_root.glob("*_elev??")):
                destination = radar / source.name
                if source.name.endswith("elev01"):
                    clone_without_or_with_wrong_var(source, destination, mode)
                else:
                    shutil.copy2(source, destination)
            exit_code, receipt, stderr = run_case(
                mode, radar, args.build, args.base_snapshot
            )
            if exit_code == 0:
                raise AssertionError(f"{mode} unexpectedly succeeded")
            if receipt and receipt.get("accepted"):
                raise AssertionError(f"{mode} was accepted")
            cases.append(
                {
                    "name": mode,
                    "exit": exit_code,
                    "receipt": receipt,
                    "stderr": stderr,
                }
            )

        for mode in ("short_gate_count", "short_final_gate_count"):
            radar = work / mode
            radar.mkdir()
            for source in sorted(args.radar_root.glob("*_elev??")):
                destination = radar / source.name
                if mode == "short_gate_count" or source.name.endswith("elev09"):
                    clone_without_or_with_wrong_var(source, destination, mode)
                else:
                    shutil.copy2(source, destination)
            exit_code, receipt, stderr = run_case(
                mode, radar, args.build, args.base_snapshot
            )
            if exit_code != 0 or not receipt or not receipt.get("accepted"):
                raise AssertionError(
                    f"{mode} short-count volume failed: exit={exit_code} {stderr}"
                )
            output = (
                Path(receipt["evidence"])
                / "final_lapsprd/v04/262281300.v04"
            )
            summary = check_output(output)
            cases.append(
                {
                    "name": mode,
                    "exit": exit_code,
                    "receipt": receipt,
                    "stderr": stderr,
                    "content": summary,
                    "contract": "short metadata counts mask padded normalized bins",
                }
            )

        first_gate = work / "geometry_first_gate"
        shutil.copytree(args.radar_root, first_gate)
        set_geometry(first_gate, first_gate_m=200.0, spacing_m=None)
        exit_code, receipt, stderr = run_case(
            "geometry_first_gate", first_gate, args.build, args.base_snapshot
        )
        if exit_code != 0 or not receipt or not receipt.get("accepted"):
            raise AssertionError(
                f"metadata first-gate remap failed: exit={exit_code} {stderr}"
            )
        cases.append(
            {
                "name": "geometry_first_gate",
                "exit": exit_code,
                "receipt": receipt,
                "stderr": stderr,
                "contract": "metadata first gate is bound into regenerated LUTs",
            }
        )

        spacing = work / "geometry_unsupported_spacing"
        shutil.copytree(args.radar_root, spacing)
        set_geometry(spacing, first_gate_m=None, spacing_m=300.0)
        exit_code, receipt, stderr = run_case(
            "geometry_unsupported_spacing", spacing, args.build, args.base_snapshot
        )
        if exit_code == 0 or (receipt and receipt.get("accepted")):
            raise AssertionError("unsupported spacing unexpectedly passed")
        cases.append(
            {
                "name": "geometry_unsupported_spacing",
                "exit": exit_code,
                "receipt": receipt,
                "stderr": stderr,
                "contract": "only configured 250 m spacing is accepted",
            }
        )

        mismatch = work / "geometry_mismatch"
        shutil.copytree(args.radar_root, mismatch)
        with netCDF4.Dataset(mismatch / "262281300_elev01", "r+") as dataset:
            dataset.variables["firstGateRangeV"][...] = 200.0
            dataset.variables["firstGateRangeZ"][...] = 200.0
        exit_code, receipt, stderr = run_case(
            "geometry_mismatch", mismatch, args.build, args.base_snapshot
        )
        if exit_code == 0 or (receipt and receipt.get("accepted")):
            raise AssertionError("mismatched tilt geometry unexpectedly passed")
        cases.append(
            {
                "name": "geometry_mismatch",
                "exit": exit_code,
                "receipt": receipt,
                "stderr": stderr,
                "contract": "tilts must match the volume LUT geometry",
            }
        )

        missing = work / "missing_tilt"
        shutil.copytree(args.radar_root, missing)
        (missing / "262281300_elev05").unlink()
        try:
            validate_tilt_files(missing, "262281300", 9)
        except RuntimeError as error:
            cases.append({"name": "missing_tilt", "exit": 1, "error": str(error)})
        else:
            raise AssertionError("missing tilt unexpectedly passed preflight")

    args.output.write_text(json.dumps({"status": "PASS", "cases": cases}, indent=2) + "\n")
    print(f"RADAR_REMAP_NEGATIVE_PASS {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
