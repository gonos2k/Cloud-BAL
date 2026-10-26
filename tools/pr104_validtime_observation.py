#!/usr/bin/env python3
"""Compare explicit-time LSO observations with exact WRF history records."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np


REPO = Path(__file__).resolve().parents[1]
PR103_PATH = REPO / "tools/pr103_surface_temperature_observation.py"
PR103_SPEC = importlib.util.spec_from_file_location("pr103_surface_temperature_observation", PR103_PATH)
PR103 = importlib.util.module_from_spec(PR103_SPEC)
sys.modules[PR103_SPEC.name] = PR103
PR103_SPEC.loader.exec_module(PR103)

ARMS = {"H", "A", "N"}


def parse_valid_time(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError("valid time must be an explicit UTC timestamp ending in Z")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("valid time must use YYYY-MM-DDTHH:MM:SSZ") from exc
    if parsed.second != 0:
        raise ValueError("LSO report times have minute precision; valid time seconds must be 00")
    return parsed


def observation_time(path: Path) -> datetime:
    with path.open("r", encoding="ascii") as stream:
        header = stream.readline().split()
    if len(header) < 2:
        raise ValueError(f"malformed LSO header in {path}")
    for date_format in ("%d-%b-%Y %H:%M:%S.%f", "%d-%b-%Y %H:%M:%S"):
        try:
            return datetime.strptime(" ".join(header[:2]), date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise ValueError(f"invalid LSO header timestamp in {path}: {' '.join(header[:2])}")


def validate_observation_values(observations: list[dict]) -> None:
    fields = ("lat", "lon", "elev_m", "temperature_f", "temperature_expected_accuracy_f")
    for index, observation in enumerate(observations):
        for field in fields:
            try:
                finite = math.isfinite(float(observation[field]))
            except (KeyError, TypeError, ValueError):
                finite = False
            if not finite:
                raise ValueError(f"LSO record {index + 1} has nonfinite or invalid {field}")


def load_histories(history_paths: dict[str, Path], valid_time: datetime,
                   observations: list[dict], observation_path: Path) -> dict:
    if set(history_paths) != ARMS:
        raise ValueError(f"history arms must be exactly {sorted(ARMS)}")
    expected_date = valid_time.date()
    header_time = observation_time(observation_path)
    if header_time != valid_time:
        raise ValueError(f"LSO header timestamp {header_time:%Y-%m-%dT%H:%M:%SZ} does not match valid time {valid_time:%Y-%m-%dT%H:%M:%SZ}")
    validate_observation_values(observations)

    arm_rows = {}
    arm_metrics = {}
    base_attrs = base_lat = base_lon = None
    geometry_audit = None
    expected_hhmm = valid_time.hour * 100 + valid_time.minute
    for arm in ("H", "A", "N"):
        path = history_paths[arm]
        record_metadata = {}
        attrs, field, lat_grid, lon_grid = PR103.model_metadata(
            path, valid_time.strftime("%Y-%m-%dT%H:%M:%SZ"), record_metadata=record_metadata)
        if base_attrs is None:
            base_attrs, base_lat, base_lon = attrs, lat_grid, lon_grid
            projection = {
                "lat1": attrs["lat1"], "lon1": attrs["lon1"], "stdlon": attrs["STAND_LON"],
                "truelat1": attrs["TRUELAT1"], "truelat2": attrs["TRUELAT2"],
                "dx": attrs["DX"], "dy": attrs["DY"],
            }
            geometry_audit = PR103.grid_mapping_residuals(lat_grid, lon_grid, projection)
        elif attrs != base_attrs or not (np.array_equal(lat_grid, base_lat) and np.array_equal(lon_grid, base_lon)):
            raise ValueError(f"{arm} projection or mass grid differs from H")
        rows, metrics = PR103.compare(observations, field, projection, expected_hhmm)
        arm_rows[arm] = rows
        arm_metrics[arm] = {
            "history_path": str(path), "history_sha256": sha256(path),
            "history_record_index": record_metadata["index"],
            "history_record_time": record_metadata["stored_time"],
            "valid_time_utc": valid_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "field": "T2", "field_units": "K", "field_shape_yx": list(field.shape),
            "field_min_k": float(field.min()), "field_max_k": float(field.max()),
            "metrics": metrics,
        }

    return {
        "arms": arm_metrics,
        "matched_station_records": arm_rows["H"],
        "matched_station_records_by_arm": arm_rows,
        "geometry_audit": {"anchor_source": "XLAT[0,0]/XLONG[0,0] from exact history record",
                            "mass_grid_shape_yx": list(base_lat.shape), **geometry_audit},
        "operator_pair_differences": {
            "N_minus_A": paired_operator_difference(arm_rows["N"], arm_rows["A"], "H(XN) - H(XA)"),
            "A_minus_H": paired_operator_difference(arm_rows["A"], arm_rows["H"], "H(XA) - H(XH)"),
            "N_minus_H": paired_operator_difference(arm_rows["N"], arm_rows["H"], "H(XN) - H(XH)"),
        },
    }


def paired_operator_difference(x_rows: list[dict], y_rows: list[dict], definition: str) -> dict:
    def index(rows: list[dict]) -> dict[tuple[str, str, str, int], float]:
        result = {}
        for row in rows:
            key = (row["station_id"], row["wmo_id"], row["provider"], row["time_hhmm"])
            if key in result:
                raise ValueError(f"duplicate matched station key: {key}")
            result[key] = row["model_t2_c"]
        return result

    x_values, y_values = index(x_rows), index(y_rows)
    if x_values.keys() != y_values.keys():
        missing_from_x = len(y_values.keys() - x_values.keys())
        missing_from_y = len(x_values.keys() - y_values.keys())
        raise ValueError(f"operator pair has different station coverage: missing_from_x={missing_from_x}, missing_from_y={missing_from_y}")
    keys = sorted(x_values)
    if not keys:
        raise ValueError("operator pair has no matched station coverage")
    delta = np.asarray([x_values[key] - y_values[key] for key in keys], dtype=float)
    return {
        "definition": f"{definition}, station-interpolated T2 in degC",
        "paired_station_count": int(delta.size),
        "nonzero_signal": bool(np.any(delta != 0.0)),
        "rms_delta_c": float(np.sqrt(np.square(delta).mean())) if delta.size else None,
        "max_abs_delta_c": float(np.abs(delta).max()) if delta.size else None,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--valid-time", required=True, help="exact UTC timestamp, YYYY-MM-DDTHH:MM:SSZ")
    parser.add_argument("--observation", type=Path, required=True, help="LSO file for the requested UTC date")
    parser.add_argument("--history", action="append", required=True, metavar="ARM=PATH",
                        help="explicit WRF history file; provide H, A, and N once each")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    valid_time = parse_valid_time(args.valid_time)
    history_paths = {}
    for item in args.history:
        if "=" not in item:
            raise SystemExit("--history must use ARM=PATH")
        arm, path = item.split("=", 1)
        if arm not in ARMS or arm in history_paths or not path:
            raise SystemExit("--history requires one unique H, A, and N ARM=PATH entry")
        history_paths[arm] = Path(path)
    inputs = {args.observation.resolve(), *(path.resolve() for path in history_paths.values()),
              PR103_PATH.resolve(), Path(__file__).resolve()}
    if args.output.resolve() in inputs:
        raise SystemExit("--output must not overwrite an observation, history, or source file")
    observations, lso_counts = PR103.read_lso(args.observation)
    try:
        result = load_histories(history_paths, valid_time, observations, args.observation)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    payload = {
        "schema": "pr104_explicit_valid_time_observation_v1",
        "scope": "same-valid-time observation comparison; descriptive residuals only",
        "valid_time_utc": valid_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observation": {"path": str(args.observation), "sha256": sha256(args.observation),
                        "units": "degF", "header_time_utc": valid_time.strftime("%Y-%m-%dT%H:%M:%SZ")},
        "observation_file_counts": lso_counts,
        "operator": "PR103 source-mapped Lambert mass-grid interpolation and legacy gdtost",
        **result,
        "limits": ["Only records reporting at the requested UTC minute are matched.",
                   "No nearest-time selection or zero filling is performed.",
                   "Residuals do not establish independent forecast skill; observation QC and uncertainty are not modeled."],
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
