#!/usr/bin/env python3
"""Map first-call KDM6 output moment gaps to same-time reflectivity failures."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path

import netCDF4
import numpy as np

from native_kdm6_trace import read_dump
from native_kdm6_call_geometry import audit as audit_geometry
from pr65_pbl_domain_metrics import active_field, crop_slices, read_times


PAIRS = (("QCLOUD", "QNCLOUD"), ("QICE", "QNICE"),
         ("QRAIN", "QNRAIN"), ("QGRAUP", "QIB"))
EXPECTED_TIMES = ("2026-08-16_12:00:00", "2026-08-16_12:00:20")


def validate_call_headers(pre: dict, post: dict) -> None:
    if (pre["stage"] != 1 or post["stage"] != 2 or
            pre["itimestep"] != 1 or post["itimestep"] != 1 or
            pre["itimestep"] != post["itimestep"] or
            pre["bounds"] != post["bounds"] or pre["params"] != post["params"]):
        raise ValueError("KDM6 pre/post trace headers do not match the first call")


def validate_output_times(times: tuple[str, ...]) -> None:
    if times != EXPECTED_TIMES:
        raise ValueError(f"unexpected WRF output timestamps: {times}")


def validate_finite_pair(mass: np.ndarray, moment: np.ndarray, label: str) -> None:
    if not np.isfinite(mass).all() or not np.isfinite(moment).all():
        raise ValueError(f"{label} mass or moment contains nonfinite values")


def _receipt_bound_output(run: Path, output: Path, receipt_path: Path) -> str:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    run_root = run.resolve()
    if (Path(receipt.get("run_root", "")).resolve() != run_root or
            receipt.get("returncode") != 0 or receipt.get("input_integrity") != "PASS" or
            receipt.get("output_isolation") != "PASS"):
        raise ValueError("run receipt does not bind a successful isolated run root")
    try:
        relative = output.resolve().relative_to(run_root).as_posix()
    except ValueError as exc:
        raise ValueError("WRF output is outside the receipt run root") from exc
    matches = [row for row in receipt["outputs"] if row.get("path") == relative]
    try:
        file_stat = output.lstat()
    except FileNotFoundError as exc:
        raise ValueError("WRF output is missing") from exc
    if (len(matches) != 1 or not stat.S_ISREG(file_stat.st_mode) or output.is_symlink() or
            file_stat.st_nlink != 1 or matches[0].get("nlink") != 1):
        raise ValueError("WRF output is not a unique regular receipt-listed artifact")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    if digest != matches[0]["sha256"]:
        raise ValueError("WRF output hash differs from run receipt")
    return digest


def summarize(run: Path) -> dict:
    pre = read_dump(run / "kdm6_first_call_pre.raw")
    post = read_dump(run / "kdm6_first_call_post.raw")
    validate_call_headers(pre, post)
    geometry_path = run / "pr63_geometry.raw"
    receipt_path = run / "run-isolation-pr67.json"
    geometry_audit = audit_geometry(geometry_path, run / "kdm6_first_call_pre.raw",
                                    run / "kdm6_first_call_post.raw", receipt_path)
    slices = crop_slices(pre["bounds"])
    outputs = list(run.glob("wrfout_d01_*"))
    if len(outputs) != 1:
        raise ValueError("expected one WRF output file")
    output = outputs[0]
    output_hash = _receipt_bound_output(run, output, receipt_path)
    with netCDF4.Dataset(output) as dataset:
        times = read_times(dataset.variables["Times"])
        validate_output_times(times)
        time_index = 1
        reflectivity = active_field(dataset.variables["REFL_10CM"], time_index, slices)
        nonfinite_reflectivity = ~np.isfinite(reflectivity)
        rain = active_field(dataset.variables["QRAIN"], time_index, slices)
        rain_number = active_field(dataset.variables["QNRAIN"], time_index, slices)
        output_gaps = {}
        for mass_name, moment_name in PAIRS:
            mass = active_field(dataset.variables[mass_name], time_index, slices)
            moment = active_field(dataset.variables[moment_name], time_index, slices)
            validate_finite_pair(mass, moment, f"{mass_name}/{moment_name}")
            output_gaps[f"{mass_name}/{moment_name}"] = {
                "positive_mass_cells": int(np.count_nonzero(mass > 0)),
                "positive_mass_zero_moment_cells": int(np.count_nonzero((mass > 0) & (moment == 0))),
                "nonfinite_reflectivity_positive_mass_zero_moment_cells": int(
                    np.count_nonzero(nonfinite_reflectivity & (mass > 0) & (moment == 0)))
            }
    rain_nan_pairing = {
        "nonfinite_reflectivity_cells": int(np.count_nonzero(nonfinite_reflectivity)),
        "QR_positive_NR_zero": int(np.count_nonzero(nonfinite_reflectivity & (rain > 0) & (rain_number == 0))),
        "QR_positive_NR_positive": int(np.count_nonzero(nonfinite_reflectivity & (rain > 0) & (rain_number > 0))),
        "QR_nonpositive_NR_zero": int(np.count_nonzero(nonfinite_reflectivity & (rain <= 0) & (rain_number == 0))),
        "mask_sha256": hashlib.sha256(np.ascontiguousarray(nonfinite_reflectivity).tobytes()).hexdigest(),
    }
    raw_gaps = {}
    for mass, moment in (("QC", "NC"), ("QI", "NI"), ("QR", "NR"), ("QG", "BG")):
        mass_values, moment_values = post["fields"][mass], post["fields"][moment]
        validate_finite_pair(mass_values, moment_values, f"KDM6 {mass}/{moment}")
        raw_gaps[f"{mass}/{moment}"] = {
            "positive_mass_cells": int(np.count_nonzero(mass_values > 0)),
            "positive_mass_zero_moment_cells": int(np.count_nonzero((mass_values > 0) & (moment_values == 0))),
        }
    return {
        "wrfout_sha256": output_hash,
        "receipt_sha256": geometry_audit["receipt_sha256"],
        "executable_sha256": geometry_audit["executable_sha256"],
        "timestamp": times[time_index],
        "active_shape_kji": list(reflectivity.shape),
        "reflectivity_nonfinite": rain_nan_pairing,
        "same_time_output_positive_mass_zero_moment": output_gaps,
        "same_call_kdm6_post_positive_mass_zero_moment": raw_gaps,
        "scope": "one public KDM6 call active tile mapped to the WRF output at the second recorded time; co-occurrence does not establish cause",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = summarize(args.run)
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
