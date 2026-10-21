#!/usr/bin/env python3
"""Receipt-bound frozen-C4 water inventories and available 600-second budget."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
from typing import Any

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HISTORY = Path(__file__).with_name("pr87_native_history.py")
_SPEC = importlib.util.spec_from_file_location("pr87_native_history", HISTORY)
native = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(native)
_TRACE_SPEC = importlib.util.spec_from_file_location("native_kdm6_trace", ROOT / "tools/native_kdm6_trace.py")
kdm6_trace = importlib.util.module_from_spec(_TRACE_SPEC)
assert _TRACE_SPEC.loader is not None
_TRACE_SPEC.loader.exec_module(kdm6_trace)

RUN_ROOTS = {
    "OFF": Path("/var/tmp/pr93_OFF_600s_c4_bound_20261020"),
    "COUPLED": Path("/var/tmp/pr93_COUPLED_600s_c4_bound_20261020"),
}
WATER_FIELDS = dict(native.WATER)
PRECIP_FIELDS = ("RAINC", "RAINNC")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _receipt_bound_history(root: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    receipt_path = root / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0:
        raise ValueError(f"{root} is not a completed successful run")
    bound = {Path(row["path"]).name: row["sha256"]
             for row in receipt.get("generated_files", []) if "path" in row and "sha256" in row}
    history_name = "wrfout_d01_2026-08-16_13:00:00"
    history_path = root / "run" / history_name
    expected = bound.get(history_name)
    if not expected or sha256(history_path) != expected:
        raise ValueError(f"C4 history is not receipt-bound: {history_path}")
    times, grid = native._file_index([history_path])
    window = native._receipt_window(receipt_path, [history_path], sorted(times),
                                    endpoint_seconds=600, interval_seconds=60,
                                    allow_incomplete=False)
    if len(times) != 11 or window["observed_endpoint_seconds"] != 600:
        raise ValueError("expected exact 0..600 second history coverage")
    return history_path, receipt, {"receipt": {"path": str(receipt_path), "sha256": sha256(receipt_path)},
                                   "history": {"path": str(history_path), "sha256": expected},
                                   "window": window, "grid": grid}


def _stats(cell_values: np.ndarray) -> dict[str, float]:
    column = np.sum(cell_values, axis=0, dtype=np.float64)
    return {"signed_total_kg": float(np.sum(cell_values, dtype=np.float64)),
            "L1_kg": float(np.sum(np.abs(cell_values), dtype=np.float64)),
            "max_abs_cell_kg": float(np.max(np.abs(cell_values))),
            "max_abs_column_kg": float(np.max(np.abs(column))),
            "column_L1_kg": float(np.sum(np.abs(column), dtype=np.float64))}


def column_map_stats(values: np.ndarray, latitude: np.ndarray,
                     longitude: np.ndarray) -> dict[str, Any]:
    if values.ndim != 2 or latitude.shape != values.shape or longitude.shape != values.shape:
        raise ValueError("column values and latitude/longitude must share a 2D native grid")
    if not np.isfinite(values).all() or not np.isfinite(latitude).all() or not np.isfinite(longitude).all():
        raise ValueError("column diagnostics and coordinates must be finite")
    absolute = np.abs(values)
    flat = int(np.argmax(absolute))
    j, i = np.unravel_index(flat, values.shape)
    return {"signed_total_kg": float(np.sum(values, dtype=np.float64)),
            "L1_kg": float(np.sum(absolute, dtype=np.float64)),
            "max_abs_kg": float(absolute[j, i]),
            "signed_at_max_abs_kg": float(values[j, i]),
            "abs_quantiles_kg": {f"p{q}": float(np.percentile(absolute, q))
                                 for q in (50, 90, 95, 99)},
            "max_location": {"j_zero_based": int(j), "i_zero_based": int(i),
                             "latitude_deg": float(latitude[j, i]),
                             "longitude_deg": float(longitude[j, i])}}


def export_column_diagnostics(column_dir: Path, plot_path: Path,
                              maps: dict[str, dict[str, np.ndarray]]) -> dict[str, Any]:
    """Write private per-cell columns and a compact paired-arm map; never overwrite."""
    if plot_path.exists():
        raise FileExistsError(plot_path)
    column_dir.mkdir(parents=True, exist_ok=False)
    column_dir.chmod(0o700)
    arrays: dict[str, np.ndarray] = {}
    stats = {}
    for arm, fields in maps.items():
        for name in ("inventory_change_kg", "precipitation_outflow_kg",
                     "available_inventory_change_plus_precipitation_kg", "latitude_deg",
                     "longitude_deg", "cell_area_m2"):
            key = f"{arm}_{name}"
            arrays[key] = np.asarray(fields[name], dtype=np.float64)
        stats[arm] = {name: column_map_stats(fields[name], fields["latitude_deg"],
                                             fields["longitude_deg"])
                      for name in ("inventory_change_kg", "precipitation_outflow_kg",
                                   "available_inventory_change_plus_precipitation_kg")}
    private_path = column_dir / "water_columns.npz"
    with private_path.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    private_path.chmod(0o600)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plot_path.parent.mkdir(parents=True, exist_ok=True)
    titles = ("Atmospheric inventory change", "Accumulated precipitation outflow",
              "Available imbalance (ΔW + precipitation)")
    fields = ("inventory_change_kg", "precipitation_outflow_kg",
              "available_inventory_change_plus_precipitation_kg")
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    color_limits = {}
    for col, (name, title) in enumerate(zip(fields, titles)):
        combined = np.concatenate([maps[arm][name].ravel() for arm in ("OFF", "COUPLED")])
        vmax = float(np.percentile(np.abs(combined), 99.5)) or 1.0
        vmin = 0.0 if name == "precipitation_outflow_kg" else -vmax
        color_limits[name] = {"vmin_kg": vmin, "vmax_kg": vmax,
                              "rule": "pooled OFF/COUPLED absolute-value 99.5th percentile; tails saturated",
                              "saturated_columns_by_arm": {
                                  arm: int(np.count_nonzero((maps[arm][name] < vmin) | (maps[arm][name] > vmax)))
                                  for arm in ("OFF", "COUPLED")}}
        for row, arm in enumerate(("OFF", "COUPLED")):
            image = axes[row, col].pcolormesh(maps[arm]["longitude_deg"],
                                               maps[arm]["latitude_deg"],
                                               maps[arm][name], shading="auto",
                                               cmap="viridis" if vmin == 0 else "coolwarm",
                                               vmin=vmin, vmax=vmax)
            axes[row, col].set_title(f"{arm}: {title}", fontsize=10)
            axes[row, col].set_xlabel("Longitude (degrees)")
            if col == 0:
                axes[row, col].set_ylabel("Latitude (degrees)")
            fig.colorbar(image, ax=axes[row, col], label="kg per native column",
                         extend="max" if vmin == 0 else "both")
    fig.suptitle("Frozen C4 0–600 s water columns — available imbalance is not closure\nColors saturate at pooled absolute-value p99.5; unclipped extrema are in the JSON")
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    return {"private_npz": {"path": str(private_path), "sha256": sha256(private_path),
                             "arrays": sorted(arrays),
                             "privacy": "Private numeric per-column arrays; do not publish."},
            "paired_map_png": {"path": str(plot_path), "sha256": sha256(plot_path)},
            "units": "kg per native column", "stats_by_arm": stats,
            "color_limits_by_field": color_limits}


def available_column_residual(inventory_change: np.ndarray,
                              precipitation_outflow: np.ndarray) -> np.ndarray:
    """Sum atmospheric layer changes by column, then add surface outflow."""
    if inventory_change.ndim != 3 or precipitation_outflow.shape != inventory_change.shape[1:]:
        raise ValueError("inventory change and precipitation maps use incompatible KJI/JI shapes")
    if not np.isfinite(inventory_change).all() or not np.isfinite(precipitation_outflow).all():
        raise ValueError("residual inputs must be finite")
    return np.sum(inventory_change, axis=0, dtype=np.float64) + precipitation_outflow


def inventory_record(ds: netCDF4.Dataset, record: int, gravity: float,
                     dx: float, dy: float) -> tuple[dict[str, float], np.ndarray, np.ndarray]:
    mass, _ = native._dry_mass(ds, record, gravity, dx, dy)
    inventory = {}
    species_extensive = []
    for name in WATER_FIELDS:
        field = native._finite(ds, name, record)
        if field.shape != mass.shape:
            raise ValueError(f"{name} and native hybrid dry mass shapes differ")
        extensive = field * mass
        inventory[name] = float(np.sum(extensive, dtype=np.float64))
        species_extensive.append(extensive)
    total_extensive = np.sum(species_extensive, axis=0, dtype=np.float64)
    area = dx * dy / (native._finite(ds, "MAPFAC_MX", record) *
                      native._finite(ds, "MAPFAC_MY", record))
    return inventory, total_extensive, area


def analyze_arm(arm: str, root: Path, gravity: float) -> dict[str, Any]:
    path, receipt, identity = _receipt_bound_history(root)
    times, grid = native._file_index([path])
    ordered = sorted(times)
    inventories: list[dict[str, float]] = []
    total_extensive: list[np.ndarray] = []
    precip_total: list[float] = []
    precip_change_map = None
    latitude = longitude = None
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_mask(False)
        for name in PRECIP_FIELDS:
            if name not in ds.variables:
                raise ValueError(f"history is missing required accumulated precipitation {name}")
            native._check_unit(ds, name, ("mm",))
        base_accum = None
        for when in ordered:
            _, record = times[when]
            inventory, water_ext, area = inventory_record(ds, record, gravity,
                                                           grid["dx"], grid["dy"])
            if when == ordered[-1]:
                latitude = native._finite(ds, "XLAT", record)
                longitude = native._finite(ds, "XLONG", record)
            accum = np.stack([native._finite(ds, name, record) for name in PRECIP_FIELDS])
            if accum.shape[1:] != area.shape:
                raise ValueError("precipitation accumulator does not map to native mass grid")
            if base_accum is None:
                base_accum = accum.copy()
                precip_change_map = np.zeros(area.shape, dtype=np.float64)
            else:
                precip_change_map += np.sum(accum - previous_accum, axis=0) * area
            previous_accum = accum
            precip_total.append(float(np.sum(precip_change_map, dtype=np.float64)))
            inventories.append(inventory)
            total_extensive.append(water_ext)
    delta = total_extensive[-1] - total_extensive[0]
    residual_columns = available_column_residual(delta, precip_change_map)
    return {"arm": arm, "receipt_status": receipt["status"], "identities": identity,
            "history_timestamps": [when.strftime("%Y-%m-%d_%H:%M:%S") for when in ordered],
            "native_dry_mass_measure": "DX*DY/(MAPFAC_MX*MAPFAC_MY) * -(C1H*(MU+MUB)+C2H)*DNW/g",
            "water_species_inventory_kg_by_elapsed_minute": inventories,
            "water_total_inventory_kg_by_elapsed_minute": [sum(row.values()) for row in inventories],
            "precipitation_accumulator_increment_kg_by_elapsed_minute": precip_total,
            "elapsed_600s": {
                "species_inventory_change_kg": {name: inventories[-1][name] - inventories[0][name]
                                                   for name in WATER_FIELDS},
                "total_water_inventory_change_kg": float(sum(inventories[-1].values()) -
                                                           sum(inventories[0].values())),
                "precipitation_outflow_kg": float(precip_total[-1]),
                "inventory_change_cell_diagnostics": _stats(delta),
                "available_residual_column_change_plus_precipitation": {
                    "signed_total_kg": float(np.sum(residual_columns, dtype=np.float64)),
                    "L1_kg": float(np.sum(np.abs(residual_columns), dtype=np.float64)),
                    "max_abs_column_kg": float(np.max(np.abs(residual_columns)))},
                "inventory_change_diagnostic_only": True,
                "closure_status": "OPEN_MISSING_TERMS"},
            "_column_maps": {"inventory_change_kg": np.sum(delta, axis=0, dtype=np.float64),
                             "precipitation_outflow_kg": precip_change_map,
                             "available_inventory_change_plus_precipitation_kg": residual_columns,
                             "latitude_deg": latitude, "longitude_deg": longitude,
                             "cell_area_m2": area},
            "missing_terms": ["lateral and top boundary water fluxes",
                              "surface exchange and precipitation interception/evaporation",
                              "non-microphysics water sources and sinks",
                              "relaxation/nudging and other model adjustments",
                              "numerical transport, diffusion, and roundoff residuals",
                              "precipitation phase-specific boundary attribution"]}


def psd_representation_audit(roots: dict[str, Path]) -> dict[str, Any]:
    source = ROOT / "docs/evidence/pr93_active_ice_20261020/runtime/ice_replay/call_origin_summary.json"
    summary = json.loads(source.read_text())
    arms = {}
    for arm, root in roots.items():
        old = summary["arms"][arm]
        receipt_path = root / "receipt.json"
        receipt = json.loads(receipt_path.read_text())
        if sha256(receipt_path) != old["receipt"]["sha256"]:
            raise ValueError(f"{arm} receipt no longer matches the C4 PSD audit")
        ledger = root / "run" / "pr85_kdm6_psd_boundary.raw.gz"
        row = next((item for item in receipt["generated_files"]
                    if Path(item["path"]).name == ledger.name), None)
        if row is None or sha256(ledger) != old["ledger_identity"]["compressed_sha256"]:
            raise ValueError(f"{arm} PSD boundary ledger no longer matches the C4 audit")
        coverage: Counter[tuple[str, str, str]] = Counter()
        representable = Counter()
        contexts: set[tuple[int, int]] = set()
        with gzip.open(ledger, "rt", encoding="ascii") as stream:
            for line in stream:
                if line.startswith("# PR90_KDM6_PSD_BOUNDARY_CONTEXT"):
                    fields = line.split()
                    contexts.add((int(fields[-2]), int(fields[-1])))
                    continue
                if not line.startswith("PR85_KDM6_PSD_BOUNDARY,"):
                    continue
                fields = line.rstrip().split(",")
                if len(fields) != 19:
                    raise ValueError(f"{arm} malformed PSD boundary row")
                species, stage, side = fields[1], fields[2], fields[6]
                coverage[(species, stage, side)] += 1
                representable[fields[18].upper() == "T"] += 1
        completion = old["subsequent_stage1_psd_completion"]
        arms[arm] = {"capture_status": old["capture_status"],
                     "first_valid_to_invalid_call": old["first_valid_to_invalid_call"],
                     "first_transition_level_count": old["first_transition_level_count"],
                     "first_subsequent_stage1_reconstruction": {
                         key: completion[key] for key in ("call_index", "stage", "side", "Nbefore",
                             "Nnative", "Ndirected", "exactNmin", "nativeDelta", "storageCorrection",
                             "boundary_rows_after_first_call")},
                     "nativeDelta_units": "# m-3",
                     "ledger_identity": {"path": str(ledger),
                         "compressed_sha256": row["sha256"],
                         "expanded_sha256": next(item["sha256"] for item in receipt["compressed_outputs"]
                                                  if item.get("compressed_path") == ledger.name)},
                     "ledger_representation_coverage": {
                         "context_count_timestep_lat_pairs": len(contexts),
                         "boundary_row_count_by_species_stage_side": {
                             f"{species}/{stage}/side{side}": count
                             for (species, stage, side), count in sorted(coverage.items())},
                         "native_reconstruction_available_rows": representable[True],
                         "native_reconstruction_unavailable_rows": representable[False]},
                     "volume_weighted_number_change": "UNAVAILABLE: boundary ledger does not include DELZ or cell volume",
                     "interpretation": "Selected ice PSD representation reconstruction only; number change is not nucleation."}
    return {"source_summary": {"path": str(source), "sha256": sha256(source)}, "arms": arms}


def verify_paired_grid(roots: dict[str, Path]) -> dict[str, Any]:
    paths = {arm: root / "run" / "wrfout_d01_2026-08-16_13:00:00"
             for arm, root in roots.items()}
    with netCDF4.Dataset(paths["OFF"]) as off, netCDF4.Dataset(paths["COUPLED"]) as coupled:
        off.set_auto_mask(False)
        coupled.set_auto_mask(False)
        if (float(off.DX), float(off.DY)) != (float(coupled.DX), float(coupled.DY)):
            raise ValueError("OFF/COUPLED DX/DY differ")
        if off.variables["Times"].shape != coupled.variables["Times"].shape or not np.array_equal(
                off.variables["Times"][:], coupled.variables["Times"][:]):
            raise ValueError("OFF/COUPLED history timestamps differ")
        for name in ("MAPFAC_MX", "MAPFAC_MY", "XLAT", "XLONG", "C1H", "C2H", "DNW"):
            if not np.array_equal(off.variables[name][:], coupled.variables[name][:]):
                raise ValueError(f"OFF/COUPLED {name} differs")
        return {"dx_m": float(off.DX), "dy_m": float(off.DY),
                "timestamps_exact_match": True, "mass_map_factors_exact_match": True,
                "mass_grid_shape": list(off.variables["MU"].shape[-2:]),
                "coordinates_and_hybrid_coefficients_exact_match": True}


def history_source_scope(root: Path) -> dict[str, Any]:
    path = root / "run" / "wrfout_d01_2026-08-16_13:00:00"
    with netCDF4.Dataset(path) as ds:
        available = {}
        for name in ("RAINC", "RAINNC", "RAINSH", "SNOWNC", "GRAUPELNC", "HAILNC", "QFX",
                     "QVAPOR", "U", "V", "W"):
            if name in ds.variables:
                variable = ds.variables[name]
                available[name] = {"units": str(getattr(variable, "units", "")),
                                   "description": str(getattr(variable, "description", "")),
                                   "dimensions": list(variable.dimensions)}
        water_flux_names = [name for name in ds.variables
                            if any(token in name.upper() for token in ("QVAPOR_FLUX", "MOIST_FLUX", "WATER_FLUX"))]
    receipt = json.loads((root / "receipt.json").read_text())
    ledgers = sorted(Path(row["path"]).name for row in receipt.get("generated_files", [])
                     if any(token in Path(row["path"]).name.lower()
                            for token in ("budget", "transport", "source", "process")))
    return {"history_public_fields": available,
            "water_species_face_flux_fields_present": water_flux_names,
            "receipt_bound_diagnostic_ledgers": ledgers,
            "scope": "RAINC and RAINNC are accumulated public precipitation depths. QFX is an instantaneous surface moisture flux; sparse history snapshots are not a time-integrated exchange ledger. U/V/W do not provide water-species face fluxes. Selected process ledgers do not constitute a whole-model transport/nudging/surface budget."}


def kdm6_geometry_source_audit(roots: dict[str, Path], gravity: float) -> dict[str, Any]:
    arms = {}
    for arm, root in roots.items():
        run_receipt = json.loads((root / "receipt.json").read_text())
        build_info = run_receipt["candidate_build"]
        build_path = Path(build_info["receipt_path"])
        build = json.loads(build_path.read_text())
        if sha256(build_path) != build_info["receipt_sha256"]:
            raise ValueError("C4 native overlay build receipt changed")
        overrides = {Path(row["requested_path"]).name: row
                     for row in build["source_overrides"].values()}
        kdm_source = overrides["module_mp_kdm6.F"]
        solve_source = overrides["solve_em.F"]
        for row in (kdm_source, solve_source):
            source_path = Path(row["requested_path"])
            if sha256(source_path) != row["requested_sha256"]:
                raise ValueError(f"C4 source override changed: {source_path}")
        kdm_text = Path(kdm_source["requested_path"]).read_text(errors="replace")
        solve_text = Path(solve_source["requested_path"]).read_text(errors="replace")
        if ("real,intent(in) :: den(" not in kdm_text or "real,intent(in) :: delz(" not in kdm_text):
            raise ValueError("C4 KDM6 source no longer declares DEN and DELZ read-only")
        ordering = [solve_text.find("CALL pr85_joint_stage_dump('PRE_KDM6'"),
                    solve_text.find("CALL microphysics_driver("),
                    solve_text.find("CALL pr85_joint_stage_dump('POST_KDM6'"),
                    solve_text.find("CALL after_all_rk_steps (")]
        if any(pos < 0 for pos in ordering) or ordering != sorted(ordering):
            raise ValueError("C4 solve_em producer order cannot be verified")

        raw_gz = root / "run/kdm6_third_call_pre.raw.gz"
        compressed_row = next(row for row in run_receipt["compressed_outputs"]
                              if row["compressed_path"] == raw_gz.name)
        if sha256(raw_gz) != compressed_row["compressed_sha256"]:
            raise ValueError("third-call PRE capture is not bound by the run receipt")
        with tempfile.TemporaryDirectory(prefix="pr94-c4-geometry-") as temp_dir:
            expanded = Path(temp_dir) / "kdm6_third_call_pre.raw"
            digest = hashlib.sha256()
            with gzip.open(raw_gz, "rb") as source, expanded.open("wb") as target:
                for block in iter(lambda: source.read(1 << 20), b""):
                    digest.update(block)
                    target.write(block)
            if digest.hexdigest() != compressed_row["sha256"]:
                raise ValueError("third-call PRE expanded hash is not receipt-bound")
            trace = kdm6_trace.read_dump(expanded)
        if (trace["stage"], trace["itimestep"], trace["params"]["dt_s"]) != (1, 3, 20.0):
            raise ValueError("expected the authoritative 20-second KDM6 PRE input at timestep 3")
        bounds = trace["bounds"]
        index = {when: (path, record) for when, (path, record) in
                 native._file_index([root / "run/wrfout_d01_2026-08-16_13:00:00"])[0].items()}
        endpoint = sorted(index)[1]
        if (endpoint - min(index)).total_seconds() != 60:
            raise ValueError("third-call geometry comparison requires the matching T60 history endpoint")
        with netCDF4.Dataset(index[endpoint][0]) as ds:
            ds.set_auto_mask(False)
            record = index[endpoint][1]
            phi = (native._finite(ds, "PH", record) +
                   native._finite(ds, "PHB", record))
            history_dz = np.diff(phi, axis=0) / gravity
        y = slice(bounds["jts"] - 1, bounds["jte"])
        x = slice(bounds["its"] - 1, bounds["ite"])
        k = slice(bounds["kts"] - 1, bounds["kte"])
        history_dz = history_dz[k, y, x].transpose(1, 0, 2)
        call_dz = trace["fields"]["DELZ"].astype(np.float64)
        delta = history_dz - call_dz
        relative = np.abs(delta) / call_dz
        arms[arm] = {"third_call_pre_identity": {
                         "path": str(raw_gz), "compressed_sha256": compressed_row["compressed_sha256"],
                         "expanded_sha256": compressed_row["sha256"]},
                     "source_binding": {
                         "overlay_build_receipt": {"path": str(build_path), "sha256": sha256(build_path)},
                         "module_mp_kdm6_source": {"path": kdm_source["requested_path"],
                             "sha256": kdm_source["requested_sha256"],
                             "DEN_and_DELZ_intent": "IN"},
                         "solve_em_source": {"path": solve_source["requested_path"],
                             "sha256": solve_source["requested_sha256"],
                             "producer_order": ["PRE_KDM6", "microphysics_driver", "POST_KDM6",
                                                "after_all_rk_steps"]}},
                     "call": {"timestep": 3, "call_seconds": 60,
                              "captured_pre_fields": ["DEN", "DELZ", *WATER_FIELDS]},
                     "same_minute_history_layer_thickness_comparison": {
                         "history_record_timestamp": endpoint.strftime("%Y-%m-%d_%H:%M:%S"),
                         "support_jki": list(call_dz.shape),
                         "mean_abs_difference_m": float(np.mean(np.abs(delta))),
                         "max_abs_difference_m": float(np.max(np.abs(delta))),
                         "mean_relative_abs_difference": float(np.mean(relative)),
                         "max_relative_abs_difference": float(np.max(relative)),
                         "exact_match_fraction": float(np.mean(history_dz == call_dz)),
                         "source_order_note": "History geometry is emitted after microphysics and after_all_rk_steps; it is not the KDM6 PRE input geometry."},
                     "call_budget_status": "NOT_COMPUTED",
                     "call_budget_gap": "Only timestep 3 has a receipt-bound KDM6 DELZ dump; its call-specific RAINNC increment and call-specific numerical residual are not captured. Remaining KDM6 calls have no DELZ capture. The minute RAINNC history increment spans three calls and is not assigned to one call."}
    return {"arms": arms,
            "conclusion": "The KDM6 input geometry and density are directly captured only for timestep 3, but same-minute history PH+PHB is a post-microphysics/post-finalization product and does not exactly reproduce that DELZ. The current receipts do not support a complete per-call water-plus-precipitation residual; no PH-derived or initial geometry is substituted."}


def boundary_and_source_ledger_audit(roots: dict[str, Path]) -> dict[str, Any]:
    arms = {}
    for arm, root in roots.items():
        receipt = json.loads((root / "receipt.json").read_text())
        run = root / "run"
        namelist = (run / "namelist.input.source").read_text(errors="replace")
        fdda_match = re.search(r"(?is)&fdda\s*(.*?)\/", namelist)
        if fdda_match is None:
            raise ValueError("C4 namelist is missing its FDDA block")
        fdda_body = fdda_match.group(1).strip()
        boundary_match = re.search(r"(?is)&bdy_control\s*(.*?)\/", namelist)
        if boundary_match is None:
            raise ValueError("C4 namelist is missing its boundary-control block")
        boundary = boundary_match.group(1)
        specified = re.search(r"(?i)specified\s*=\s*\.true\.", boundary) is not None
        ledger_counts: dict[str, Any] = {}
        for name, marker in (("pr85_joint_transport_budget.raw.gz", "BASELINE_JOINT_FEASIBLE"),
                             ("pr85_joint_source_diffusion.raw.gz", "SOURCE_DIFFUSION_DELTA_DT_PRESSURE"),
                             ("pr87_pbl_source_correction.raw.gz", "PR87_PBL_SOURCE_CORRECTION_RK"),
                             ("pr85_cumulus_source.raw.gz", "PR85_CUMULUS_SOURCE_V1")):
            count = count_ledger_marker_rows(run / name, marker)
            ledger_counts[name] = {"receipt_sha256": next(row["sha256"] for row in receipt["generated_files"]
                                                              if row["path"] == name),
                                   "records_with_marker": count}
        kdm_source_path = Path(receipt["candidate_build"]["receipt_path"])
        build = json.loads(kdm_source_path.read_text())
        kdm_source = next(row["requested_path"] for row in build["source_overrides"].values()
                          if Path(row["requested_path"]).name == "module_mp_kdm6.F")
        kdm_text = Path(kdm_source).read_text(errors="replace")
        capture_once = ("pr67_trace_this_call = .not. pr67_trace_complete" in kdm_text and
                        "pr67_trace_complete = .true." in kdm_text)
        arms[arm] = {"fdda_namelist_block": fdda_body or "EMPTY",
                     "fdda_configured": bool(fdda_body),
                     "specified_lateral_boundary_enabled": specified,
                     "specified_boundary_width_and_relax_zone": {
                         key: int(re.search(rf"(?i){key}\s*=\s*(\d+)", boundary).group(1))
                         for key in ("spec_bdy_width", "relax_zone")},
                     "water_species_face_flux_fields": [],
                     "receipt_bound_source_ledgers": ledger_counts,
                     "kdm6_detailed_process_capture": {
                         "source_gating_verifies_first_call_only": capture_once,
                         "captured_process_file": "pr67_kdm6_process.raw.gz",
                         "whole_window_call_coverage": False},
                     "term_interpretation": {
                         "joint_transport": "RK grouped Q/N candidate/fallback diagnostics; not face water flux",
                         "joint_source_diffusion": "selected paired scalar diffusion correction; not full moisture transport",
                         "pbl_source_correction": "logged PBL tendency correction channels, not the complete PBL moisture source",
                         "cumulus_source": "KSAS QC/QI and paired number source packets; not all QV/hydrometeor source terms",
                         "surface": "QFX snapshots exist but no time-integrated surface exchange ledger",
                         "lateral_boundary": "specified lateral boundary active; no water-species boundary flux ledger",
                         "relaxation": "FDDA namelist block is empty; analysis nudging is not configured in this run"}}
    return {"arms": arms}


def count_ledger_marker_rows(path: Path, marker: str) -> int:
    """Count marker records in a padded Fortran text ledger."""
    with gzip.open(path, "rt", encoding="ascii", errors="replace") as stream:
        return sum(line.lstrip().startswith(marker) for line in stream)


def analyze(off_root: Path = RUN_ROOTS["OFF"], coupled_root: Path = RUN_ROOTS["COUPLED"],
            column_dir: Path | None = None, plot_path: Path | None = None) -> dict[str, Any]:
    constants_path = Path("/var/tmp/pr87_history_constants_20261019/receipt.json")
    gravity, constants_identity = native._constants(constants_path)
    arms = {"OFF": analyze_arm("OFF", off_root, gravity),
            "COUPLED": analyze_arm("COUPLED", coupled_root, gravity)}
    psd = psd_representation_audit({"OFF": off_root, "COUPLED": coupled_root})
    paired_grid = verify_paired_grid({"OFF": off_root, "COUPLED": coupled_root})
    source_scope = {arm: history_source_scope(root) for arm, root in
                    (("OFF", off_root), ("COUPLED", coupled_root))}
    geometry_source = kdm6_geometry_source_audit({"OFF": off_root, "COUPLED": coupled_root}, gravity)
    source_ledger_audit = boundary_and_source_ledger_audit({"OFF": off_root, "COUPLED": coupled_root})
    column_diagnostics = None
    if column_dir is not None or plot_path is not None:
        if column_dir is None or plot_path is None:
            raise ValueError("private column directory and public PNG path must be supplied together")
        column_diagnostics = export_column_diagnostics(
            column_dir, plot_path,
            {arm: result.pop("_column_maps") for arm, result in arms.items()})
    else:
        for result in arms.values():
            result.pop("_column_maps")
    return {"schema": "pr94_frozen_c4_absolute_water_budget_v1",
            "status": "ACCOUNTED_DIAGNOSTIC_OPEN", "physical_approval": False,
            "window_seconds": [0, 600], "history_interval_seconds": 60,
            "gravity_source": constants_identity, "paired_grid": paired_grid,
            "source_scope_audit": source_scope, "kdm6_geometry_source_audit": geometry_source,
            "boundary_and_source_ledger_audit": source_ledger_audit, "arms": arms,
            "interpretation": "Absolute per-arm water inventories and accumulated precipitation are reported with their available residual. Inventory change alone is not a conservation residual; no whole-model closure claim is made.",
            "psd_reconstruction": psd,
            "column_diagnostics": column_diagnostics}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off-root", type=Path, default=RUN_ROOTS["OFF"])
    parser.add_argument("--coupled-root", type=Path, default=RUN_ROOTS["COUPLED"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-column-dir", type=Path, required=True,
                        help="new private output directory for compressed per-column arrays")
    parser.add_argument("--column-map-png", type=Path, required=True,
                        help="new public paired OFF/COUPLED per-column map PNG")
    args = parser.parse_args()
    result = analyze(args.off_root, args.coupled_root, args.private_column_dir, args.column_map_png)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
