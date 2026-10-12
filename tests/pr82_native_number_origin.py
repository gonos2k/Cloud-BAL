#!/usr/bin/env python3
"""Bind the first native NC rejection to input, initial readback, and KDM6 state."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
import sys
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from native_kdm6_trace import read_dump


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_new_json(path: Path, value: dict) -> None:
    output = Path(os.path.abspath(path))
    for component in reversed((output, *output.parents)):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"output path contains a symlink: {component}")
        if component == output:
            raise FileExistsError(f"refusing to overwrite existing output: {output}")
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"output parent is not a directory: {component}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def float_bits(value: float) -> str:
    return f"{struct.unpack('>I', struct.pack('>f', value))[0]:08X}"


def netcdf_cell(path: Path, i: int, j: int, k: int) -> dict:
    with Dataset(path) as dataset:
        result = {"path": str(path), "sha256": sha256(path),
                  "shape": {name: len(dataset.dimensions[name])
                            for name in ("Time", "bottom_top", "south_north", "west_east")}}
        index = (0, k - 1, j - 1, i - 1)
        for name in ("QNCLOUD", "QCLOUD", "QVAPOR"):
            value = np.float32(dataset[name][index])
            result[name] = {"value": float(value), "bits": f"{value.view(np.uint32).item():08X}",
                            "units": getattr(dataset[name], "units", "")}
        result["netcdf_indices_zero_based_time_k_j_i"] = list(index)
        return result


def trace_cell(path: Path, i: int, j: int, k: int) -> dict:
    dump = read_dump(path)
    bounds = dump["bounds"]
    index = (j - bounds["jts"], k - bounds["kms"], i - bounds["its"])
    fields = {}
    for name in ("NC", "QC", "DEN", "Q"):
        value = np.float32(dump["fields"][name][index])
        fields[name] = {"value": float(value), "bits": f"{value.view(np.uint32).item():08X}"}
    denominator = np.float32(np.float32(1.0) + np.float32(fields["Q"]["value"]))
    dry_density = np.float32(np.float32(fields["DEN"]["value"]) / denominator)
    fields["dry_density"] = {"value": float(dry_density),
                             "bits": f"{dry_density.view(np.uint32).item():08X}"}
    return {"path": str(path), "sha256": dump["sha256"], "stage": dump["stage"],
            "timestep": dump["itimestep"], "bounds": bounds,
            "local_active_indices_zero_based_j_k_i": list(index), "fields": fields}


def rejection_row(path: Path) -> dict:
    rows = [line.strip().split(",") for line in path.read_text().splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) != 14 or rows[0][0] != "NUMBER_BASIS_REJECT":
        raise ValueError("expected exactly one shared rejection record")
    labels = ("record", "species", "stage", "i", "call_lat_index", "k",
              "publicinputbits", "dry_density_bits", "product_bits",
              "mxcsr_before", "mxcsr_after", "thread_before", "thread_after", "errorclass")
    row = dict(zip(labels, rows[0], strict=True))
    row["sha256"] = sha256(path)
    return row


def build(input_path: Path, initial_path: Path, pre_path: Path, reject_path: Path) -> dict:
    row = rejection_row(reject_path)
    if (row["species"], row["stage"], row["errorclass"]) != ("NC", "INPUT", "POSITIVE_TO_ZERO"):
        raise ValueError("trace is not the expected first NC input rejection")
    i, j, k = int(row["i"]), int(row["call_lat_index"]), int(row["k"])
    trace = trace_cell(pre_path, i, j, k)
    input_cell = netcdf_cell(input_path, i, j, k)
    initial_cell = netcdf_cell(initial_path, i, j, k)
    if row["publicinputbits"] != trace["fields"]["NC"]["bits"]:
        raise ValueError("rejection public input bits differ from KDM6 pre-call NC")
    if row["dry_density_bits"] != trace["fields"]["dry_density"]["bits"]:
        raise ValueError("rejection density differs from KDM6 pre-call DEN/(1+Q)")
    minimum_subnormal = float(np.nextafter(np.float32(0.0), np.float32(1.0)))
    product = minimum_subnormal * trace["fields"]["dry_density"]["value"]
    return {"schema": "pr82_native_number_origin_v1",
            "scope": "read-only single-cell origin trace; no physics value changed",
            "coordinates_fortran_global_i_j_k": [i, j, k],
            "mapping": {"netcdf": "(Time=0, bottom_top=k-1, south_north=j-1, west_east=i-1)",
                        "kdm6_active_local": "(j-jts, k-kms, i-its)"},
            "wrfinput": input_cell, "initial_wrfout_readback": initial_cell,
            "kdm6_first_call_pre": trace, "rejection": row,
            "checks": {"input_qncloud_zero": input_cell["QNCLOUD"]["bits"] == "00000000",
                       "input_qcloud_zero": input_cell["QCLOUD"]["bits"] == "00000000",
                       "initial_qncloud_zero": initial_cell["QNCLOUD"]["bits"] == "00000000",
                       "initial_qcloud_zero": initial_cell["QCLOUD"]["bits"] == "00000000",
                       "first_call_nc_is_smallest_positive_subnormal": trace["fields"]["NC"]["bits"] == "00000001",
                       "first_call_qc_zero": trace["fields"]["QC"]["bits"] == "00000000",
                       "dry_density_reproduces_rejection": row["dry_density_bits"] == trace["fields"]["dry_density"]["bits"],
                       "minimum_subnormal_product_below_half_min_subnormal": product < minimum_subnormal / 2.0,
                       "origin_interval": "after initial wrfout readback and before first KDM6 call; exact host RK/PBL boundary not identified"}}


def main() -> int:
    input_path, initial_path, pre_path, reject_path, output_path = map(Path, sys.argv[1:])
    opened = {str(path): sha256(path) for path in (input_path, initial_path, pre_path, reject_path)}
    result = build(input_path, initial_path, pre_path, reject_path)
    after = {str(path): sha256(path) for path in (input_path, initial_path, pre_path, reject_path)}
    if opened != after:
        raise RuntimeError("an opened native input or trace changed while origin receipt was built")
    result["opened_inputs_sha256_before"] = opened
    result["opened_inputs_sha256_after"] = after
    write_new_json(output_path, result)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
