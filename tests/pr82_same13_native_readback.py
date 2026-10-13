#!/usr/bin/env python3
"""Independent field-level readback for the same13 native initial wrfout."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import netCDF4
import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def time_string(ds: netCDF4.Dataset) -> str:
    return b"".join(ds.variables["Times"][0].tolist()).decode("ascii")


def unmasked_values(variable: netCDF4.Variable) -> np.ndarray:
    raw = variable[:]
    if np.any(np.ma.getmaskarray(raw)):
        raise ValueError(f"{variable.name}: masked values are forbidden")
    values = np.asarray(raw)
    for attribute in ("_FillValue", "missing_value"):
        if not hasattr(variable, attribute):
            continue
        fill = np.asarray(getattr(variable, attribute))
        if np.any(values == fill):
            raise ValueError(f"{variable.name}: explicit {attribute} value is forbidden")
    if not np.isfinite(values).all():
        raise ValueError(f"{variable.name}: non-finite field")
    return values


def bind_run_receipt(run: dict[str, object], input_path: Path,
                     output_path: Path) -> dict[str, str]:
    """Bind the readback pair to exact candidate and initial-output bytes."""
    expected_input = run.get("candidate_wrfinput_sha256")
    expected_output = run.get("initial_wrfo_sha256")
    actual_input, actual_output = sha256(input_path), sha256(output_path)
    if not isinstance(expected_input, str) or actual_input != expected_input:
        raise ValueError("run receipt candidate wrfinput hash does not match readback input")
    if not isinstance(expected_output, str) or actual_output != expected_output:
        raise ValueError("run receipt initial wrfout hash does not match readback output")
    return {"input_sha256": actual_input, "initial_wrfo_sha256": actual_output}


def field_record(variable: netCDF4.Variable, expected_dims: tuple[str, ...], units: str | None,
                 expected_units: str | None) -> dict[str, object]:
    if variable.dimensions != expected_dims:
        raise ValueError(f"{variable.name}: dimensions {variable.dimensions} != {expected_dims}")
    actual_units = getattr(variable, "units", None)
    if expected_units is not None and actual_units != expected_units:
        raise ValueError(f"{variable.name}: units {actual_units!r} != {expected_units!r}")
    if units is not None and actual_units != units:
        raise ValueError(f"{variable.name}: input/output unit mismatch")
    values = np.asarray(unmasked_values(variable), dtype=np.float32)
    return {"dimensions": list(variable.dimensions), "shape": list(values.shape),
            "units": actual_units,
            "min": float(values.min()), "max": float(values.max()),
            "positive_cells": int(np.count_nonzero(values > 0)),
            "zero_cells": int(np.count_nonzero(values == 0)),
            "sha256_f32_le": hashlib.sha256(values.astype("<f4", copy=False).tobytes()).hexdigest()}


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit("usage: pr82_same13_native_readback.py RUN_RECEIPT WRFINPUT WRFO OUTPUT_JSON")
    receipt_path, input_path, output_path, report_path = map(Path, sys.argv[1:])
    if report_path.exists() or report_path.is_symlink():
        raise SystemExit(f"refusing to overwrite readback output: {report_path}")
    run = json.loads(receipt_path.read_text())
    receipt_sha256 = sha256(receipt_path)
    bound_hashes = bind_run_receipt(run, input_path, output_path)
    if run.get("initialization_gate") != "PASS_SCOPED_INITIALIZATION_READBACK":
        raise SystemExit("native isolated initialization receipt is not passing")
    if run.get("run_isolation", {}).get("input_integrity") != "PASS" or \
            run.get("run_isolation", {}).get("output_isolation") != "PASS":
        raise SystemExit("native runner isolation receipt is not passing")

    mass_dims = ("Time", "bottom_top", "south_north", "west_east")
    surface_dims = ("Time", "south_north", "west_east")
    stag_dims = ("Time", "bottom_top_stag", "south_north", "west_east")
    units = {"QVAPOR": "kg kg-1", "QCLOUD": "kg kg-1", "QICE": "kg kg-1",
             "QRAIN": "kg kg-1", "QSNOW": "kg kg-1", "QGRAUP": "kg kg-1",
             "PSFC": "Pa", "P": "Pa", "PB": "Pa", "T": "K", "PH": "m2 s-2",
             "PHB": "m2 s-2", "U": "m s-1", "V": "m s-1", "W": "m s-1",
             "MU": "Pa", "MUB": "Pa"}
    expected_dims = {
        **{name: mass_dims for name in ("QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP", "P", "PB", "T")},
        "PSFC": surface_dims, "MU": surface_dims, "MUB": surface_dims,
        "PH": stag_dims, "PHB": stag_dims,
        "U": ("Time", "bottom_top", "south_north", "west_east_stag"),
        "V": ("Time", "bottom_top", "south_north_stag", "west_east"),
        "W": stag_dims,
    }
    with netCDF4.Dataset(input_path) as source, netCDF4.Dataset(output_path) as initial:
        source_time, output_time = time_string(source), time_string(initial)
        if source_time != "2026-08-16_13:00:00" or output_time != source_time:
            raise ValueError(f"wrong 13 UTC input/output time: {source_time} / {output_time}")
        fields: dict[str, object] = {}
        names = list(expected_dims)
        number_names = sorted(name for name in source.variables if name.startswith("QN"))
        for name in number_names:
            expected_dims[name] = mass_dims
        for name, dims in expected_dims.items():
            if name not in source.variables or name not in initial.variables:
                raise ValueError(f"required native field missing from input or initial output: {name}")
            source_var, output_var = source.variables[name], initial.variables[name]
            expected_units = units.get(name)
            if name.startswith("QN"):
                if not getattr(source_var, "units", "").strip():
                    raise ValueError(f"{name}: missing source number-moment units")
                expected_units = None
            input_state = field_record(source_var, dims, None, expected_units)
            output_state = field_record(output_var, dims, input_state["units"], expected_units)
            a = unmasked_values(source_var)
            b = unmasked_values(output_var)
            if a.shape != b.shape:
                raise ValueError(f"{name}: source/output shape mismatch: {a.shape} != {b.shape}")
            diff = np.asarray(b, dtype=np.float64) - np.asarray(a, dtype=np.float64)
            fields[name] = {
                "input": input_state, "initial_wrfo": output_state,
                "exact_equal": bool(np.array_equal(a, b)),
                "changed_cells": int(np.count_nonzero(a != b)),
                "max_abs_difference": float(np.abs(diff).max(initial=0.0)),
            }

        physical_pressure = np.asarray(initial.variables["P"][:], dtype=np.float64) + \
            np.asarray(initial.variables["PB"][:], dtype=np.float64)
        source_pressure = np.asarray(source.variables["P"][:], dtype=np.float64) + \
            np.asarray(source.variables["PB"][:], dtype=np.float64)
        pressure_delta = physical_pressure - source_pressure
        initial_geopotential = np.asarray(initial.variables["PH"][:], dtype=np.float64) + \
            np.asarray(initial.variables["PHB"][:], dtype=np.float64)
        source_geopotential = np.asarray(source.variables["PH"][:], dtype=np.float64) + \
            np.asarray(source.variables["PHB"][:], dtype=np.float64)
        geopotential_delta = initial_geopotential - source_geopotential
        if not np.isfinite(physical_pressure).all() or np.any(physical_pressure <= 0):
            raise ValueError("initial output physical P+PB must be positive and finite")
        if getattr(initial.variables["T"], "description", None) != \
                "perturbation potential temperature theta-t0":
            raise ValueError("initial output T field lacks expected perturbation-theta semantics")

        hydromass = ("QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP")
        if not all(fields[name]["input"]["positive_cells"] > 0 for name in hydromass):
            raise ValueError("not every hydromass field has positive cells in the 13 UTC input")
        if not all(fields[name]["input"]["positive_cells"] == 0 for name in number_names):
            raise ValueError("expected retained real.exe number-moment fields to be zero for this diagnostic")

        report = {
            "schema": "pr82_same13_native_initial_field_readback_v1",
            "status": "PASS_SCOPED_INITIALIZATION_READBACK",
            "native_first_step_gate": run.get("first_step_gate"),
            "native_first_step_rejection": run.get("first_step_rejection"),
            "science_authority": "NONE",
            "operational_authority": "NONE",
            "valid_time": output_time,
            "run_receipt_sha256": receipt_sha256,
            **bound_hashes,
            "native_wrftitle": getattr(initial, "TITLE", None),
            "physics_mp_physics": int(getattr(initial, "MP_PHYSICS")),
            "fields": fields,
            "physical_pressure_p_plus_pb_pa": {
                "shape": list(physical_pressure.shape), "min": float(physical_pressure.min()),
                "max": float(physical_pressure.max()),
                "changed_cells_from_real_input": int(np.count_nonzero(pressure_delta)),
                "max_absolute_change_from_real_input_pa": float(np.abs(pressure_delta).max(initial=0.0)),
            },
            "geopotential_ph_plus_phb_m2_s2": {
                "changed_cells_from_real_input": int(np.count_nonzero(geopotential_delta)),
                "max_absolute_change_from_real_input": float(np.abs(geopotential_delta).max(initial=0.0)),
            },
            "T_semantics": "perturbation potential temperature theta minus base theta",
            "number_basis_interpretation": "real.exe input QN fields are zero; positive hydromass is not microphysics-validity evidence",
            "first_native_species_observer": run.get("first_native_species_observer"),
            "run_isolation": {
                "input_integrity": run["run_isolation"]["input_integrity"],
                "output_isolation": run["run_isolation"]["output_isolation"],
                "native_trace_output_integrity": run.get("native_trace_output_integrity"),
            },
        }
    if (sha256(receipt_path) != receipt_sha256 or
            sha256(input_path) != bound_hashes["input_sha256"] or
            sha256(output_path) != bound_hashes["initial_wrfo_sha256"]):
        raise ValueError("run receipt or readback input/output changed during inspection")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "time": output_time,
                      "first_step_gate": report["native_first_step_gate"],
                      "report": str(report_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
