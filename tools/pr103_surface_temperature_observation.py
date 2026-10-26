#!/usr/bin/env python3
"""Compare 13Z LSO air temperature with source-mapped WRF T2 fields."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset


ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee")
REPO = Path(__file__).resolve().parents[1]
LSO = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/00/lapsprd/lso/262281300.lso")
LSO_SHA256 = "b70ee7a758bf2d27b938ff346e3fc4c40c4c79be22f746d0f0cb0cf2ce03b9fd"
LSO_BADFLAG_F = -99.9
MISSING_FLAG = 1.0e37
FIVEARM = REPO / "docs/evidence/pr102_execution_20261025/fivearm/fivearm_history_readback.json"
FIVEARM_SHA256 = "d10f124bed615f0546594266971db263d6ba7db48ae3ee210e985f4c8c7db6b2"
UPSTREAM_BINDING = REPO / "tests/original_upstream_replay_20260816.json"
SOURCE_PINS = {
    "src/lib/gridconv.f": "bb48cb301f3fb612bcc0a4944f1d649d2aa16e6cc34d18d22caa82aa17c56cff",
    "src/lib/modules/module_map_utils.f90": "b9fdabaa25e928f1db2f0e35f868e2c0ef92f9093c1de68ab9ced05238662d57",
    "src/lib/modules/module_wrf_netcdf.f90": "45d4d35f290e7db564b35bb422cb5f48d1c186f8de3e13d6f7f6d44e4ab5c9a0",
    "src/lib/bgdata/wrf/module_wrf_lga.f90": "efb48b0d83b5c3038928043a2ca36e06de25baf5d775a6587444b36757b2fa6c",
    "src/lib/read_surface_obs.f": "ba6ae0ed4547ed90a2f7200bcfb36c1cd4f295cc70539bb03740fe89c80629ad",
    "src/include/lso_formats.inc": "956becb489dcb7aee43857aef788c15e0fc0eec0303a179d801051ed71e3f96a",
    "src/include/surface_obs.inc": "3edca9ceb40699ae14c71bce836232747ef141290e44decd025dead160028ebe",
}
WRF_LLXY = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS/wrf_v4_8_kfarms_work/WRF-v4.8.0/share/module_llxy.F")
WRF_LLXY_SHA256 = "0c777e66ffbb0602479cadcc0ab484769a140c4cb2b3e9a8f757597086f0c76b"
FINITE_HELPER = REPO / "tools/pr87_native_history.py"
FINITE_HELPER_SHA256 = "d6feb0e5fd5d53a60d7256a7b3c4faaa3c7f2488b799af25278aec7529c28a71"
_FINITE_SPEC = importlib.util.spec_from_file_location("pr87_native_history", FINITE_HELPER)
_FINITE_MODULE = importlib.util.module_from_spec(_FINITE_SPEC)
sys.modules[_FINITE_SPEC.name] = _FINITE_MODULE
_FINITE_SPEC.loader.exec_module(_FINITE_MODULE)
ARMS = {
    "O": (ROOT / "pr99_c2_matched640_20261022/OFF/run/wrfout_d01_2026-08-16_13:00:00", "e9a6ec6ca8af2f99b3ee4a9fedab13b42a4997a2ab6f68ac08e897117766470f", "c4174b0363dc3b6eb5117ae1e011e9bee0f4f70d090036c607331fac7b0d1f8d"),
    "H": (ROOT / "pr99_c2_matched640_20261022/HYDRO/run/wrfout_d01_2026-08-16_13:00:00", "4e8e79eff2ceffc699fc59d8bb382b7936a6bd276068746c45bb4b072be35d84", "1440db5a0178af11ac4d92854b3284cc35cb5a74e5e6f6a14cc59dcac3a00a64"),
    "C": (ROOT / "pr99_c2_matched640_20261022/COUPLED/run/wrfout_d01_2026-08-16_13:00:00", "e32992f7539a3b24d2eec4f06d5d7455accb97fa0de3ef50d415f9ac749670ba", "0a7e1c3bcce58dea8433e9bffa615395d923cd05377c5068469af5dba29759cb"),
    "P": (ROOT / "pr101_projected_c2_640_20261023/run/wrfout_d01_2026-08-16_13:00:00", "0a19bcc0ff51f8f4287a4fb2d4e6ee02de6c49a93d429a7f9f4bf26abdd8e96a", "d0a7920687aecbef15b91f2641638918f00beea67de5fb2af6e5597175bc5da2"),
    "N": (ROOT / "pr102_native_structure640_20261025/STRUCTURED640_RUN/run/wrfout_d01_2026-08-16_13:00:00", "fd18da17a47abeb862ac088f4ea185d34583de65d88245737b124065aa52165a", "313295e9cbf9e30a12a437c501bf3db2cf25c0e6762ec5d51c31d54ba311d4d6"),
}
# Pinned WRF-v4.8.0 share/module_llxy.F defines EARTH_RADIUS_M=6370000.
RE = 6_370_000.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_lso(path: Path) -> tuple[list[dict], dict]:
    lines = path.read_text(errors="strict").splitlines()
    header = lines[0].split()
    declared = int(header[-1])
    records = []
    i = 1
    while i < len(lines):
        meta = lines[i].split()
        temp = lines[i + 2].split()
        kkk = int(lines[i + 7].split()[0])
        if len(meta) < 7 or len(temp) < 2:
            raise ValueError(f"malformed LSO record at line {i + 1}")
        records.append({
            "station_id": meta[0], "wmo_id": meta[1], "provider": meta[2],
            "lat": float(meta[3]), "lon": float(meta[4]), "elev_m": float(meta[5]),
            "time_hhmm": int(meta[6]), "temperature_f": float(temp[0]),
            "temperature_expected_accuracy_f": float(temp[1]),
        })
        i += 8 + max(kkk, 0)
    if i != len(lines) or len(records) != declared:
        raise ValueError(f"LSO record count mismatch: parsed={len(records)} declared={declared}")
    return records, {"declared_records": declared, "parsed_records": len(records)}


def lc_grid_ij(lat: float, lon: float, *, lat1: float, lon1: float,
               stdlon: float, truelat1: float, truelat2: float,
               dx: float, dy: float) -> tuple[float, float]:
    """Double-precision port of WRF-v4.8.0 share/module_llxy.F set_lc/llij_lc."""
    if dx != dy:
        raise ValueError("source WRF/LAPS mapping requires square grid spacing")
    hemi = 1.0 if truelat1 >= 0 else -1.0
    t1 = math.radians(truelat1)
    t2 = math.radians(truelat2)
    if abs(truelat1 - truelat2) <= 0.1:
        cone = math.sin(abs(t1))
    else:
        a, b = sorted((abs(t1), abs(t2)))
        cone = (math.log(math.cos(a)) - math.log(math.cos(b))) / (
            math.log(math.tan((math.pi / 2 - a) / 2))
            - math.log(math.tan((math.pi / 2 - b) / 2))
        )
    rebydx = RE / dx
    rsw = rebydx * math.cos(t1) / cone * (
        math.tan((math.pi / 2 - hemi * math.radians(lat1)) / 2)
        / math.tan((math.pi / 2 - hemi * t1) / 2)
    ) ** cone
    dlon1 = (lon1 - stdlon + 180) % 360 - 180
    polei = 1 - hemi * rsw * math.sin(cone * math.radians(dlon1))
    polej = 1 + rsw * math.cos(cone * math.radians(dlon1))
    dlon = (lon - stdlon + 180) % 360 - 180
    rm = rebydx * math.cos(t1) / cone * (
        math.tan((math.pi / 2 - hemi * math.radians(lat)) / 2)
        / math.tan((math.pi / 2 - hemi * t1) / 2)
    ) ** cone
    arg = cone * math.radians(dlon)
    i = polei + hemi * rm * math.sin(arg)
    j = polej - rm * math.cos(arg)
    if hemi == -1:
        i, j = 2 - i, 2 - j
    return i, j


def binom4(v: tuple[float, float, float, float], x: float) -> float:
    """Same 4-point overlapping quadratic rule as gridconv.f:binom."""
    x1, x2, x3, x4 = 1.0, 2.0, 3.0, 4.0
    y1, y2, y3, y4 = v
    if y2 >= 1.0e19 or y3 >= 1.0e19:
        return MISSING_FLAG
    wt1 = (x - x3) / (x2 - x3)
    wt2 = 1.0 - wt1
    if y4 < 1.0e19:
        yz22 = wt1 * (x - x4) / (x2 - x4)
        yz23 = wt2 * (x - x4) / (x3 - x4)
        yz24 = (x - x2) * (x - x3) / ((x4 - x2) * (x4 - x3))
    else:
        yz22, yz23, yz24 = wt1, wt2, 0.0
    if y1 < 1.0e19:
        yz11 = (x - x2) * (x - x3) / ((x1 - x2) * (x1 - x3))
        yz12 = wt1 * (x - x1) / (x2 - x1)
        yz13 = wt2 * (x - x1) / (x3 - x1)
    else:
        yz11, yz12, yz13 = 0.0, wt1, wt2
    if yz11 == 0.0 and yz24 == 0.0:
        return wt1 * y2 + wt2 * y3
    return wt1 * (yz11 * y1 + yz12 * y2 + yz13 * y3) + wt2 * (
        yz22 * y2 + yz23 * y3 + yz24 * y4
    )


def fahrenheit_to_celsius(value_f: float) -> float:
    return (value_f - 32.0) * (5.0 / 9.0)


def kelvin_to_celsius(value_k: float) -> float:
    return value_k - 273.15


def gdtost(field: np.ndarray, i: float, j: float) -> tuple[float | None, str | None]:
    """Port gridconv.f gdtost/binom for nonwrapped fields, with NaN masking."""
    ny, nx = field.shape
    if i < 1.0 or j < 1.0 or i > nx or j > ny:
        return None, "outside_or_incomplete_4x4_stencil"

    def point(x_index: int, y_index: int) -> float:
        if x_index < 0 or x_index >= nx or y_index < 0 or y_index >= ny:
            return MISSING_FLAG
        value = float(field[y_index, x_index])
        return value if math.isfinite(value) else MISSING_FLAG

    ix1 = int(i) - 1
    iy1 = int(j) - 1
    if i < 1.0:
        ix1 = 1
    if j < 1.0:
        iy1 = 1
    scr = []
    for iii in range(ix1, ix1 + 4):
        row = tuple(point(iii - 1, jjj - 1) for jjj in range(iy1, iy1 + 4))
        yy = j - (iy1 - 1)
        scr.append(row[1] if yy == 2.0 else binom4(row, yy))
    xx = i - (ix1 - 1)
    value = scr[1] if xx == 2.0 else binom4(tuple(scr), xx)
    if not math.isfinite(value) or value >= 1.0e19:
        return None, "invalid_model_stencil"
    return value, None


def model_metadata(path: Path) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray]:
    with Dataset(path) as nc:
        nc.set_auto_mask(False)
        model_time = b"".join(nc.variables["Times"][0]).decode("ascii")
        if model_time != "2026-08-16_13:00:00":
            raise ValueError(f"unexpected model time in {path}")
        attrs = {name: float(getattr(nc, name)) for name in ("TRUELAT1", "TRUELAT2", "STAND_LON", "DX", "DY")}
        # Archived history exposes WRF's mass-grid XLAT/XLONG; LAT_LL_T and
        # LON_LL_T expected by the current LAPS reader are absent here.
        lat_grid = _FINITE_MODULE._finite(nc, "XLAT", 0)
        lon_grid = _FINITE_MODULE._finite(nc, "XLONG", 0)
        attrs["lat1"] = float(lat_grid[0, 0])
        attrs["lon1"] = float(lon_grid[0, 0])
        t2var = nc.variables["T2"]
        if getattr(t2var, "units", "") not in ("K", "kelvin", "Kelvin"):
            raise ValueError(f"unexpected T2 units in {path}: {getattr(t2var, 'units', None)}")
        t2 = _FINITE_MODULE._finite(nc, "T2", 0)
    if t2.ndim != 2 or lat_grid.shape != t2.shape or lon_grid.shape != t2.shape:
        raise ValueError(f"T2/XLAT/XLONG shape mismatch in {path}")
    if np.all(t2 == 0.0):
        raise ValueError(f"T2 is all-zero in {path}; likely uncomputed history diagnostic")
    return attrs, t2, lat_grid, lon_grid


def grid_mapping_residuals(lat_grid: np.ndarray, lon_grid: np.ndarray,
                           projection: dict) -> dict:
    """Report every archived mass-grid point's LC inverse-mapping residual."""
    if lat_grid.shape != lon_grid.shape:
        raise ValueError("XLAT/XLONG shape mismatch")
    ny, nx = lat_grid.shape
    di = np.empty((ny, nx), dtype=np.float64)
    dj = np.empty((ny, nx), dtype=np.float64)
    for y in range(ny):
        for x in range(nx):
            i, j = lc_grid_ij(float(lat_grid[y, x]), float(lon_grid[y, x]), **projection)
            di[y, x], dj[y, x] = i - (x + 1), j - (y + 1)
    return {
        "grid_points": int(nx * ny),
        "i_delta_grid_units": {"rms": float(np.sqrt(np.mean(di * di))), "max_abs": float(np.max(np.abs(di)))},
        "j_delta_grid_units": {"rms": float(np.sqrt(np.mean(dj * dj))), "max_abs": float(np.max(np.abs(dj)))},
        "meaning": "raw map output minus 1-based XLAT/XLONG indices; descriptive only, no fitted tolerance",
    }


def compare(observations: list[dict], model: np.ndarray, projection: dict) -> tuple[list[dict], dict]:
    rows, exclusions = [], {}
    for obs in observations:
        if obs["time_hhmm"] != 1300:
            reason = "non_1300_report_time"
        elif obs["temperature_f"] == LSO_BADFLAG_F:
            reason = "missing_lso_temperature_sentinel"
        else:
            i, j = lc_grid_ij(obs["lat"], obs["lon"], **projection)
            t2_k, reason = gdtost(model, i, j)
        if reason:
            exclusions[reason] = exclusions.get(reason, 0) + 1
            continue
        obs_c = fahrenheit_to_celsius(obs["temperature_f"])
        model_c = kelvin_to_celsius(t2_k)
        rows.append({**{k: obs[k] for k in ("station_id", "wmo_id", "provider", "lat", "lon", "elev_m", "time_hhmm", "temperature_expected_accuracy_f")},
                     "observation_c": obs_c, "model_t2_k": t2_k, "model_t2_c": model_c,
                     "signed_model_minus_observation_c": model_c - obs_c})
    residuals = np.asarray([r["signed_model_minus_observation_c"] for r in rows], dtype=float)
    metrics = {
        "matched_count": int(residuals.size), "excluded_counts_by_reason": exclusions,
        "signed_bias_c": float(residuals.mean()) if residuals.size else None,
        "mae_c": float(np.abs(residuals).mean()) if residuals.size else None,
        "rmse_c": float(np.sqrt(np.square(residuals).mean())) if residuals.size else None,
        "max_abs_residual_c": float(np.abs(residuals).max()) if residuals.size else None,
    }
    return rows, metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sha256(FIVEARM) != FIVEARM_SHA256:
        raise SystemExit("fivearm history readback does not match its recorded source pin")
    for relative, expected in SOURCE_PINS.items():
        source_path = ROOT / "KLAPS50/klaps-v5.0_" / relative
        if sha256(source_path) != expected:
            raise SystemExit(f"authoritative source hash mismatch: {source_path}")
    if sha256(WRF_LLXY) != WRF_LLXY_SHA256:
        raise SystemExit("pinned WRF projection source hash mismatch")
    if sha256(FINITE_HELPER) != FINITE_HELPER_SHA256:
        raise SystemExit("pinned PR87 finite-history helper hash mismatch")
    if sha256(LSO) != LSO_SHA256:
        raise SystemExit("13Z LSO hash does not match original_upstream_replay pin")
    upstream = json.loads(UPSTREAM_BINDING.read_text())
    if upstream["surface_observations"]["20260816T130000Z"]["sha256"] != LSO_SHA256:
        raise SystemExit("13Z LSO hash is not present in the original upstream binding")
    fivearm = json.loads(FIVEARM.read_text())
    observations, lso_counts = read_lso(LSO)
    base_attrs = None
    base_lat_grid = base_lon_grid = None
    base_t2 = None
    geometry_audit = None
    arm_results = {}
    for arm, (path, expected_sha, receipt_sha) in ARMS.items():
        if fivearm["controls"][{"O": "OFF", "H": "HYDRO", "C": "COUPLED", "P": "P", "N": "STRUCTURED"}[arm]]["receipt_sha256"] != receipt_sha:
            raise SystemExit(f"{arm} receipt hash does not match fivearm readback")
        if fivearm["artifact_pins_before_after"][str(path)] != expected_sha:
            raise SystemExit(f"{arm} T0 history hash does not match fivearm readback")
        if sha256(path) != expected_sha:
            raise SystemExit(f"{arm} history hash does not match fivearm receipt pin: {path}")
        attrs, field, lat_grid, lon_grid = model_metadata(path)
        if base_attrs is None:
            base_attrs, base_t2 = attrs, field.copy()
        elif attrs != base_attrs:
            raise SystemExit(f"{arm} WRF projection differs from O mass-grid geometry")
        projection = {
            "lat1": attrs["lat1"], "lon1": attrs["lon1"],
            "stdlon": attrs["STAND_LON"], "truelat1": attrs["TRUELAT1"],
            "truelat2": attrs["TRUELAT2"], "dx": attrs["DX"], "dy": attrs["DY"],
        }
        if base_lat_grid is None:
            base_lat_grid, base_lon_grid = lat_grid, lon_grid
            geometry_audit = grid_mapping_residuals(lat_grid, lon_grid, projection)
        elif not (np.array_equal(lat_grid, base_lat_grid) and np.array_equal(lon_grid, base_lon_grid)):
            raise SystemExit(f"{arm} XLAT/XLONG grid differs from O mass-grid geometry")
        rows, metrics = compare(observations, field, projection)
        arm_results[arm] = {
            "history_path": str(path), "history_sha256": expected_sha,
            "closed_run_receipt_sha256": receipt_sha,
            "history_time_utc": "2026-08-16T13:00:00Z", "field": "T2",
            "field_units": "K", "field_shape_yx": list(field.shape),
            "field_min_k": float(field.min()), "field_max_k": float(field.max()),
            "t2_same_as_O_bitwise": bool(np.array_equal(field, base_t2)),
            "t2_changed_cells_vs_O": int(np.count_nonzero(field != base_t2)),
            "t2_max_abs_delta_k_vs_O": float(np.max(np.abs(field - base_t2))),
            "history_value_validation": {
                "finite_and_declared_fill_checked": "pr87_native_history._finite with set_auto_mask(False)",
                "all_zero_diagnostic_check": bool(np.all(field == 0.0)),
                "all_zero_check_is": "uncomputed-diagnostic guard only, not physical acceptance",
            },
            "metrics": metrics,
        }
        if arm == "O":
            reference_rows = rows
    payload = {
        "schema": "pr103_surface_temperature_input_consistency_v1",
        "scope": "same-cycle input consistency only; not independent forecast skill",
        "observation": {"path": str(LSO), "sha256": LSO_SHA256, "valid_time_utc": "2026-08-16T13:00:00Z",
                        "units": "degF", "reader_source": "klaps-v5.0_/src/lib/read_surface_obs.f + src/include/lso_formats.inc",
                        "qc": "no additional QC applied; QC authority/source flags not included in this summary"},
        "observation_file_counts": lso_counts,
        "observation_missing_temperature": {"sentinel_degF": LSO_BADFLAG_F,
                                             "source": "klaps-v5.0_/src/include/surface_obs.inc:badflag"},
        "operator": {"projection_source": "WRF-v4.8.0/share/module_llxy.F; pinned WRF Lambert geometry with XLAT/XLONG mass-grid anchor",
                     "station_interpolation_source": "klaps-v5.0_/src/lib/gridconv.f:gdtost + binom",
                     "operator_label": "source-faithful diagnostic adapter; not a registered assimilation H",
                     "operator": "WRF Lambert mass-grid latlon_to_ij then legacy overlapping-quadratics gdtost; out-of-domain points excluded"},
        "geometry_audit": {"anchor_source": "XLAT[0,0,0]/XLONG[0,0,0] because archived history lacks LAT_LL_T/LON_LL_T expected by get_wrf2_map",
                           "mass_grid_shape_yx": list(base_lat_grid.shape), **geometry_audit},
        "residual": "H(X)-Y = WRF T2 (K -> degC) minus station air temperature (degF -> degC)",
        "arms": arm_results,
        "matched_station_records": reference_rows,
        "lineage_pins": {
            "fivearm_history_readback": {"path": str(FIVEARM), "sha256": FIVEARM_SHA256},
            "original_upstream_replay": {"path": str(UPSTREAM_BINDING), "sha256": sha256(UPSTREAM_BINDING)},
            "source_files": SOURCE_PINS,
            "wrf_projection_source": {"path": str(WRF_LLXY), "sha256": WRF_LLXY_SHA256,
                                      "earth_radius_m": RE},
            "finite_history_helper": {"path": str(FINITE_HELPER), "sha256": FINITE_HELPER_SHA256},
        },
        "limits": ["LSO may have contributed to same-cycle analysis/input; no independent-skill claim.",
                   "Raw residuals only; no uncertainty or covariance model.",
                   "Missing QC authority is retained as a limitation; no quality cutoff invented."],
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
