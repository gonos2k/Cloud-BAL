#!/usr/bin/env python3
"""Extract CP02 native first-hour state at canonical 5-mm lost-hit points."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import csv
import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914")
REPO = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50")
EVIDENCE = Path(__file__).resolve().parent
REPO_ROOT = EVIDENCE.parents[3]
PRECIP_EVIDENCE = REPO_ROOT / "docs/evidence/precip_hourly_20261027"
NPZ = PRECIP_EVIDENCE / "rn1_recovery/hour_13_arrays.npz"
ARMS = ("off", "hydro", "liquid")
FIELDS = ("QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP")
P0_PA, RD, CP = 100000.0, 287.05, 1004.5


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_csv_exclusive(path: Path, rows: list[dict]) -> None:
    with path.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def load_mapper():
    path = ROOT / "compare_six_hour_csi.py"
    pins = json.loads((PRECIP_EVIDENCE / "rn1_recovery/input_pins_after.json").read_text())
    expected = next((item["sha256"] for item in pins["inputs"] if item["path"] == str(path)), None)
    if expected is None or sha256(path) != expected:
        raise RuntimeError("archived comparison mapper hash differs from the pinned first-hour source")
    spec = importlib.util.spec_from_file_location("cp02_csi", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE / "current")
    args = parser.parse_args()
    outdir = args.output_dir.resolve()
    if outdir.exists():
        raise RuntimeError(f"refusing to overwrite existing output directory: {outdir}")
    mapper = load_mapper()
    source_manifest = json.loads((PRECIP_EVIDENCE / "rn1_recovery/manifest.json").read_text())
    expected_npz_hash = source_manifest["files"]["hour_13_arrays.npz"]
    if sha256(NPZ) != expected_npz_hash:
        raise RuntimeError("canonical hour_13_arrays.npz differs from its evidence manifest")
    pins_before = (PRECIP_EVIDENCE / "rn1_recovery/input_pins_before.json").read_bytes()
    pins_after = (PRECIP_EVIDENCE / "rn1_recovery/input_pins_after.json").read_bytes()
    if pins_before != pins_after:
        raise RuntimeError("first-hour source input pins changed during source staging")
    pinned_inputs = {item["path"]: item["sha256"] for item in json.loads(pins_after)["inputs"]}
    reference = json.loads((ROOT / "reference/inventory.json").read_text())
    mask, target_lat, target_lon = None, None, None
    reference, mask, target_lat, target_lon, provenance = mapper.load_reference(
        ROOT / "reference", REPO / "ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300"
    )
    provenance_records = []
    for name, path in provenance.items():
        actual = sha256(path)
        if pinned_inputs.get(str(path)) != actual:
            raise RuntimeError(f"{name} source differs from the first-hour input pins: {path}")
        provenance_records.append({"name": name, "path": str(path), "sha256": actual})
    arrays = np.load(NPZ)
    selector = (arrays["reference"] >= 5) & (arrays["OFF"] >= 5) & ((arrays["HYDRO"] < 5) | (arrays["LIQUID"] < 5))
    selected_positions = np.flatnonzero(selector)
    if selected_positions.size != 20:
        raise RuntimeError(f"expected canonical 20-point selector, got {selected_positions.size}")
    target_flat = arrays["flat_index_yx"][selected_positions].astype(int)
    y, x = np.divmod(target_flat, target_lat.shape[1])
    crop_x = reference["grid"]["crop_x_inclusive"]
    crop_y = reference["grid"]["crop_y_inclusive"]
    corner_y0, corner_y1 = crop_y[0] - 2, crop_y[1] - 1
    corner_x0, corner_x1 = crop_x[0] - 2, crop_x[1] - 1
    with Dataset(ROOT / "off/run/wrfout_d01_2026-08-16_13:00:00") as ds:
        source_grid_lat = np.asarray(ds["XLAT"][0], dtype=np.float64)
        source_grid_lon = np.asarray(ds["XLONG"][0], dtype=np.float64)
    source_lat = source_grid_lat[corner_y0:corner_y1+1, corner_x0:corner_x1+1]
    source_lon = source_grid_lon[corner_y0:corner_y1+1, corner_x0:corner_x1+1]
    if not np.array_equal(target_lat[y, x], arrays["latitude"][selected_positions]) or not np.array_equal(target_lon[y, x], arrays["longitude"][selected_positions]):
        raise RuntimeError("canonical NPZ target coordinates differ from source-bound ODAM crop")
    mapping = mapper.build_curvilinear_mapping(source_lat, source_lon, target_lat, target_lon, mask)
    if not np.all(mapping["valid"][y, x]):
        raise RuntimeError("lost-hit points include invalid native mapping")

    rows = []
    mapping_rows = []
    rain_rows = []
    precipitation_checks = []
    files = []
    for arm in ARMS:
        snapshots = {}
        for hour in (12, 13):
            path = ROOT / arm / "run" / f"wrfout_d01_2026-08-16_{hour:02d}:00:00"
            expected_time = datetime(2026, 8, 16, hour, tzinfo=timezone.utc)
            snapshot = mapper.read_wrf_snapshot(path, expected_time, reference)
            with Dataset(path) as ds:
                dims = (len(ds.dimensions["west_east"]), len(ds.dimensions["south_north"]), len(ds.dimensions["bottom_top"]))
                if dims != (234, 282, 39):
                    raise RuntimeError(f"unexpected WRF dimensions in {path}")
                required = ("T", "P", "PB", *FIELDS)
                missing = [name for name in required if name not in ds.variables]
                if missing:
                    raise RuntimeError(f"missing fields in {path}: {missing}")
                expected_dimensions = ("Time", "bottom_top", "south_north", "west_east")
                for name in ("T", "P", "PB", *FIELDS):
                    if ds[name].dimensions != expected_dimensions:
                        raise RuntimeError(f"unexpected {name} dimension names in {path}: {ds[name].dimensions}")
                    if ds[name].shape != (1, 39, 282, 234):
                        raise RuntimeError(f"unexpected {name} shape in {path}: {ds[name].shape}")
                    expected_units = "K" if name == "T" else "Pa" if name in ("P", "PB") else "kg kg-1"
                    units = str(getattr(ds[name], "units", "")).strip()
                    if units != expected_units:
                        raise RuntimeError(f"unexpected {name} units in {path}: {units!r}")
                for name in ("T", "P", "PB", *FIELDS):
                    field = np.ma.asarray(ds[name][0])
                    if np.ma.getmaskarray(field).any() or not np.isfinite(field.filled(np.nan)).all():
                        raise RuntimeError(f"nonfinite or masked {name} in {path}")
                if not np.array_equal(snapshot["lat"], source_grid_lat) or not np.array_equal(snapshot["lon"], source_grid_lon):
                    raise RuntimeError(f"native horizontal coordinates changed across histories: {path}")
                files.append({"arm": arm.upper(), "valid_time": expected_time.strftime("%Y-%m-%d_%H:%M:%S"), "path": str(path), "size": path.stat().st_size, "sha256": sha256(path)})
                snapshots[hour] = {name: np.asarray(ds[name][0], dtype=np.float64) for name in ("T", "P", "PB", *FIELDS)}
                total, valid = mapper.raw_total(snapshot)
                snapshots[hour]["rain"] = total
                snapshots[hour]["rain_valid"] = valid

        # Reproduce the canonical comparison's remap-then-difference precipitation operator.
        before_crop = snapshots[12]["rain"][corner_y0:corner_y1+1, corner_x0:corner_x1+1]
        after_crop = snapshots[13]["rain"][corner_y0:corner_y1+1, corner_x0:corner_x1+1]
        before_valid = snapshots[12]["rain_valid"][corner_y0:corner_y1+1, corner_x0:corner_x1+1]
        after_valid = snapshots[13]["rain_valid"][corner_y0:corner_y1+1, corner_x0:corner_x1+1]
        before, _ = mapper.remap_field(before_crop, before_valid, mapping)
        after, _ = mapper.remap_field(after_crop, after_valid, mapping)
        extracted_increment = after[y, x] - before[y, x]
        expected_increment = arrays[arm.upper()][selected_positions]
        exact_match = bool(np.array_equal(extracted_increment, expected_increment))
        max_error = float(np.max(np.abs(extracted_increment - expected_increment)))
        precipitation_checks.append({"arm": arm.upper(), "points": int(len(y)), "max_abs_error_mm": max_error, "exact_array_equal": exact_match, "pass": exact_match})
        if not exact_match:
            raise RuntimeError(f"hourly precipitation exact cross-check failed for {arm}: {max_error} mm")
        for point, (row, col) in enumerate(zip(y, x)):
            rain_rows.append({"arm": arm.upper(), "losthit_rank": point + 1, "canonical_mask_vector_position": int(selected_positions[point]), "target_flat_index_yx": int(target_flat[point]),
                              "canonical_hourly_increment_mm": float(expected_increment[point]),
                              "remapped_12z_cumulative_mm": float(before[row, col]), "remapped_13z_cumulative_mm": float(after[row, col]),
                              "recomputed_increment_mm": float(extracted_increment[point]),
                              "difference_mm": float(extracted_increment[point] - expected_increment[point])})

        for point, (row, col) in enumerate(zip(y, x)):
            i0, j0 = int(mapping["i0"][row, col]), int(mapping["j0"][row, col])
            u, v = float(mapping["u"][row, col]), float(mapping["v"][row, col])
            weights = np.array(((1-u)*(1-v), u*(1-v), (1-u)*v, u*v))
            stencil = ((j0+corner_y0, i0+corner_x0), (j0+corner_y0, i0+corner_x0+1),
                       (j0+corner_y0+1, i0+corner_x0), (j0+corner_y0+1, i0+corner_x0+1))
            if arm == "off":
                for corner_id, ((jj, ii), weight) in enumerate(zip(stencil, weights)):
                    mapping_rows.append({"losthit_rank": point + 1, "canonical_mask_vector_position": int(selected_positions[point]), "target_flat_index_yx": int(target_flat[point]),
                                         "target_y": int(row), "target_x": int(col), "lat": float(target_lat[row, col]), "lon": float(target_lon[row, col]),
                                         "corner": corner_id, "native_j": jj, "native_i": ii, "weight": float(weight), "u": u, "v": v})
            for hour in (12, 13):
                state = snapshots[hour]
                for k in range(39):
                    vals = {}
                    for name in ("T", "P", "PB", *FIELDS):
                        vals[name] = float(weights @ np.array([state[name][k, jj, ii] for jj, ii in stencil]))
                    # Diagnostic thermodynamic transformation at each source corner, then bilinear interpolation.
                    corner_temp = []
                    for jj, ii in stencil:
                        p = state["P"][k, jj, ii] + state["PB"][k, jj, ii]
                        if not np.isfinite(p) or p <= 0.0:
                            raise RuntimeError(f"invalid total pressure at {arm} {hour}Z point {point} level {k}")
                        corner_temp.append((state["T"][k, jj, ii] + 300.0) * (p / P0_PA) ** (RD / CP))
                    if not np.isfinite(corner_temp).all():
                        raise RuntimeError(f"nonfinite diagnostic temperature at {arm} {hour}Z point {point} level {k}")
                    rows.append({
                        "arm": arm.upper(), "valid_time_utc": f"2026-08-16T{hour:02d}:00:00Z", "losthit_rank": point + 1,
                        "canonical_mask_vector_position": int(selected_positions[point]),
                        "target_flat_index_yx": int(target_flat[point]), "target_y": int(row), "target_x": int(col),
                        "lat": float(target_lat[row, col]), "lon": float(target_lon[row, col]),
                        "native_j0": j0+corner_y0, "native_i0": i0+corner_x0, "bilinear_u": u, "bilinear_v": v, "bottom_top_k": k,
                        "T_theta_perturbation_K": vals["T"], "P_perturbation_Pa": vals["P"], "PB_base_pressure_Pa": vals["PB"],
                        "T_K_diagnostic": float(weights @ np.asarray(corner_temp)), "P_Pa": vals["P"]+vals["PB"],
                        **{f"{name}_kgkg": vals[name] for name in FIELDS},
                    })

    if not all(item["pass"] for item in precipitation_checks):
        raise RuntimeError("one or more precipitation checks failed")
    archived_identities = json.loads((ROOT / "RESULT.json").read_text())["sources"]["wrfout"]
    expected_hashes = {
        (arm.upper(), Path(item["path"]).name): item["sha256"]
        for arm, arm_records in archived_identities.items() for item in arm_records
        if "_12:00:00" in item["path"] or "_13:00:00" in item["path"]
    }
    for record in files:
        if expected_hashes.get((record["arm"], Path(record["path"]).name)) != record["sha256"]:
            raise RuntimeError(f"history SHA256 does not match archived RESULT.json: {record['path']}")
    if outdir.exists():
        raise RuntimeError(f"refusing to overwrite existing output directory: {outdir}")
    stage = outdir.with_name(f".{outdir.name}.tmp")
    if stage.exists():
        raise RuntimeError(f"refusing to overwrite existing staging directory: {stage}")
    stage.mkdir(parents=True)
    csv_path = stage / "losthit_native_profiles.csv"
    mapping_path = stage / "losthit_mapping.csv"
    rain_path = stage / "precipitation_crosscheck.csv"
    figure_path = stage / "losthit_mean_profiles.png"
    receipt_path = stage / "extraction_receipt.json"
    final_csv, final_mapping, final_rain, final_figure, final_receipt = (outdir / p.name for p in (csv_path, mapping_path, rain_path, figure_path, receipt_path))
    try:
        write_csv_exclusive(csv_path, rows)
        write_csv_exclusive(mapping_path, mapping_rows)
        write_csv_exclusive(rain_path, rain_rows)
        figure, axes = plt.subplots(1, 4, figsize=(15, 7), sharey=True, constrained_layout=True)
        plot_fields = (("T_K_diagnostic", "Temperature (K)", 1.0), ("QVAPOR_kgkg", "QVAPOR (g/kg)", 1000.0),
                       ("QCLOUD_kgkg", "QCLOUD (g/kg)", 1000.0), ("QRAIN_kgkg", "QRAIN (g/kg)", 1000.0))
        colors = {"OFF": "#333333", "HYDRO": "#1464a5", "LIQUID": "#b23a48"}
        for axis, (field, title, scale) in zip(axes, plot_fields):
            for arm in ARMS:
                for hour, linestyle in ((12, "-"), (13, "--")):
                    subset = [r for r in rows if r["arm"] == arm.upper() and r["valid_time_utc"].endswith(f"T{hour:02d}:00:00Z")]
                    grouped = [[r for r in subset if r["bottom_top_k"] == k] for k in range(39)]
                    profile = np.array([np.mean([r[field] for r in group]) for group in grouped])
                    pprofile = np.array([np.mean([r["P_Pa"] for r in group]) for group in grouped])
                    axis.plot(profile * scale, pprofile / 100.0, color=colors[arm.upper()], linestyle=linestyle,
                              label=f"{arm.upper()} {hour:02d}Z")
            axis.set_title(title); axis.set_xlabel(title.split(" (")[0]); axis.grid(True, alpha=0.25)
            axis.xaxis.set_major_locator(MaxNLocator(nbins=4))
        axes[0].set_ylabel("Mean pressure over 20 points (hPa; unweighted)")
        axes[0].invert_yaxis(); axes[-1].legend(fontsize=7, ncol=2, loc="best")
        figure.suptitle("CP02 first hour at 20 canonical lost-hit points\nEqual-weight point means at each native mass level; not column-mass weighted")
        with figure_path.open("xb") as figure_stream:
            figure.savefig(figure_stream, format="png", dpi=170)
        plt.close(figure)
        receipt = {
            "status": "PASS_SCOPED_NATIVE_STATE_EXTRACTION",
            "selector": "canonical hour_13_arrays.npz: reference>=5 & OFF>=5 & ((HYDRO<5)|(LIQUID<5)); exactly 20 points",
            "selector_source": {"path": str(NPZ), "sha256": sha256(NPZ), "manifest_sha256": expected_npz_hash},
            "mapping": "compare_six_hour_csi.py build_curvilinear_mapping; ODAM 253x149; native WRF 282x234; existing one-cell-halo; bilinear, no extrapolation",
            "mapping_residual_max_deg": mapping["residual_max_deg"], "mapping_valid_points": int(len(y)),
            "history_records": files, "precipitation_crosscheck": precipitation_checks,
            "input_pin_preservation": {"before_sha256": sha256(PRECIP_EVIDENCE / "rn1_recovery/input_pins_before.json"), "after_sha256": sha256(PRECIP_EVIDENCE / "rn1_recovery/input_pins_after.json"), "identical": True},
            "source_provenance": provenance_records,
            "thermodynamics": {"temperature": "derived diagnostic, per-corner from theta=T+300 K and P+PB, then bilinear; p0=100000 Pa, Rd=287.05, Cp=1004.5", "not_native_temperature_output": True},
            "fields": ["T_theta_perturbation_K", "P_perturbation_Pa", "PB_base_pressure_Pa", "T_K_diagnostic", "P_Pa", *[f"{name}_kgkg" for name in FIELDS]],
            "limitations": ["Only saved state and accumulated precipitation fields; no process tendency, conversion budget, or native microphysics rate diagnostics captured.", "OFF/HYDRO/LIQUID differ in several initialization fields and share initial W; this is paired whole-initialization response, not isolated thermodynamic causality.", "WRF T is perturbation potential temperature; temperature transformation is explicitly labeled diagnostic and is not claimed to duplicate the model thermodynamic routine exactly."],
            "output_csv": str(final_csv), "output_csv_sha256": sha256(csv_path), "rows": len(rows),
            "mapping_csv": str(final_mapping), "mapping_csv_sha256": sha256(mapping_path),
            "precipitation_crosscheck_csv": str(final_rain), "precipitation_crosscheck_csv_sha256": sha256(rain_path),
            "figure": str(final_figure), "figure_sha256": sha256(figure_path),
            "source_result": {"path": str(ROOT / "RESULT.json"), "sha256": sha256(ROOT / "RESULT.json")},
            "source_mapping_code": {"path": str(ROOT / "compare_six_hour_csi.py"), "sha256": sha256(ROOT / "compare_six_hour_csi.py")},
        }
        with receipt_path.open("x") as f:
            f.write(json.dumps(receipt, indent=2)+"\n")
        stage.rename(outdir)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    print(json.dumps({"csv": str(final_csv), "rows": len(rows), "map_error_deg": mapping["residual_max_deg"], "checks": precipitation_checks}, indent=2))

if __name__ == "__main__":
    main()
