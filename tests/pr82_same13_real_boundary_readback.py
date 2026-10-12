#!/usr/bin/env python3
"""Validate exact-time met_em inputs and actual same13 real.exe boundary output."""
import argparse
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def timestamp(dataset):
    return b"".join(dataset.variables["Times"][0].tolist()).decode().strip()


def metgrid_contract(paths):
    output = []
    required_units = {"TT": "K", "GHT": "m", "UU": "m s-1", "VV": "m s-1",
                      "RH": "%", "PSFC": "Pa", "PMSL": "Pa", "SKINTEMP": "K"}
    for path, expected_time in zip(paths, ("13:00:00", "14:00:00", "15:00:00")):
        with netCDF4.Dataset(path) as dataset:
            expected = f"2026-08-16_{expected_time}"
            actual = timestamp(dataset)
            if actual != expected:
                raise SystemExit(f"{path}: timestamp {actual} != {expected}")
            attrs = {name: getattr(dataset, name) for name in
                     ("WEST-EAST_GRID_DIMENSION", "SOUTH-NORTH_GRID_DIMENSION", "DX", "DY")}
            if attrs != {"WEST-EAST_GRID_DIMENSION": 235, "SOUTH-NORTH_GRID_DIMENSION": 283,
                         "DX": 5000.0, "DY": 5000.0}:
                raise SystemExit(f"{path}: source grid contract mismatch: {attrs}")
            if len(dataset.dimensions["num_metgrid_levels"]) != 21:
                raise SystemExit(f"{path}: expected 21 metgrid levels")
            for name, units in required_units.items():
                if name not in dataset.variables:
                    raise SystemExit(f"{path}: missing {name}")
                variable = dataset.variables[name]
                if getattr(variable, "units", "") != units:
                    raise SystemExit(f"{path}: {name} units mismatch")
                if not np.isfinite(np.asarray(variable[:])).all():
                    raise SystemExit(f"{path}: non-finite {name}")
            if "PRES" not in dataset.variables or dataset.variables["PRES"].shape != (1, 21, 282, 234):
                raise SystemExit(f"{path}: pressure coordinate shape mismatch")
            has_direct_qv = "QV" in dataset.variables
            if expected_time == "13:00:00" and not has_direct_qv:
                raise SystemExit("candidate 13 UTC must supply direct QV")
            output.append({"path": str(path), "sha256": sha256(path), "time": actual,
                           "grid": [235, 283], "spacing_m": [5000.0, 5000.0],
                           "metgrid_levels": 21, "direct_QV_present": has_direct_qv,
                           "Qv_units": getattr(dataset.variables["QV"], "units", None)
                           if has_direct_qv else None})
    return output


parser = argparse.ArgumentParser()
parser.add_argument("--inputs", nargs=3, type=Path)
parser.add_argument("--namelist", type=Path)
parser.add_argument("--validate-inputs-only", type=Path)
parser.add_argument("--verify-output", type=Path)
parser.add_argument("artifacts", nargs="*", type=Path)
args = parser.parse_args()

if args.validate_inputs_only:
    if not args.inputs or not args.namelist:
        parser.error("input validation needs three met_em files and namelist")
    receipt = args.validate_inputs_only
    if receipt.exists() or receipt.is_symlink():
        raise SystemExit("input contract receipt exists")
    text = args.namelist.read_text()
    for snippet in ("start_hour                          = 13,", "end_hour                            = 15,",
                    "interval_seconds                    = 3600,",
                    "use_sh_qv                           = .true.,",
                    "sfcp_to_sfcp                        = .true.,"):
        if snippet not in text:
            raise SystemExit(f"required real configuration missing: {snippet.strip()}")
    if "use_input_w" in text:
        raise SystemExit("unexpected use_input_w namelist override")
    evidence = {"status": "PASS_SCOPED_SAME13_BOUNDARY_INPUT_CONTRACT",
                "namelist_sha256": sha256(args.namelist),
                "namelist_delta_from_single_time": {
                    "start_hour": [13, 13], "end_hour": [13, 15],
                    "interval_seconds": [10800, 3600]},
                "physics_and_direct_qv_options_preserved": True,
                "met_em_inputs": metgrid_contract(args.inputs),
                "time_authority": "retained same-time source products at 14/15, not retimed 12 UTC data"}
    receipt.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n")
    raise SystemExit(0)

if not args.verify_output or len(args.artifacts) != 3:
    parser.error("output verification expects input-contract.json wrfinput wrfbdy single-time-wrfinput")
contract, wrfinput_path, boundary_path, single_path = args.verify_output, *args.artifacts
if args.inputs or args.namelist:
    parser.error("output mode does not accept input validation arguments")
evidence = json.loads(contract.read_text())
if evidence.get("status") != "PASS_SCOPED_SAME13_BOUNDARY_INPUT_CONTRACT":
    raise SystemExit("input contract is not passing")
with netCDF4.Dataset(wrfinput_path) as wrf, netCDF4.Dataset(single_path) as single:
    actual_time = timestamp(wrf)
    if actual_time != "2026-08-16_13:00:00":
        raise SystemExit(f"wrfinput valid time changed: {actual_time}")
    required_start_state = ("QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP",
                            "PSFC", "P", "PB", "T", "PH", "PHB", "U", "V", "W", "MU", "MUB")
    n_moments = sorted(name for name in wrf.variables if name.startswith("QN"))
    compared = {}
    for name in (*required_start_state, *n_moments):
        if name not in wrf.variables or name not in single.variables:
            raise SystemExit(f"same-time state missing {name} from real.exe output or reference")
        current = np.asarray(wrf.variables[name][:])
        reference = np.asarray(single.variables[name][:])
        if (current.shape != reference.shape
                or wrf.variables[name].dimensions != single.variables[name].dimensions
                or getattr(wrf.variables[name], "units", None) != getattr(single.variables[name], "units", None)
                or not np.array_equal(current, reference)):
            raise SystemExit(f"multi-time real.exe changed candidate start-state {name}")
        if not np.isfinite(current).all():
            raise SystemExit(f"non-finite start-state field {name}")
        compared[name] = {"shape": list(current.shape),
                          "dimensions": list(wrf.variables[name].dimensions),
                          "units": getattr(wrf.variables[name], "units", None),
                          "exact_match_single_time": True,
                          "sha256_f32": hashlib.sha256(current.astype("<f4", copy=False).tobytes()).hexdigest()}
    pressure = np.asarray(wrf.variables["P"][:], dtype=np.float64) + \
        np.asarray(wrf.variables["PB"][:], dtype=np.float64)
    if np.any(pressure <= 0) or not np.isfinite(pressure).all():
        raise SystemExit("physical P+PB must be finite and positive")
    if wrf.variables["T"].getncattr("description") != "perturbation potential temperature theta-t0":
        raise SystemExit("WRF T field does not declare perturbation potential-temperature semantics")
with netCDF4.Dataset(boundary_path) as boundary:
    bdy_time = timestamp(boundary)
    if bdy_time != "2026-08-16_13:00:00":
        raise SystemExit(f"wrfbdy anchor time changed: {bdy_time}")
    if len(boundary.dimensions["bdy_width"]) != 5 or len(boundary.dimensions["bottom_top"]) != 39:
        raise SystemExit("wrfbdy grid/vertical contract mismatch")
    qv_boundary = [name for name in boundary.variables if name.startswith("QVAPOR_")]
    if not qv_boundary:
        raise SystemExit("use_sh_qv=.true. did not produce QVAPOR boundary fields")
    for name in qv_boundary:
        if not np.isfinite(np.asarray(boundary.variables[name][:])).all():
            raise SystemExit(f"non-finite boundary QV field {name}")
    boundary_fields = sorted(boundary.variables)
output = {"status": "PASS_SCOPED_SAME13_REAL_WRFINIT_BOUNDARY_READBACK",
          "time": actual_time,
          "wrfinput_sha256": sha256(wrfinput_path),
          "wrfbdy_sha256": sha256(boundary_path),
          "wrfinput_fields_exact_to_single_time_real": compared,
          "required_start_fields": list(required_start_state),
          "available_number_moment_fields": n_moments,
          "physical_pressure_p_plus_pb_pa": {
              "shape": list(pressure.shape), "min": float(pressure.min()), "max": float(pressure.max())},
          "T_semantics": "perturbation potential temperature theta minus base theta",
          "wrfbdy_anchor_time": bdy_time,
          "wrfbdy_fields": boundary_fields,
          "qvapor_boundary_fields": qv_boundary,
          "science_authority": "NONE"}
contract.with_name("boundary_readback.json").write_text(json.dumps(output, sort_keys=True, indent=2) + "\n")
