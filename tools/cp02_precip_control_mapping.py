#!/usr/bin/env python3
"""Map one CP02 first-hour lost hit and a nearby retained hit to init controls."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import sys
from collections.abc import Mapping
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


REPO = Path(__file__).resolve().parents[1]
ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch")
CASE = ROOT / "cp02_six_hour_20260914"
NPZ = REPO / "docs/evidence/precip_hourly_20261027/rn1_recovery/hour_13_arrays.npz"
NPZ_SHA256 = "4290d0d2955ffde8555c2fa6c8d7655825f6e982cd2b3b7a2604d8149eea00fa"
MAPPER = REPO / "docs/evidence/precip_hourly_20261027/rn1_recovery/archived_compare_six_hour_csi.py"
MAPPER_SHA256 = "1cfa4965155ec273e8e1ca9f963bd79a5ece3bc47beb4ae3db4e8b8f5e21b2c0"
ARRAY_FIELDS = ("T", "P", "PB", "QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP")
PAYLOAD = Path("/var/tmp/cp02-binary-boundary-20261028/input/payload.nc")
SHADOW = Path("/var/tmp/cp02-binary-boundary-20261028/hydro_baseline_unlimited/HYDRO.wps.shadow.nc")
ANALYSIS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300")
INIT_FILES = {
    "OFF": ROOT / "cp02_native_12_15.B4Lwmh/real/wrfinput_d01",
    "HYDRO": ROOT / "cp02_actual12_liquid_wps.HisIOM/real_HYDRO/wrfinput_d01",
    "LIQUID": ROOT / "cp02_actual12_liquid_wps.HisIOM/real_LIQUID_RADAR_RH1/wrfinput_d01",
}
METGRID_FILES = {
    "OFF": ROOT / "cp02_native_12_15.B4Lwmh/metgrid/met_em.d01.2026-08-16_12:00:00.nc",
    "HYDRO": ROOT / "cp02_actual12_liquid_wps.HisIOM/metgrid_HYDRO/met_em.d01.2026-08-16_12:00:00.nc",
    "LIQUID": ROOT / "cp02_actual12_liquid_wps.HisIOM/metgrid_LIQUID_RADAR_RH1/met_em.d01.2026-08-16_12:00:00.nc",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_archived_mapper():
    if sha256(MAPPER) != MAPPER_SHA256:
        raise RuntimeError("archived RN1 mapper differs from its pinned source hash")
    spec = importlib.util.spec_from_file_location("cp02_archived_csi", MAPPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load archived mapper: {MAPPER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def select_points(arrays: np.lib.npyio.NpzFile) -> list[dict[str, object]]:
    lost = (arrays["reference"] >= 5.0) & (arrays["OFF"] >= 5.0) & (
        (arrays["HYDRO"] < 5.0) | (arrays["LIQUID"] < 5.0)
    )
    retained = (arrays["reference"] >= 5.0) & (arrays["OFF"] >= 5.0) & (
        arrays["HYDRO"] >= 5.0
    ) & (arrays["LIQUID"] >= 5.0)
    lost_indices = np.flatnonzero(lost)
    if lost_indices.size != 20:
        raise RuntimeError(f"expected 20 canonical first-hour lost hits; found {lost_indices.size}")
    removed_false_alarm = (arrays["reference"] < 5.0) & (arrays["OFF"] >= 5.0) & (
        (arrays["HYDRO"] < 5.0) | (arrays["LIQUID"] < 5.0)
    )
    positive_background = (arrays["reference"] > 0.0) & (arrays["reference"] < 5.0) & (
        arrays["OFF"] < 5.0
    ) & (arrays["HYDRO"] < 5.0) & (arrays["LIQUID"] < 5.0)
    selected = [("lost_hit", int(i)) for i in lost_indices[:4]]
    selected.extend(("retained_hit", int(i)) for i in np.flatnonzero(retained)[:4])
    selected.extend(("removed_false_alarm", int(i)) for i in np.flatnonzero(removed_false_alarm)[:4])
    selected.extend(("RN1_positive_reference_all_forecasts_below5mm", int(i)) for i in np.flatnonzero(positive_background)[:4])
    result = []
    for point_number, (role, index) in enumerate(selected, start=1):
        result.append({
            "point_id": f"P{point_number:02d}",
            "role": role,
            "selection_source": "canonical hour_13_arrays.npz 3688-point common-valid sample",
            "rn1_sample_index_zero_based": index,
            "target_flat_index_yx": int(arrays["flat_index_yx"][index]),
            "latitude": float(arrays["latitude"][index]),
            "longitude": float(arrays["longitude"][index]),
            "reference_mm": float(arrays["reference"][index]),
            "OFF_mm": float(arrays["OFF"][index]),
            "HYDRO_mm": float(arrays["HYDRO"][index]),
            "LIQUID_mm": float(arrays["LIQUID"][index]),
            "payload_radar_invalid_proxy": "not_in_3688point_comparison_NPZ",
        })
    # Four controls outside the RN1 sample: two with positive background rain
    # and two with positive background snow where the payload's reflectivity
    # validity bit is clear. This is a payload proxy flag, not observed truth.
    with Dataset(PAYLOAD) as payload, Dataset(SHADOW) as shadow:
        lat = np.asarray(payload["latitude"][0], dtype=np.float64)
        lon = np.asarray(payload["longitude"][:], dtype=np.float64)
        radar_valid = np.asarray(payload["radar_reflectivity_valid"][0], dtype=bool)
        shadow_radar_valid = np.asarray(shadow["radar_valid"][:], dtype=bool)
        if not np.array_equal(radar_valid, shadow_radar_valid):
            raise RuntimeError("payload reflectivity validity mask differs from HYDRO shadow radar_valid proxy")
        rain = np.asarray(shadow["background_rain"][:], dtype=np.float64)
        snow = np.asarray(shadow["background_snow"][:], dtype=np.float64)
        for species, field in (("rain", rain), ("snow", snow)):
            eligible = (~radar_valid) & (field > 0.0)
            counts = np.count_nonzero(eligible, axis=0)
            column_indices = np.flatnonzero(counts > 0)
            if column_indices.size < 2:
                raise RuntimeError(f"insufficient invalid-reflectivity positive-{species} source columns")
            # Select strongest positive background columns, then stable
            # flat-index tie-break. These are exploratory external controls.
            maxima = np.max(np.where(eligible, field, 0.0), axis=0).ravel()
            candidate_indices = column_indices
            if candidate_indices.size < 2:
                raise RuntimeError(f"insufficient invalid-reflectivity positive-{species} source columns")
            order = np.lexsort((candidate_indices, -maxima[candidate_indices]))
            for index in candidate_indices[order[:2]]:
                j, i = np.unravel_index(int(index), lat.shape)
                levels = np.flatnonzero(eligible[:, j, i] & (field[:, j, i] > 0.0))
                level = int(levels[0])
                result.append({
                    "point_id": f"P{len(result)+1:02d}",
                    "role": f"payload_positive_{species}_reflectivity_invalid_proxy",
                    "selection_source": str(PAYLOAD),
                    "rn1_sample_index_zero_based": "",
                    "target_flat_index_yx": "",
                    "latitude": float(lat[j, i]), "longitude": float(lon[j, i]),
                    "reference_mm": "", "OFF_mm": "", "HYDRO_mm": "", "LIQUID_mm": "",
                    "payload_radar_invalid_proxy": True,
                    "payload_source_j_zero_based": int(j), "payload_source_i_zero_based": int(i),
                    "proxy_positive_species": species, "proxy_level_zero_based": level,
                    "proxy_background_mixing_ratio_kgkg": float(field[level, j, i]),
                })
    if len(result) != 20 or len({(p["latitude"], p["longitude"]) for p in result}) != 20:
        raise RuntimeError("selection must contain 20 unique source columns")
    return result


def make_mapping(mapper, points: list[dict[str, object]], arrays: np.lib.npyio.NpzFile):
    inventory, fixed_mask, target_lat, target_lon, provenance = mapper.load_reference(
        CASE / "reference", Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300")
    )
    point_positions = []
    point_mask = np.zeros(target_lat.shape, dtype=bool)
    for point in points:
        if point["target_flat_index_yx"] != "":
            y, x = np.divmod(int(point["target_flat_index_yx"]), target_lat.shape[1])
            if (float(target_lat[y, x]), float(target_lon[y, x])) != (point["latitude"], point["longitude"]):
                raise RuntimeError(f"canonical NPZ coordinates do not match ODAM grid at {point['role']}")
        else:
            # Payload controls already name exact source columns. Their WRF
            # native location is found by geographic inversion below.
            y, x = -1, -1
        point_positions.append((int(y), int(x)))
        if y >= 0:
            point_mask[y, x] = True
    crop_x = inventory["grid"]["crop_x_inclusive"]
    crop_y = inventory["grid"]["crop_y_inclusive"]
    jbase, ibase = crop_y[0] - 2, crop_x[0] - 2
    with Dataset(CASE / "off/run/wrfout_d01_2026-08-16_13:00:00") as dataset:
        source_lat = np.asarray(dataset["XLAT"][0], dtype=np.float64)
        source_lon = np.asarray(dataset["XLONG"][0], dtype=np.float64)
    corner_lat = source_lat[jbase : crop_y[1], ibase : crop_x[1]]
    corner_lon = source_lon[jbase : crop_y[1], ibase : crop_x[1]]
    mapping = mapper.build_curvilinear_mapping(corner_lat, corner_lon, target_lat, target_lon, point_mask)
    points_out = []
    for point, (y, x) in zip(points, point_positions):
        if y >= 0:
            j0, i0 = int(mapping["j0"][y, x]) + jbase, int(mapping["i0"][y, x]) + ibase
            u, v = float(mapping["u"][y, x]), float(mapping["v"][y, x])
            residual = float(mapping["residual_max_deg"])
            target_y, target_x = y, x
        else:
            j0, i0, u, v, residual = inverse_grid_mapping(source_lat, source_lon, float(point["latitude"]), float(point["longitude"]))
            target_y = target_x = ""
        stencil = ((j0, i0), (j0, i0 + 1), (j0 + 1, i0), (j0 + 1, i0 + 1))
        weights = ((1-u)*(1-v), u*(1-v), (1-u)*v, u*v)
        points_out.append({**point, "target_y_zero_based": target_y, "target_x_zero_based": target_x, "native_j0_zero_based": j0,
                           "native_i0_zero_based": i0, "bilinear_u": u, "bilinear_v": v,
                           "coordinate_residual_max_deg": residual,
                           "corners": [{"corner": label, "native_j_zero_based": jj, "native_i_zero_based": ii, "weight": float(w)}
                                       for label, (jj, ii), w in zip(("00", "10", "01", "11"), stencil, weights)]})
    # Map each point independently onto the original payload grid. These
    # coordinates are the original-grid capture controls; the WRF stencil is
    # retained separately above and is never treated as index-identical.
    with Dataset(PAYLOAD) as payload:
        payload_lat = np.asarray(payload["latitude"][0], dtype=np.float64)
        payload_lon = np.asarray(payload["longitude"][:], dtype=np.float64)
    for point in points_out:
        pj, pi, pu, pv, residual = inverse_grid_mapping(payload_lat, payload_lon, float(point["latitude"]), float(point["longitude"]))
        pw = ((1-pu)*(1-pv), pu*(1-pv), (1-pu)*pv, pu*pv)
        point["sourcegrid_j0_zero_based"] = pj
        point["sourcegrid_i0_zero_based"] = pi
        point["sourcegrid_u"] = pu
        point["sourcegrid_v"] = pv
        point["sourcegrid_coordinate_residual_max_deg"] = residual
        source_corners = [{"corner": label, "shadow_j_zero_based": jj, "shadow_i_zero_based": ii, "weight": float(w)}
                          for label, (jj, ii), w in zip(("00", "10", "01", "11"), ((pj,pi),(pj,pi+1),(pj+1,pi),(pj+1,pi+1)), pw)]
        source_point = source_corners[int(np.argmax(pw))]
        point["sourcegrid_point_j_zero_based"] = source_point["shadow_j_zero_based"]
        point["sourcegrid_point_i_zero_based"] = source_point["shadow_i_zero_based"]
        point["sourcegrid_point_weight"] = float(max(pw))
        point["sourcegrid_corners"] = source_corners
        if point["rn1_sample_index_zero_based"] == "":
            point["external_control_distance_to_rn1_sample_km"] = nearest_sample_distance(
                float(point["latitude"]), float(point["longitude"]), arrays
            )
    return points_out, source_lat, source_lon, provenance, inventory


def inverse_grid_mapping(source_lat: np.ndarray, source_lon: np.ndarray, target_lat: float, target_lon: float):
    """Invert one curvilinear lat/lon cell with bounded Newton steps."""
    scale = math.cos(math.radians(target_lat))
    distance = (source_lat - target_lat) ** 2 + ((source_lon - target_lon) * scale) ** 2
    nearest_j, nearest_i = np.unravel_index(int(np.argmin(distance)), distance.shape)
    candidates = []
    for j0 in range(max(0, nearest_j - 2), min(source_lat.shape[0] - 1, nearest_j + 2)):
        for i0 in range(max(0, nearest_i - 2), min(source_lat.shape[1] - 1, nearest_i + 2)):
            a_lat = np.array((source_lat[j0, i0], source_lat[j0, i0 + 1], source_lat[j0 + 1, i0], source_lat[j0 + 1, i0 + 1]))
            a_lon = np.array((source_lon[j0, i0], source_lon[j0, i0 + 1], source_lon[j0 + 1, i0], source_lon[j0 + 1, i0 + 1]))
            u = v = 0.5
            for _ in range(12):
                w = np.array(((1-u)*(1-v), u*(1-v), (1-u)*v, u*v))
                lat = float(w @ a_lat); lon = float(w @ a_lon)
                dlat_du = (1-v)*(a_lat[1]-a_lat[0]) + v*(a_lat[3]-a_lat[2])
                dlat_dv = (1-u)*(a_lat[2]-a_lat[0]) + u*(a_lat[3]-a_lat[1])
                dlon_du = (1-v)*(a_lon[1]-a_lon[0]) + v*(a_lon[3]-a_lon[2])
                dlon_dv = (1-u)*(a_lon[2]-a_lon[0]) + u*(a_lon[3]-a_lon[1])
                determinant = dlat_du*dlon_dv - dlon_du*dlat_dv
                if abs(determinant) < 1.0e-14:
                    break
                e_lat, e_lon = lat-target_lat, lon-target_lon
                u -= (e_lat*dlon_dv - e_lon*dlat_dv) / determinant
                v -= (dlat_du*e_lon - dlon_du*e_lat) / determinant
            w = np.array(((1-u)*(1-v), u*(1-v), (1-u)*v, u*v))
            residual = max(abs(float(w @ a_lat)-target_lat), abs(float(w @ a_lon)-target_lon))
            if -1.0e-8 <= u <= 1.0+1.0e-8 and -1.0e-8 <= v <= 1.0+1.0e-8:
                candidates.append((residual, j0, i0, min(1.0, max(0.0, u)), min(1.0, max(0.0, v))))
    if not candidates:
        raise RuntimeError(f"coordinate is outside native WRF grid: {target_lat}, {target_lon}")
    residual, j0, i0, u, v = min(candidates)
    if residual > 1.0e-6:
        raise RuntimeError(f"native WRF bilinear coordinate residual too large: {residual}")
    return j0, i0, u, v, residual


def nearest_sample_distance(latitude: float, longitude: float, arrays: np.lib.npyio.NpzFile) -> float:
    lat1, lon1 = math.radians(latitude), math.radians(longitude)
    lat = np.radians(arrays["latitude"])
    lon = np.radians(arrays["longitude"])
    dlat, dlon = lat - lat1, lon - lon1
    a = np.sin(dlat / 2) ** 2 + math.cos(lat1) * np.cos(lat) * np.sin(dlon / 2) ** 2
    return float(np.min(6371.0088 * 2 * np.arcsin(np.sqrt(a))))


def validate_capture_points(points: list[dict[str, object]]) -> None:
    if not isinstance(points, list) or len(points) != 20:
        raise ValueError("capture selection must contain exactly 20 points")
    if any(not isinstance(point, Mapping) for point in points):
        raise ValueError("capture selection entries must be mappings")
    point_ids = [point.get("point_id") for point in points]
    coordinates = [(point.get("latitude"), point.get("longitude")) for point in points]
    source_indices = [(point.get("sourcegrid_point_j_zero_based"), point.get("sourcegrid_point_i_zero_based")) for point in points]
    if any(not isinstance(value, str) or not value for value in point_ids) or len(set(point_ids)) != 20:
        raise ValueError("capture selection point IDs must be nonempty and unique")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for pair in coordinates for value in pair):
        raise ValueError("capture selection coordinates must be finite numbers")
    if len(set(coordinates)) != 20:
        raise ValueError("capture selection coordinates must be unique")
    if any(type(j) is not int or type(i) is not int or j < 0 or i < 0 for j, i in source_indices) or len(set(source_indices)) != 20:
        raise ValueError("capture selection source-grid indices must be valid and unique")
    roles = {role: sum(point.get("role") == role for point in points) for role in {
        "lost_hit", "retained_hit", "removed_false_alarm", "RN1_positive_reference_all_forecasts_below5mm",
        "payload_positive_rain_reflectivity_invalid_proxy", "payload_positive_snow_reflectivity_invalid_proxy"}}
    if roles != {"lost_hit": 4, "retained_hit": 4, "removed_false_alarm": 4,
                "RN1_positive_reference_all_forecasts_below5mm": 4,
                "payload_positive_rain_reflectivity_invalid_proxy": 2,
                "payload_positive_snow_reflectivity_invalid_proxy": 2}:
        raise ValueError(f"capture selection category counts are invalid: {roles}")


def extract_controls(points: list[dict[str, object]], source_lat: np.ndarray, source_lon: np.ndarray):
    control_rows, metgrid_rows, source_files = [], [], []
    for arm in ("OFF", "HYDRO", "LIQUID"):
        init_path, metgrid_path = INIT_FILES[arm], METGRID_FILES[arm]
        source_files.extend((
            {"kind": "wrfinput_d01", "arm": arm, "path": str(init_path), "size": init_path.stat().st_size, "sha256": sha256(init_path)},
            {"kind": "met_em", "arm": arm, "path": str(metgrid_path), "size": metgrid_path.stat().st_size, "sha256": sha256(metgrid_path)},
        ))
        with Dataset(init_path) as init, Dataset(metgrid_path) as metgrid:
            ilat, ilon = np.asarray(init["XLAT"][0]), np.asarray(init["XLONG"][0])
            if not np.array_equal(ilat, source_lat) or not np.array_equal(ilon, source_lon):
                raise RuntimeError(f"WRF input coordinates differ from native history grid for {arm}")
            mlat, mlon = np.asarray(metgrid["XLAT_M"][0]), np.asarray(metgrid["XLONG_M"][0])
            if mlat.shape != source_lat.shape or mlon.shape != source_lon.shape:
                raise RuntimeError(f"metgrid coordinate shapes differ for {arm}")
            for point in points:
                corners = point["corners"]
                js = [int(c["native_j_zero_based"]) for c in corners]
                is_ = [int(c["native_i_zero_based"]) for c in corners]
                weights = np.array([float(c["weight"]) for c in corners])
                target_lat, target_lon = float(point["latitude"]), float(point["longitude"])
                for source, lat_grid, lon_grid in (("wrfinput", ilat, ilon), ("met_em", mlat, mlon)):
                    lat_res = abs(float(weights @ lat_grid[js, is_]) - target_lat)
                    lon_res = abs(float(weights @ lon_grid[js, is_]) - target_lon)
                    if max(lat_res, lon_res) > 2.0e-6:
                        raise RuntimeError(f"{source} coordinate interpolation mismatch for {arm} {point['role']}: {lat_res}, {lon_res}")
                for k in range(init.dimensions["bottom_top"].size):
                    for name in ARRAY_FIELDS:
                        plane = np.asarray(init[name][0, k, :, :], dtype=np.float64)
                        values = plane[js, is_]
                        control_rows.append({"arm": arm, "point_id": point["point_id"], "role": point["role"], "latitude": point["latitude"], "longitude": point["longitude"],
                                             "target_flat_index_yx": point["target_flat_index_yx"],
                                             "sourcegrid_point_j_zero_based": point["sourcegrid_point_j_zero_based"], "sourcegrid_point_i_zero_based": point["sourcegrid_point_i_zero_based"],
                                             "wrf_bottom_top_k_zero_based": k, "field": name,
                                             "bilinear_value": float(weights @ values),
                                             **{f"corner_{c['corner']}_value": float(value) for c, value in zip(corners, values)}})
                for k in range(metgrid.dimensions["num_metgrid_levels"].size):
                    for name in ("QR", "QS"):
                        plane = np.asarray(metgrid[name][0, k, :, :], dtype=np.float64)
                        values = plane[js, is_]
                        metgrid_rows.append({"arm": arm, "point_id": point["point_id"], "role": point["role"], "latitude": point["latitude"], "longitude": point["longitude"],
                                             "target_flat_index_yx": point["target_flat_index_yx"],
                                             "sourcegrid_point_j_zero_based": point["sourcegrid_point_j_zero_based"], "sourcegrid_point_i_zero_based": point["sourcegrid_point_i_zero_based"],
                                             "metgrid_level_zero_based": k, "field": name,
                                             "bilinear_value": float(weights @ values),
                                             **{f"corner_{c['corner']}_value": float(value) for c, value in zip(corners, values)}})
    return control_rows, metgrid_rows, source_files


def reconstruct_precipitation(mapper, points, inventory, arrays):
    rows = []
    rn1_points = [p for p in points if p["rn1_sample_index_zero_based"] != ""]
    for arm in ("OFF", "HYDRO", "LIQUID"):
        cumulative = {}
        for hour in (12, 13):
            path = CASE / arm.lower() / "run" / f"wrfout_d01_2026-08-16_{hour:02d}:00:00"
            snapshot = mapper.read_wrf_snapshot(path, datetime(2026, 8, 16, hour, tzinfo=timezone.utc), inventory)
            cumulative[hour] = mapper.raw_total(snapshot)[0]
        for point in rn1_points:
            j0, i0 = int(point["native_j0_zero_based"]), int(point["native_i0_zero_based"])
            u, v = float(point["bilinear_u"]), float(point["bilinear_v"])
            one_u, one_v = 1.0-u, 1.0-v
            before = float(one_u*one_v*cumulative[12][j0,i0] + u*one_v*cumulative[12][j0,i0+1]
                           + one_u*v*cumulative[12][j0+1,i0] + u*v*cumulative[12][j0+1,i0+1])
            after = float(one_u*one_v*cumulative[13][j0,i0] + u*one_v*cumulative[13][j0,i0+1]
                          + one_u*v*cumulative[13][j0+1,i0] + u*v*cumulative[13][j0+1,i0+1])
            increment = after - before
            sample = int(point["rn1_sample_index_zero_based"])
            expected = float(arrays[arm][sample])
            rows.append({"arm": arm, "point_id": point["point_id"], "role": point["role"], "rn1_sample_index_zero_based": sample,
                         "target_flat_index_yx": point["target_flat_index_yx"], "expected_hourly_increment_mm": expected,
                         "remapped_12z_cumulative_mm": before, "remapped_13z_cumulative_mm": after,
                         "reconstructed_increment_mm": increment, "exact_equal": increment == expected,
                         "difference_mm": increment - expected})
    if len(rows) != 48 or not all(row["exact_equal"] for row in rows):
        maximum = max(abs(float(row["difference_mm"])) for row in rows)
        raise RuntimeError(f"first-hour NPZ reconstruction failed; max abs error={maximum}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=REPO / "docs/evidence/cp02_density_controls_20261029/controls")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing evidence: {output}")
    history_paths = [CASE / arm.lower() / "run" / f"wrfout_d01_2026-08-16_{hour:02d}:00:00"
                     for arm in ("OFF", "HYDRO", "LIQUID") for hour in (12, 13)]
    reference_dir = CASE / "reference"
    mask_receipt_path = reference_dir / "mask_receipt.json"
    mask_receipt = json.loads(mask_receipt_path.read_text(encoding="utf-8"))
    mask_path = Path(mask_receipt["artifact"])
    if not mask_path.is_absolute():
        mask_path = reference_dir / mask_path
    reference_paths = [reference_dir / "inventory.json", mask_receipt_path, mask_path, ANALYSIS,
                       CASE / "run_contract.md", CASE / "ONE_HOUR_REPRODUCTION.json"]
    input_paths = list(dict.fromkeys([NPZ, MAPPER, PAYLOAD, SHADOW, *INIT_FILES.values(), *METGRID_FILES.values(), *history_paths, *reference_paths]))
    input_hashes_before = {str(path): {"size": path.stat().st_size, "sha256": sha256(path)} for path in input_paths}
    fixed_hashes = {str(NPZ): NPZ_SHA256, str(MAPPER): MAPPER_SHA256,
                    str(PAYLOAD): "03f6bb5da1986fa62972256483fb245ca4132d1dade3e056b3c3f435cd6e0097",
                    str(SHADOW): "c1f5d039ac73c90cb6b21dd619ebc5774f3b6c7387c9b9701af4360fb635f2cb"}
    fixed_hashes.update({str(INIT_FILES[arm]): value for arm, value in {
        "OFF": "5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc",
        "HYDRO": "7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126",
        "LIQUID": "1dae2480a9ff4c4a386abf9ff5210f36ad3162330e2dc579d870d64b37be4470",
    }.items()})
    for path, expected in fixed_hashes.items():
        if input_hashes_before[path]["sha256"] != expected:
            raise RuntimeError(f"source hash differs from pinned input: {path}")
    if sha256(NPZ) != NPZ_SHA256:
        raise RuntimeError("canonical first-hour RN1 comparison NPZ differs from its pinned hash")
    mapper = load_archived_mapper()
    arrays = np.load(NPZ)
    points = select_points(arrays)
    mapped_points, source_lat, source_lon, provenance, inventory = make_mapping(mapper, points, arrays)
    validate_capture_points(mapped_points)
    controls, metgrid, source_files = extract_controls(mapped_points, source_lat, source_lon)
    precip_checks = reconstruct_precipitation(mapper, mapped_points, inventory, arrays)
    # Recheck inputs to make the read-only extraction stable across the run.
    for item in source_files:
        if sha256(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"source changed during extraction: {item['path']}")
    input_hashes_after = {str(path): {"size": path.stat().st_size, "sha256": sha256(path)} for path in input_paths}
    for path, before in input_hashes_before.items():
        if input_hashes_after[path] != before:
            raise RuntimeError(f"source size/hash changed during extraction: {path}")
    output.mkdir(parents=True)
    wrf_mapping_rows = []
    source_mapping_rows = []
    for point in mapped_points:
        for corner in point["corners"]:
            wrf_mapping_rows.append({key: value for key, value in point.items() if key not in ("corners", "sourcegrid_corners")} | corner)
        for corner in point["sourcegrid_corners"]:
            source_mapping_rows.append({key: value for key, value in point.items() if key not in ("corners", "sourcegrid_corners")} | corner)
    scalar_points = [{key: value for key, value in point.items() if key not in ("corners", "sourcegrid_corners")} for point in mapped_points]
    for filename, rows in (("selected_points.csv", scalar_points), ("wrf_mapping.csv", wrf_mapping_rows),
                           ("source_grid_mapping.csv", source_mapping_rows), ("wrfinput_corner_controls.csv", controls),
                           ("metgrid_corner_controls.csv", metgrid), ("precipitation_reconstruction.csv", precip_checks)):
        with (output / filename).open("x", newline="") as stream:
            columns = list(dict.fromkeys(key for row in rows for key in row.keys()))
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    capture_rows = []
    for point in mapped_points:
        source_point = max(point["sourcegrid_corners"], key=lambda item: float(item["weight"]))
        capture_rows.append({
            "point_id": point["point_id"], "role": point["role"], "rn1_sample_index_zero_based": point["rn1_sample_index_zero_based"],
            "target_flat_index_yx": point["target_flat_index_yx"], "latitude": point["latitude"], "longitude": point["longitude"],
            "reference_mm": point["reference_mm"], "OFF_mm": point["OFF_mm"], "HYDRO_mm": point["HYDRO_mm"], "LIQUID_mm": point["LIQUID_mm"],
            "payload_radar_invalid_proxy": point["payload_radar_invalid_proxy"],
            "external_control_distance_to_rn1_sample_km": point.get("external_control_distance_to_rn1_sample_km", ""),
            "shadow_j_zero_based": source_point["shadow_j_zero_based"], "shadow_i_zero_based": source_point["shadow_i_zero_based"],
            "sourcegrid_corner": source_point["corner"], "sourcegrid_weight": source_point["weight"],
            "mapping_source": "payload latitude/longitude bilinear inversion; max-weight original source column",
        })
    with (output / "capture_points.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(capture_rows[0].keys()))
        writer.writeheader()
        writer.writerows(capture_rows)
    receipt = {
        "status": "PASS_CP02_FIRST_HOUR_POINT_TO_INITIALIZATION_CONTROLS",
        "valid_time_utc": "2026-08-16T12:00:00Z",
        "forecast_valid_time_utc": "2026-08-16T13:00:00Z",
        "selection": "4 each: lost hits (reference>=5, OFF>=5, any treatment<5), retained hits (reference and all forecasts>=5), removed OFF false alarms (reference<5, OFF>=5, any treatment<5), RN1-positive reference below 5 mm with all forecasts below 5 mm; plus 2 payload positive-rain and 2 positive-snow columns with payload reflectivity-valid=0; point IDs P01-P20 are stable within this receipt",
        "point_count": len(mapped_points),
        "points": mapped_points,
        "mapping_method": "RN1 sample target -> native WRF corners uses archived compare_six_hour_csi.py curvilinear bilinear map; original source-grid controls are independently solved from lat/lon in pinned payload.nc. Payload proxy controls map to WRF by coordinate inversion. Indices are not equated.",
        "coordinate_checks": "weighted native WRF and payload source-grid corner coordinates reproduce each requested target coordinate; coordinate residuals are recorded per point. sourcegrid_point_i/j identifies the highest-weight source column for the 20-column capture list; the full interpolation stencil remains available in source_grid_mapping.csv",
        "precipitation_reconstruction": {"point_count": 16, "arm_point_checks": len(precip_checks), "exact_array_equal": all(row["exact_equal"] for row in precip_checks), "max_abs_error_mm": max(abs(float(row["difference_mm"])) for row in precip_checks)},
        "sources": [{"path": path, "size_before": before["size"], "sha256_before": before["sha256"],
                     "size_after": input_hashes_after[path]["size"], "sha256_after": input_hashes_after[path]["sha256"],
                     "unchanged": before == input_hashes_after[path]} for path, before in input_hashes_before.items()],
        "extraction_tool": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).resolve())},
        "source_role_records": [{"kind": name, "path": str(path), "sha256": sha256(path)} for name, path in provenance.items()],
        "fields": {"wrfinput": list(ARRAY_FIELDS), "met_em": ["QR", "QS"]},
        "limitations": ["No GDB/runtime capture performed; this freezes twenty points for later authorized capture.",
                        "The RN1 arrays are paired comparison data for 3688 common valid points; payload reflectivity_valid/radar_valid are shadow input proxies, not independent observed-radar truth.",
                        "The four payload proxy points are external exploratory controls, not verification-linked or causal controls; their nearest RN1 sample distances are explicit.",
                        "Metgrid levels and WRF bottom_top levels are not interchangeable; separate files preserve each vertical coordinate.",
                        "OFF, HYDRO, and LIQUID initial inputs have distinct recorded preparation ancestry; differences do not identify a single causal operation.",
                        "The prelabel draft capture CSV was not consumed by runtime capture; capture_points.csv is the corrected frozen input."],
        "outputs": {name: {"path": name, "sha256": sha256(output / name)} for name in ("capture_points.csv", "selected_points.csv", "wrf_mapping.csv", "source_grid_mapping.csv", "wrfinput_corner_controls.csv", "metgrid_corner_controls.csv", "precipitation_reconstruction.csv")},
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "point_count": receipt["point_count"],
                      "precipitation_reconstruction": receipt["precipitation_reconstruction"],
                      "capture_points_sha256": receipt["outputs"]["capture_points.csv"]["sha256"]}))


if __name__ == "__main__":
    main()
