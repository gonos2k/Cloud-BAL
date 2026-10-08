#!/usr/bin/env python3
"""Audit the first unpaired KDM6 input against the staged WRF input."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from netCDF4 import Dataset

from native_kdm6_trace import read_dump

EXPECTED_SOURCE_SHA256 = "1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819"
EXPECTED_WRFINPUT_SHA256 = "aecc4885da1d612e57ec8c603b6c85df6a89e3c53cda5a4a302ec65d33866739"
EXPECTED_VALID_TIME = "2026-08-16_12:00:00"
PAIRS = (("rain", "QR", "NR", "QRAIN", "QNRAIN"),
         ("cloud", "QC", "NC", "QCLOUD", "QNCLOUD"),
         ("ice", "QI", "NI", "QICE", "QNICE"),
         ("graupel", "QG", "BG", "QGRAUP", "QIB"))
PR65_PBL_PATCH = Path(__file__).resolve().parents[1] / "docs/evidence/pr65_pbl_shared_nc_research.patch"
PR65_PBL_RUN = Path(__file__).resolve().parents[1] / "docs/evidence/pr65_pbl_shared_nc_postcapture_run_20261007.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state(mass: float, moment: float) -> str:
    if not (math.isfinite(mass) and math.isfinite(moment)):
        return "invalid_nonfinite"
    if mass < 0.0 or moment < 0.0:
        return "invalid_negative"
    if mass == 0.0 and moment == 0.0:
        return "absent"
    if mass > 0.0 and moment > 0.0:
        return "active"
    if mass > 0.0:
        return "mass_only"
    return "moment_only"


def first_unpaired(trace: dict) -> dict:
    fields = trace["fields"]
    bounds = trace["bounds"]
    for j_index in range(fields["QI"].shape[0]):
        for k_index in range(fields["QI"].shape[1]):
            for i_index in range(fields["QI"].shape[2]):
                for species, mass_name, moment_name, _, _ in PAIRS:
                    mass = float(fields[mass_name][j_index, k_index, i_index])
                    moment = float(fields[moment_name][j_index, k_index, i_index])
                    pair_state = state(mass, moment)
                    if pair_state not in ("absent", "active"):
                        return {
                            "species": species,
                            "mass_field": mass_name,
                            "moment_field": moment_name,
                            "state": pair_state,
                            "coordinate_ijk": {
                                "i": bounds["its"] + i_index,
                                "j": bounds["jts"] + j_index,
                                "k": bounds["kts"] + k_index,
                            },
                            "mass": mass,
                            "moment": moment,
                            "active_array_offset_jki": [j_index, k_index, i_index],
                        }
    return {"state": "no_unpaired_input"}


def wrf_valid_time(dataset: Dataset) -> str:
    if "Times" not in dataset.variables:
        raise ValueError("staged WRF input lacks Times")
    variable = dataset.variables["Times"]
    if "Time" not in variable.dimensions:
        raise ValueError("Times has no Time dimension")
    time_axis = variable.dimensions.index("Time")
    if variable.shape[time_axis] != 1:
        raise ValueError("expected one staged WRF input time")
    row = variable[tuple(0 if axis == time_axis else slice(None)
                         for axis in range(variable.ndim))]
    if getattr(row, "dtype", None) is not None and row.dtype.kind == "S":
        raw = b"".join(bytes(value) for value in row.reshape(-1))
        value = raw.decode("ascii").replace("\x00", "").strip()
    else:
        value = "".join(str(part) for part in row.reshape(-1)).replace("\x00", "").strip()
    return value


def _state_variable(dataset: Dataset, name: str):
    if name not in dataset.variables:
        raise ValueError(f"staged WRF input lacks {name}")
    variable = dataset.variables[name]
    required = {"Time", "bottom_top", "south_north", "west_east"}
    if len(variable.dimensions) != 4 or set(variable.dimensions) != required:
        raise ValueError(f"{name} dimensions do not identify WRF Time/bottom_top/south_north/west_east axes: {variable.dimensions}")
    return variable


def _selectors(variable, coordinate: dict, time_index: int = 0,
               vertical: tuple[int, int] | None = None) -> tuple:
    if any(coordinate[axis] < 1 for axis in ("i", "j", "k")):
        raise ValueError(f"WRF coordinates must be one-based positive indices: {coordinate}")
    one_based = {"bottom_top": coordinate["k"],
                 "south_north": coordinate["j"],
                 "west_east": coordinate["i"]}
    selectors = []
    for axis, length in zip(variable.dimensions, variable.shape, strict=True):
        if axis == "Time":
            index = time_index
        elif axis == "bottom_top" and vertical is not None:
            start, stop = vertical
            if start < 1 or stop < start:
                raise ValueError(f"invalid WRF vertical slice: {vertical}")
            index = slice(start - 1, stop)
        else:
            index = one_based[axis] - 1
        if isinstance(index, int) and not 0 <= index < length:
            raise ValueError(f"coordinate {coordinate} outside {axis} extent {length}")
        if isinstance(index, slice) and index.stop > length:
            raise ValueError(f"vertical slice {vertical} outside bottom_top extent {length}")
        selectors.append(index)
    return tuple(selectors)


def staged_values(path: Path, coordinate: dict, time_index: int = 0) -> dict:
    with Dataset(path) as dataset:
        result = {}
        for _, _, _, mass_name, moment_name in PAIRS:
            for name in (mass_name, moment_name):
                variable = _state_variable(dataset, name)
                index = _selectors(variable, coordinate, time_index)
                result[name] = {
                    "available": True,
                    "value": float(variable[index]),
                    "units": getattr(variable, "units", None),
                    "dimensions": list(variable.dimensions),
                }
        return result


def column_evidence(path: Path, trace: dict, coordinate: dict,
                    time_index: int = 0) -> dict:
    kts, kte = trace["bounds"]["kts"], trace["bounds"]["kte"]
    with Dataset(path) as dataset:
        qi_variable = _state_variable(dataset, "QICE")
        ni_variable = _state_variable(dataset, "QNICE")
        staged_qi = qi_variable[
            _selectors(qi_variable, coordinate, time_index, (kts, kte))]
        staged_ni = ni_variable[
            _selectors(ni_variable, coordinate, time_index, (kts, kte))]
    fields = trace["fields"]
    j_index = coordinate["j"] - trace["bounds"]["jts"]
    i_index = coordinate["i"] - trace["bounds"]["its"]
    trace_qi = fields["QI"][j_index, :, i_index]
    trace_ni = fields["NI"][j_index, :, i_index]
    expected_levels = kte - kts + 1
    if len(staged_qi) != expected_levels or len(staged_ni) != expected_levels:
        raise ValueError("staged WRF vertical slice does not match active trace kts:kte")
    if len(trace_qi) != expected_levels or len(trace_ni) != expected_levels:
        raise ValueError("native trace fields are not cropped to active kts:kte")
    levels = []
    for level, (qice, qnice, qi, ni) in enumerate(
            zip(staged_qi, staged_ni, trace_qi, trace_ni, strict=True),
            start=kts):
        levels.append({"k": level, "staged_QICE": float(qice),
                       "staged_QNICE": float(qnice), "trace_QI": float(qi),
                       "trace_NI": float(ni), "trace_pair_state": state(float(qi), float(ni))})
    return {
        "levels": levels,
        "active_k_bounds": {"kts": kts, "kte": kte},
        "staged_active_levels": [row["k"] for row in levels
                                 if row["staged_QICE"] > 0.0 and row["staged_QNICE"] > 0.0],
        "trace_mass_only_levels": [row["k"] for row in levels
                                   if row["trace_pair_state"] == "mass_only"],
        "interpretation": "The column pattern is consistent with QI transport from paired ice aloft without matched QNI, but the stored artifacts do not capture the producer immediately before this KDM6 call.",
    }


def audit(trace_path: Path, input_path: Path, source_path: Path) -> dict:
    source_hash = sha256(source_path)
    if source_hash != EXPECTED_SOURCE_SHA256:
        raise ValueError(f"frozen source SHA-256 mismatch: {source_hash}")
    input_hash = sha256(input_path)
    if input_hash != EXPECTED_WRFINPUT_SHA256:
        raise ValueError(f"staged WRF input SHA-256 mismatch: {input_hash}")
    with Dataset(input_path) as dataset:
        valid_time = wrf_valid_time(dataset)
    if valid_time != EXPECTED_VALID_TIME:
        raise ValueError(f"staged WRF input time mismatch: {valid_time}")
    trace = read_dump(trace_path)
    first = first_unpaired(trace)
    source_values = (staged_values(input_path, first["coordinate_ijk"])
                     if "coordinate_ijk" in first else {})
    column = (column_evidence(input_path, trace, first["coordinate_ijk"])
              if first.get("species") == "ice" else {})
    pbl_research = {
        "patch_path": str(PR65_PBL_PATCH), "patch_sha256": sha256(PR65_PBL_PATCH),
        "postcapture_receipt_path": str(PR65_PBL_RUN), "postcapture_receipt_sha256": sha256(PR65_PBL_RUN),
        "source_contract": "The PR65 Shinhong path carries QI in its shared vertical operator; its research NC extension carries NC through a fourth channel. The source path does not include QNI in that operator.",
        "runtime_scope": "PR65 selected-call capture validates NC accumulation, not QI/QNI tendencies at the PR73 first-mismatch cell.",
        "carrier_limit": "Existing PR65 evidence states DEL is interface-pressure thickness and not authenticated as native hybrid dry carrier.",
    }
    return {
        "schema": "pr73_native_first_unpaired_input_v1",
        "classification": "source-order diagnosis from preserved first-call trace and staged input; no repair authority",
        "case": {"valid_time_utc": "2026-08-16T12:00:00Z",
                 "wrfinput_Times": valid_time,
                 "wrfinput_sha256": input_hash,
                 "expected_wrfinput_sha256": EXPECTED_WRFINPUT_SHA256,
                 "source_input_hash_binding": "verified exact SHA-256 of retained staged 12 UTC WRF input"},
        "trace": {"path": str(trace_path), "sha256": trace["sha256"],
                  "stage": trace["stage"], "timestep": trace["itimestep"],
                  "bounds": trace["bounds"]},
        "staged_wrf_input": {"path": str(input_path), "sha256": input_hash,
                              "valid_time_utc": "2026-08-16T12:00:00Z"},
        "frozen_kdm6_source": {"path": str(source_path), "sha256": source_hash,
                               "validation_loop_order": "j ascending, then k ascending, then i ascending; species order rain, cloud, ice, graupel"},
        "first_unpaired_pair": first,
        "same_coordinate_staged_fields": source_values,
        "same_column_vertical_evidence": column,
        "pbl_source_context": pbl_research,
        "upstream_origin": {
            "finding": "At the first mismatch coordinate the staged WRF input has QICE=0 and QNICE=0; the first KDM6 input has positive QI and zero NI. The vertical column has paired ice aloft and trace-only mass-only ice below.",
            "producer_status": "PBL QI transport without QNI is a source-consistent candidate, but the exact producer is OPEN without a source-bound pre/post PBL or RK trace at this column.",
            "authority_limit": "This comparison does not establish a repair rule or authorize a mass floor, deletion, or graupel density change.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--wrfinput", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.trace, args.wrfinput, args.source)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PR73_FIRST_UNPAIRED {result['first_unpaired_pair']}")
    print(args.output)


if __name__ == "__main__":
    main()
