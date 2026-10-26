#!/usr/bin/env python3
"""Reproduce pinned GK2A LVD metadata, fill counts, and grid footprint audit."""
from __future__ import annotations

import hashlib
import argparse
import datetime as dt
import json
from pathlib import Path

import netCDF4
import numpy as np
from scipy.ndimage import binary_dilation
from scipy.spatial import cKDTree

ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50")
BAL = Path(__file__).resolve().parents[3]
LVD = ROOT / "ANAL/NE57/DAOU/00/lapsprd/lvd/kogk2a/262281400.lvd"
STATIC = ROOT / "ANAL/NE57/DABA/static.nest7grid"
COMPOSITION = ROOT / "scratch/pr103_amplitude_control_20261026/Cloud-BAL/docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json"
HORIZONTAL_ROWS = ROOT / "scratch/pr103_amplitude_control_20261026/Cloud-BAL/docs/evidence/pr93_qc_chain_20261020/laps_qc_horizontal_rows.json"
WRF = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr103_amplitude20_capture_20261026/AMPLITUDE640_RUN/run/wrfout_d01_2026-08-16_13:00:00")
PR104_STATIONS = ROOT / "scratch/pr104_validtime_observation_20261026/Cloud-BAL/docs/evidence/pr104_observation_audit_20261026/station_mask_coverage_14z.json"
REPLAY_RECEIPT = ROOT / "scratch/pr104_validtime_observation_20261026/Cloud-BAL/tests/original_upstream_replay_20260816.json"
OUTPUT = Path(__file__).with_name("satellite_lvd_audit_v3.json")
SOURCE_REFS = [
    {"root": "KLAPS50", "path": "klaps-v5.0_/src/ingest/satellite/lvd_gk2a/lvd_driver_sub.f", "lines": "21-34,843-868,1011-1034", "sha256": "f36784c270ab90a52d5768f50ffb8b79dc0c3c8ba2125853d5a64a6d17ff1545", "claim": "source-declared legacy channel numbers, wavelengths, product names and units"},
    {"root": "KLAPS50", "path": "klaps-v5.0_/src/cloud_20200204/get_sat_data.f", "lines": "68-135", "sha256": "ec9a3a407231a4e2a0c9b267d774bcdf736fa283951320bd05b74461a6aced90", "claim": "legacy cloud reader loads S8A and optional S3A; range-checks S8A"},
    {"root": "KLAPS50", "path": "klaps-v5.0_/src/cloud_20200204/getvis.f", "lines": "108-122", "sha256": "e28d1302081b5f82c4be0558fac86225f766571b4a954e3ac8f680799144a66b", "claim": "legacy visible-cloud reader loads ALB"},
    {"root": "KLAPS50", "path": "klaps-v5.0_/src/cloud_20200204/insertsat.f", "lines": "1302-1322,1360-1450", "sha256": "0b22d2d45d77001821111cb8ebd080928d89632df1fba241fbe76c5070cf9341", "claim": "empirical radiation/BT comparison adjusts cloud fractions with a 4-degree threshold and 0.05 cover step; not a general atmospheric forward RTM"},
    {"root": "KLAPS50", "path": "klaps-v5.0_/src/lib/opt90/rtm_test_FWD.f90", "lines": "3-34", "sha256": "d793f05c894d94949ebbe23036bcbb510fc4d514ae8080555168ce5aa07e0075", "claim": "separate NCEP RTM forward test utility; not evidence of GK2A channel binding or C2 runtime use"},
    {"root": "Cloud-BAL", "path": "src/common/cloud_bal_state.f90", "lines": "188-209", "sha256": "791e60fbf157c304a6945e7b04c11d3a7f8c36d82bb5c692d0b4a2ab97634d61", "claim": "Cloud-BAL state declares cloud fraction and radar reflectivity, not satellite BT"}
]
PINS = {
    LVD: "e7d2e745782dcfec29f0097183c510b759cefceab6617b2398d8a2b68cecb841",
    STATIC: "384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b",
    COMPOSITION: "331eb9837c41a7aa663864c348f8fe18c44f8e55feed736900f5029685b1aa64",
    HORIZONTAL_ROWS: "699b503c84cdeccd6020263a0a54ae3193eb2a0d29664f3c4a68ce142d68d8b8",
    WRF: "67ec6197a5f1aed9e90f56c49d5af34e9f685167f7ac2427884b9bcdef8707a4",
    PR104_STATIONS: "701a167a22da42552faa6beabc88a93e9843db2ae25b009841aae502f8d786ed",
    REPLAY_RECEIPT: "08b03eaf46c7b19e055af0da3585ee630c9578f8338910c91519ae9a90ef86e5",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def xyz(latitude: np.ndarray, longitude: np.ndarray) -> np.ndarray:
    lat = np.deg2rad(latitude)
    lon = np.deg2rad(longitude)
    return np.column_stack((np.cos(lat) * np.cos(lon),
                            np.cos(lat) * np.sin(lon), np.sin(lat)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT,
                        help="write to a new file (exclusive create); use - for stdout")
    args = parser.parse_args()
    pins = {str(path): sha256(path) for path in PINS}
    if any(pins[str(path)] != expected for path, expected in PINS.items()):
        raise SystemExit("pinned input hash mismatch")
    for source in SOURCE_REFS:
        base = ROOT if source["root"] == "KLAPS50" else BAL
        source_path = base / source["path"]
        if sha256(source_path) != source["sha256"]:
            raise SystemExit(f"pinned source hash mismatch: {source_path}")
    composition = json.loads(COMPOSITION.read_text())["composed_qc_vertical_influence"]
    composition_doc = json.loads(COMPOSITION.read_text())
    horizontal_rows = json.loads(HORIZONTAL_ROWS.read_text())
    horizontal_binding = composition_doc["input_bindings"]
    if horizontal_binding["horizontal_rows_sha256"] != pins[str(HORIZONTAL_ROWS)]:
        raise SystemExit("horizontal source-row input pin does not match frozen QC composition")
    if Path(horizontal_binding["horizontal_rows_path"]).name != HORIZONTAL_ROWS.name:
        raise SystemExit("horizontal source-row binding names an unexpected artifact")
    source_grid = horizontal_rows["source_grid"]
    replay_receipt = json.loads(REPLAY_RECEIPT.read_text())
    declared_static = next(row for row in replay_receipt["assets"] if row["role"] == "static_grid")
    if declared_static["path"] != "ANAL/NE57/DABA/static.nest7grid" or declared_static["sha256"] != pins[str(STATIC)]:
        raise SystemExit("static grid does not match the original upstream replay asset binding")
    station_coverage = json.loads(PR104_STATIONS.read_text())

    with netCDF4.Dataset(LVD) as lvd, netCDF4.Dataset(STATIC) as static, netCDF4.Dataset(WRF) as wrf:
        lat = np.asarray(static.variables["lat"][0, 0], dtype=np.float64)
        lon = np.asarray(static.variables["lon"][0, 0], dtype=np.float64)
        lvd_dims = {name: len(dim) for name, dim in lvd.dimensions.items()}
        if lat.shape != (lvd_dims["y"], lvd_dims["x"]):
            raise SystemExit("LVD and receipt-bound LAPS static grid shapes differ")
        grid_metadata = {}
        grid_metadata_differences = {}
        for name in ("Nx", "Ny", "La1", "Lo1", "LoV", "Latin1", "Latin2", "Dx", "Dy"):
            lvd_value = np.asarray(lvd.variables[name][:])
            static_value = np.asarray(static.variables[name][:])
            difference = (lvd_value.astype(np.float64) - static_value.astype(np.float64)).tolist()
            if not np.allclose(lvd_value, static_value, rtol=0.0, atol=1e-6):
                raise SystemExit(f"LVD and receipt-bound static projection metadata differ beyond 1e-6: {name}")
            grid_metadata[name] = lvd_value.tolist()
            grid_metadata_differences[name] = difference
        corner_difference = {
            "La1_deg": float(lat[0, 0]) - float(lvd.variables["La1"][0]),
            "Lo1_deg": float(lon[0, 0]) - float(lvd.variables["Lo1"][0]),
        }
        if not np.allclose(list(corner_difference.values()), 0.0, rtol=0.0, atol=1e-6):
            raise SystemExit("LVD and receipt-bound static SW corner differs beyond 1e-6 degrees")
        source_grid_differences = {
            "nx_points": int(source_grid["dimensions_xy"][0]) - lat.shape[1],
            "ny_points": int(source_grid["dimensions_xy"][1]) - lat.shape[0],
            "dx_km": float(source_grid["dx_km_f32"]) - float(static.variables["Dx"][0]) / 1000.0,
            "dy_km": float(source_grid["dy_km_f32"]) - float(static.variables["Dy"][0]) / 1000.0,
            "sw_lat_deg": float(source_grid["startlat_f32"]) - float(lvd.variables["La1"][0]),
            "sw_lon_deg": float(source_grid["startlon_f32"]) - float(lvd.variables["Lo1"][0]),
            "stdlon_deg": float(source_grid["stdlon_f32"]) - float(lvd.variables["LoV"][0]),
            "truelat1_deg": float(source_grid["truelat1_f32"]) - float(lvd.variables["Latin1"][0]),
            "truelat2_deg": float(source_grid["truelat2_f32"]) - float(lvd.variables["Latin2"][0]),
        }
        if any(value != 0 for value in source_grid_differences.values()):
            raise SystemExit("pinned horizontal-row source grid differs from LVD/static metadata")

        field_counts = {}
        for name, variable in lvd.variables.items():
            if variable.ndim != 4:
                continue
            values = np.asarray(variable[0, 0], dtype=np.float64)
            fill = float(getattr(variable, "_FillValue", np.nan))
            valid = np.isfinite(values) & (values != fill)
            field_counts[name] = {
                "units": getattr(variable, "units", ""),
                "long_name": getattr(variable, "long_name", ""),
                "finite_nonfill": int(valid.sum()),
                "raster_cells": int(values.size),
                "valid_min": float(values[valid].min()) if valid.any() else None,
                "valid_max": float(values[valid].max()) if valid.any() else None,
            }

        support_cells = set()
        source_cells = set()
        support_levels = 0
        for target in composition["targets"]:
            i, j = int(target["target_i0"]), int(target["target_j0"])
            for level in target["native_levels"]:
                if level["composed_qc_source_links"]:
                    support_levels += 1
                    support_cells.add((j, i))
                    for link in level["composed_qc_source_links"]:
                        source_cells.add((int(link["source_j0"]), int(link["source_i0"])))

        # The frozen 16-column mask is on active WRF mass points. Its indices
        # are the exact target_i0/target_j0 coordinates in the full WRF grid.
        wrf_lat = np.asarray(wrf.variables["XLAT"][0], dtype=np.float64)
        wrf_lon = np.asarray(wrf.variables["XLONG"][0], dtype=np.float64)
        if wrf_lat.shape != (282, 234):
            raise SystemExit("closed WRF history grid shape changed")
        support = np.zeros(wrf_lat.shape, dtype=bool)
        for j, i in support_cells:
            support[j, i] = True
        buffer = binary_dilation(support, structure=np.ones((11, 11), dtype=bool))
        if int(support.sum()) != 16 or int(buffer.sum()) != 196:
            raise SystemExit("frozen support or five-cell Chebyshev buffer changed")

        horizontal_source_cells = {
            (int(row["source_j0"]), int(row["source_i0"]))
            for row in horizontal_rows["links_by_source_cell"]
        }
        if horizontal_source_cells != source_cells or len(horizontal_source_cells) != 9:
            raise SystemExit("horizontal source rows and composed QC source cells disagree")
        if sum(len(row["source_pressure_k0"]) for row in horizontal_rows["links_by_source_cell"]) != 162:
            raise SystemExit("pinned horizontal rows no longer represent 162 source pressure cells")

        tree = cKDTree(xyz(lat.ravel(), lon.ravel()))
        nearest_distance, nearest_index = tree.query(xyz(wrf_lat[buffer], wrf_lon[buffer]))
        lvd_cells = np.unique(nearest_index)
        nearest_km = 6371.229 * 2 * np.arcsin(np.minimum(1.0, nearest_distance / 2.0))
        support_distance, support_index = tree.query(xyz(wrf_lat[support], wrf_lon[support]))
        support_cells_lvd = np.unique(support_index)
        support_km = 6371.229 * 2 * np.arcsin(np.minimum(1.0, support_distance / 2.0))
        channel_cells = {}
        for name in ("s3a", "s3c", "s4a", "s4c", "s8a", "s8w", "s8c", "sca", "scc"):
            values = np.asarray(lvd.variables[name][0, 0], dtype=np.float64).ravel()
            fill = float(getattr(lvd.variables[name], "_FillValue", np.nan))
            channel_cells[name] = {
                "buffer_nearest_cell_count": int(lvd_cells.size),
                "buffer_finite_nonfill_nearest_cells": int(np.count_nonzero(np.isfinite(values[lvd_cells]) & (values[lvd_cells] != fill))),
                "support_nearest_cell_count": int(support_cells_lvd.size),
                "support_finite_nonfill_nearest_cells": int(np.count_nonzero(np.isfinite(values[support_cells_lvd]) & (values[support_cells_lvd] != fill))),
                "mapped_unique_source_cells_from_162_cell_qc_support": int(len(source_cells)),
                "source_support_finite_nonfill": int(sum(np.isfinite(values[j * lat.shape[1] + i]) and values[j * lat.shape[1] + i] != fill for j, i in source_cells)),
            }
        diagnostics = {}
        for name in ("CLDFRA", "REFL_10CM"):
            var = wrf.variables[name]
            values = np.asarray(var[10], dtype=np.float64)
            finite = np.isfinite(values)
            record_time = b"".join(wrf.variables["Times"][10]).decode("ascii")
            diagnostics[name] = {
                "record_time": record_time,
                "units": getattr(var, "units", ""),
                "description": getattr(var, "description", ""),
                "finite_count": int(finite.sum()),
                "cell_count": int(values.size),
                "minimum": float(values[finite].min()),
                "maximum": float(values[finite].max()),
                "positive_cell_count": int(np.count_nonzero(values[finite] > 0)),
            }

        result = {
            "source_pins": pins,
            "static_grid_receipt": {"path": declared_static["path"], "absolute_path": str(STATIC), "sha256": declared_static["sha256"], "receipt_path": str(REPLAY_RECEIPT), "receipt_sha256": pins[str(REPLAY_RECEIPT)]},
            "pr104_station_mask_evidence": {
                "path": str(PR104_STATIONS),
                "sha256": pins[str(PR104_STATIONS)],
                "all_803": station_coverage["coverage_counts"]["all_803"],
                "valid_765": station_coverage["coverage_counts"]["valid_765"],
            },
            "horizontal_rows_binding": {
                "path": str(HORIZONTAL_ROWS),
                "sha256": pins[str(HORIZONTAL_ROWS)],
                "composition_input_binding_path": horizontal_binding["horizontal_rows_path"],
                "composition_input_binding_sha256": horizontal_binding["horizontal_rows_sha256"],
                "source_horizontal_cells": int(len(horizontal_source_cells)),
                "source_pressure_cells": 162,
                "same_source_cells_as_composition": True,
                "source_grid_registration": {
                    "projection": source_grid["projection"],
                    "startloc": source_grid["startloc"],
                    "earth_radius_km_f32": source_grid["earth_radius_km_f32"],
                    "source_grid_input_sha256": source_grid["input_sha256"],
                    "lvd_static_parameter_differences": source_grid_differences,
                    "difference_units": "native units; exact zero required; no fit",
                    "earth_radius_comparison": "LAPS static/LVD files do not expose a numeric counterpart; recorded as source-row metadata only",
                },
            },
            "source_code_refs": [
                {**source, "absolute_path": str((ROOT if source["root"] == "KLAPS50" else BAL) / source["path"])}
                for source in SOURCE_REFS
            ],
            "grid_registration": {
                "laps_static_and_lvd_shape_yx": list(lat.shape),
                "static_file_declared_role": "static_grid in tests/original_upstream_replay_20260816.json",
                "laps_lvd_projection_metadata": grid_metadata,
                "projection_parameter_differences_lvd_minus_static": grid_metadata_differences,
                "sw_corner_differences_static_latlon_minus_lvd_metadata": corner_difference,
                "comparison_tolerance": "1e-6 in native parameter units; no fit or adjustment",
                "static_to_lvd_registration": "receipt-bound static.nest7grid has same 235x283 lat/lon dimensions, Lambert projection parameters, and SW corner as LVD; its 2-D lat/lon arrays directly register the LVD raster",
                "closed_wrf_grid": str(WRF),
                "wrf_grid_shape_yx": list(wrf_lat.shape),
                "mask_to_lvd_mapping": "nearest LAPS static lat/lon cell center for each frozen WRF support/buffer column, spherical unit-vector distance",
                "buffer_nearest_laps_cells_unique": int(lvd_cells.size),
                "nearest_cell_distance_km": {"max": float(nearest_km.max()), "p95": float(np.percentile(nearest_km, 95)), "median": float(np.median(nearest_km))},
                "support_nearest_cell_distance_km": {"max": float(support_km.max()), "min": float(support_km.min())},
                "support_nearest_laps_cells_unique": int(support_cells_lvd.size),
                "support_level_cells": support_levels,
                "support_wrf_columns": int(support.sum()),
                "buffer_wrf_columns": int(buffer.sum()),
            },
            "channel_coverage_on_mapped_cells": channel_cells,
            "source_declared_channel_products": {
                "channel_1": {"slot": "visible", "LVD_products": ["SVS", "SVN", "ALB"]},
                "channel_2": {"slot": "3.9 um", "LVD_products": ["S3A", "S3C"]},
                "channel_3": {"slot": "6.7 um", "LVD_products": ["S4A", "S4C"]},
                "channel_4": {"slot": "11.2 um", "LVD_products": ["S8A", "S8W", "S8C"]},
                "channel_5": {"slot": "12.0 um", "LVD_products": ["SCA", "SCC"]},
                "calibration_limit": "legacy source labels only; channel response and independent calibration not established"
            },
            "source_composed_support": {
                "composed_qc_pressure_cells": 162,
                "unique_laps_source_grid_cells": int(len(source_cells)),
                "source_laps_grid_indices_zero_based_j_i": [list(cell) for cell in sorted(source_cells)],
                "source_mask_direct_lvd_raster_indexing": "same 235x283 LAPS source grid",
            },
            "operator_inventory": {
                "legacy_cloud_bt_operator": "insertsat.f compare_radiation empirically compares analyzed cloud to 11.2um BT and changes cloud fractions (4 K threshold; 0.05 cover step; up to 10 iterations)",
                "general_column_to_gk2a_channel_forward_radiative_transfer": "not found in the inspected C2 runtime path",
                "Cloud_BAL_satellite_bt_input": False,
                "Cloud_BAL_radar_reflectivity_input": True,
                "channel_labels": "legacy source-declared wavelength/channel labels, not independent sensor calibration or channel-response-function verification"
            },
            "closed_c2_host_diagnostics": {
                "evidence_scope": "PR103 closed historical C2 output at 13Z; this is not a new 14Z forecast evaluation",
                "diagnostics": diagnostics,
                "source_computation_binding": "The closed C2 output contains available finite nonzero diagnostics; actual selected-physics computation provenance remains unresolved because the selected C2 evidence does not bind the WRF source routine/formula. These outputs do not validate a satellite observation operator.",
            },
            "arrays": field_counts,
            "valid_time_utc": dt.datetime.fromtimestamp(float(lvd.variables["valtime"][0]), dt.timezone.utc).isoformat(),
            "reference_time_utc": dt.datetime.fromtimestamp(float(lvd.variables["reftime"][0]), dt.timezone.utc).isoformat(),
        }
    serialized = json.dumps(result, indent=2) + "\n"
    if str(args.output) == "-":
        print(serialized, end="")
    else:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(serialized)


if __name__ == "__main__":
    main()
