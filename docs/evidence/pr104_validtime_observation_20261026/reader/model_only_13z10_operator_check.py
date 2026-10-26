#!/usr/bin/env python3
"""Read-only H(XN)-H(XA) check at fixed 14Z LSO locations; does not use temperatures."""

import importlib.util
import json
from pathlib import Path
import sys

import numpy as np


REPO = Path(__file__).resolve().parents[4]
SOURCE = REPO / "tools/pr103_surface_temperature_observation.py"
SOURCE_SHA256 = "736ae3b5ec8f7e41dfd5543f00eb5b81c163a53e447e4c8de6dfcf5f182b62da"
LSO = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/00/lapsprd/lso/262281400.lso")
LSO_SHA256 = "5897d4ec8d4979a71369f68de95c68f7229ae76fa6104619d893b204b9ad6ec9"
HISTORIES = {
    "N": (Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr102_native_structure640_20261025/STRUCTURED640_RUN/run/wrfout_d01_2026-08-16_13:00:00"),
          "fd18da17a47abeb862ac088f4ea185d34583de65d88245737b124065aa52165a"),
    "A": (Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr103_amplitude20_capture_20261026/AMPLITUDE640_RUN/run/wrfout_d01_2026-08-16_13:00:00"),
          "67ec6197a5f1aed9e90f56c49d5af34e9f685167f7ac2427884b9bcdef8707a4"),
}


def load_pr103():
    spec = importlib.util.spec_from_file_location("pr103_surface_temperature_observation", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    pr103 = load_pr103()
    if pr103.sha256(SOURCE) != SOURCE_SHA256 or pr103.sha256(LSO) != LSO_SHA256:
        raise SystemExit("PR103 reader or 14Z LSO pin changed")
    if pr103.LSO_BADFLAG_F != -99.9:
        raise SystemExit("unexpected LSO temperature sentinel definition")
    observations, counts = pr103.read_lso(LSO)
    models, metadata, hashes, projection = {}, {}, {}, None
    for arm, (path, expected_hash) in HISTORIES.items():
        if pr103.sha256(path) != expected_hash:
            raise SystemExit(f"{arm} history pin changed: {path}")
        record = {}
        attrs, field, lat, lon = pr103.model_metadata(
            path, "2026-08-16T13:10:00Z", record_metadata=record)
        current_projection = {
            "lat1": attrs["lat1"], "lon1": attrs["lon1"],
            "stdlon": attrs["STAND_LON"], "truelat1": attrs["TRUELAT1"],
            "truelat2": attrs["TRUELAT2"], "dx": attrs["DX"], "dy": attrs["DY"],
        }
        if projection is None:
            projection = current_projection
            base_lat, base_lon = lat, lon
        elif (current_projection != projection or not np.array_equal(lat, base_lat) or
              not np.array_equal(lon, base_lon)):
            raise SystemExit("N/A projection or mass grid differs")
        models[arm], metadata[arm], hashes[arm] = field, record, pr103.sha256(path)

    differences = []
    for station in observations:
        i, j = pr103.lc_grid_ij(station["lat"], station["lon"], **projection)
        value_n, reason_n = pr103.gdtost(models["N"], i, j)
        value_a, reason_a = pr103.gdtost(models["A"], i, j)
        if reason_n or reason_a:
            raise SystemExit(f"unexpected station stencil exclusion: N={reason_n}, A={reason_a}")
        differences.append(value_n - value_a)

    delta = np.asarray(differences, dtype=np.float64)
    result = {
        "label": "model_only_operator_difference_at_13:10_on_predeclared_14Z_station_support",
        "interpretation": "H(XN)-H(XA) diagnostic only; LSO station temperatures were not read for scoring or used in arithmetic",
        "valid_time_of_station_locations_utc": "2026-08-16T14:00:00Z",
        "model_record_time_utc": "2026-08-16T13:10:00Z",
        "observation_file": str(LSO), "observation_sha256": LSO_SHA256,
        "lso_header_record_counts": counts,
        "station_locations": len(observations), "paired_locations": int(delta.size),
        "excluded_locations": 0,
        "history_files": {arm: {"path": str(HISTORIES[arm][0]), "sha256": hashes[arm],
                                "record_index": metadata[arm]["index"],
                                "stored_time": metadata[arm]["stored_time"]}
                          for arm in ("N", "A")},
        "nonzero_signal": bool(delta.size and np.any(delta != 0.0)),
        "rms_delta_c": float(np.sqrt(np.square(delta).mean())) if delta.size else None,
        "max_abs_delta_c": float(np.abs(delta).max()) if delta.size else None,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
