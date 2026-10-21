#!/usr/bin/env python3
"""Receipt-bound frozen-C4 cloud-pattern and early-response analysis."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/pr94_cloud_response_20261021"
COMPOSITION = ROOT / "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json"
RUNS = {arm: Path(f"/var/tmp/pr93_{arm}_600s_c4_bound_20261020") for arm in ("OFF", "COUPLED")}
SPECIES = {"QVAPOR": "kg/kg dry", "QCLOUD": "kg/kg dry", "QICE": "kg/kg dry",
           "QRAIN": "kg/kg dry", "QSNOW": "kg/kg dry", "QGRAUP": "kg/kg dry"}
STATE = {"pressure": "Pa", "geopotential": "m2 s-2"}
SECONDS = tuple(range(0, 601, 60))

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))
from pr86_compare_response import load_history  # noqa: E402
from pr94_water_budget import verify_paired_grid  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def make_masks(composition: dict[str, Any], shape: tuple[int, int, int]) -> dict[str, np.ndarray]:
    """Build time-invariant support and fixed Chebyshev buffers on active columns."""
    support = np.zeros(shape, dtype=bool)
    for target in composition["targets"]:
        i0, j0 = int(target["target_i0"]), int(target["target_j0"])
        if not (0 <= j0 - 1 < shape[1] and 0 <= i0 - 1 < shape[2]):
            raise ValueError("QC support target is outside the cropped active grid")
        for level in target["native_levels"]:
            k = int(level["native_eta_level0"])
            if not 0 <= k < shape[0]:
                raise ValueError("QC support level is outside the native grid")
            if level["composed_qc_source_links"]:
                support[k, j0 - 1, i0 - 1] = True
    if int(support.sum()) != 613 or int(support.any(axis=0).sum()) != 16:
        raise ValueError("source-composed support changed from 613 levels in 16 columns")
    columns = support.any(axis=0)
    masks = {"original_613_native_support": support}
    for radius in (2, 5):
        expanded = np.zeros_like(columns)
        ny, nx = columns.shape
        for dj in range(-radius, radius + 1):
            for di in range(-radius, radius + 1):
                ys = slice(max(0, dj), ny + min(0, dj))
                xs = slice(max(0, di), nx + min(0, di))
                src_y = slice(max(0, -dj), ny - max(0, dj))
                src_x = slice(max(0, -di), nx - max(0, di))
                expanded[ys, xs] |= columns[src_y, src_x]
        masks[f"fixed_{radius}_cell_chebyshev_buffer"] = np.broadcast_to(expanded, shape).copy()
    masks["full_active_history_domain"] = np.ones(shape, dtype=bool)
    return masks


def vector_metrics(off: np.ndarray, coupled: np.ndarray) -> dict[str, float | None]:
    """Compare actual arrays and decompose coupled-off against its initial pattern."""
    a, b = np.asarray(off, dtype=np.float64).ravel(), np.asarray(coupled, dtype=np.float64).ravel()
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("paired arrays must be finite and have identical shape")
    delta = b - a
    return {"off_rms": float(np.sqrt(np.mean(a*a))),
            "coupled_rms": float(np.sqrt(np.mean(b*b))),
            "delta_rms": float(np.sqrt(np.mean(delta*delta))),
            "delta_mean": float(np.mean(delta)), "delta_max_abs": float(np.max(np.abs(delta))),
            "delta_signed_sum": float(np.sum(delta, dtype=np.float64))}


def pattern_metrics(delta0: np.ndarray, delta: np.ndarray) -> dict[str, float | None]:
    base, current = np.asarray(delta0, dtype=np.float64).ravel(), np.asarray(delta, dtype=np.float64).ravel()
    if base.shape != current.shape or not np.isfinite(base).all() or not np.isfinite(current).all():
        raise ValueError("pattern arrays must be finite and have identical shape")
    base2 = float(np.dot(base, base))
    current2 = float(np.dot(current, current))
    cross = float(np.dot(base, current))
    cosine = cross / np.sqrt(base2 * current2) if base2 and current2 else None
    projection = cross / base2 if base2 else None
    residual = current - projection * base if projection is not None else current.copy()
    return {"cosine_delta_t_vs_delta0": cosine,
            "projection_delta_t_onto_delta0": projection,
            "orthogonal_residual_rms": float(np.sqrt(np.mean(residual*residual))),
            "delta0_rms": float(np.sqrt(np.mean(base*base))),
            "delta_t_rms": float(np.sqrt(np.mean(current*current))),
            "delta_t_minus_delta0_rms": float(np.sqrt(np.mean((current-base)**2)))}


def horizontal_translation_scan(delta0: np.ndarray, delta: np.ndarray, support: np.ndarray,
                                max_shift: int = 5) -> dict[str, Any]:
    """Compare delta0 support values with delta sampled at fixed horizontal offsets."""
    if (delta0.shape != delta.shape or support.shape != delta0.shape or delta0.ndim != 3 or
            max_shift < 0):
        raise ValueError("translation scan arrays must share a 3-D KJI shape")
    if not np.isfinite(delta0).all() or not np.isfinite(delta).all():
        raise ValueError("translation scan arrays must be finite")
    k, j, i = np.nonzero(support)
    if not len(k):
        raise ValueError("translation scan support is empty")
    baseline = delta0[support].astype(np.float64)
    base_norm = float(np.linalg.norm(baseline))
    if base_norm == 0:
        raise ValueError("translation scan baseline has zero norm")
    ny, nx = support.shape[1:]
    rows = []
    for dj in range(-max_shift, max_shift + 1):
        for di in range(-max_shift, max_shift + 1):
            shifted_j, shifted_i = j + dj, i + di
            if np.any((shifted_j < 0) | (shifted_j >= ny) |
                      (shifted_i < 0) | (shifted_i >= nx)):
                raise ValueError("search domain moves fixed support outside active grid; no wrap or crop allowed")
            current = delta[k, shifted_j, shifted_i].astype(np.float64)
            norm = float(np.linalg.norm(current))
            cosine = float(np.dot(baseline, current) / (base_norm * norm)) if norm else None
            rows.append({"lag_dj": dj, "lag_di": di, "sample_count": len(k),
                         "uncentered_cosine": cosine,
                         "aligned_difference_rms": float(np.sqrt(np.mean((current - baseline) ** 2))),
                         "sampled_delta_rms": float(np.sqrt(np.mean(current ** 2)))})
    valid = [row for row in rows if row["uncentered_cosine"] is not None]
    best = max(valid, key=lambda row: row["uncentered_cosine"]) if valid else None
    zero = next(row for row in rows if row["lag_dj"] == 0 and row["lag_di"] == 0)
    return {"search_domain": {"lag_dj": [-max_shift, max_shift],
                               "lag_di": [-max_shift, max_shift],
                               "lag_convention": "At each original support index (k,j,i), compare delta0[k,j,i] with delta[k,j+lag_dj,i+lag_di].",
                               "support_is_fixed": True, "support_native_values": int(len(k)),
                               "active_grid_shape_kji": list(delta.shape),
                               "boundary_handling": "No wrap and no lag-specific crop. Error if any fixed-support sample would leave the active grid."},
            "zero_lag": zero, "best_uncentered_cosine": best,
            "best_lag_on_search_boundary": bool(best and
                (abs(best["lag_dj"]) == max_shift or abs(best["lag_di"]) == max_shift)),
            "tie_break": "First maximum in ascending lag_dj then lag_di scan order.",
            "all_lags": rows}


def sample_coordinate(off: np.ndarray, coupled: np.ndarray,
                      coordinate_kji: tuple[int, int, int]) -> dict[str, float]:
    """Read paired fields at one preselected, unchanged native coordinate."""
    if off.shape != coupled.shape or off.ndim != 3:
        raise ValueError("coordinate samples require paired 3-D KJI fields")
    k, j, i = coordinate_kji
    if not (0 <= k < off.shape[0] and 0 <= j < off.shape[1] and 0 <= i < off.shape[2]):
        raise ValueError("selected coordinate is outside the active field")
    a, b = float(off[k, j, i]), float(coupled[k, j, i])
    if not np.isfinite((a, b)).all():
        raise ValueError("coordinate sample is nonfinite")
    return {"OFF": a, "COUPLED": b, "delta": b - a}


def verify_run(arm: str, run_root: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    receipt_path = run_root / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("arm") != arm or receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0:
        raise ValueError(f"invalid {arm} run receipt")
    if receipt.get("final_completed_step") != 30:
        raise ValueError(f"{arm} receipt does not complete frozen C4 step 30")
    rows = [row for row in receipt.get("generated_files", []) if row.get("path", "").startswith("wrfout_d01_")]
    if len(rows) != 1:
        raise ValueError(f"{arm} receipt does not identify exactly one history file")
    history = run_root / "run" / rows[0]["path"]
    if not history.is_file() or sha256(history) != rows[0]["sha256"]:
        raise ValueError(f"{arm} history is absent or does not match its receipt")
    return history, receipt, {"path": str(history), "sha256": rows[0]["sha256"],
                              "receipt_path": str(receipt_path), "receipt_sha256": sha256(receipt_path),
                              "arm": arm, "status": receipt["status"],
                              "final_completed_step": receipt["final_completed_step"]}


def read_face_winds(path: Path, frame: int) -> dict[str, np.ndarray]:
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_mask(False)
        # Exclude WRF's raw outer mass-grid ring; retain actual staggered faces.
        return {"U_face": np.asarray(ds["U"][frame, :, 1:-1, 1:-1], dtype=np.float64),
                "V_face": np.asarray(ds["V"][frame, :, 1:-1, 1:-1], dtype=np.float64),
                "W_face": np.asarray(ds["W"][frame, :, 1:-1, 1:-1], dtype=np.float64)}


def first_max(delta: np.ndarray, mask: np.ndarray | None = None) -> dict[str, Any]:
    values = np.abs(delta)
    if mask is not None:
        values = np.where(mask, values, -1.0)
    index = np.unravel_index(int(np.argmax(values)), delta.shape)
    return {"max_abs": float(abs(delta[index])), "signed_at_max": float(delta[index]),
            "index_kji": [int(x) for x in index]}


def draw_maps(deltas: dict[int, dict[str, np.ndarray]], output: Path,
              zoom_columns: np.ndarray) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    fields = {"QCLOUD": "kg/kg dry", "QICE": "kg/kg dry", "QRAIN": "kg/kg dry",
              "QSNOW": "kg/kg dry", "QGRAUP": "kg/kg dry", "pressure": "Pa",
              "geopotential": "m2 s-2", "W": "m s-1"}
    y_indices, x_indices = np.nonzero(zoom_columns)
    y0, y1 = int(y_indices.min()), int(y_indices.max()) + 1
    x0, x1 = int(x_indices.min()), int(x_indices.max()) + 1
    for field, unit in fields.items():
        times = (60, 120, 600)
        maps = {t: deltas[t][field][np.abs(deltas[t][field]).argmax(axis=0),
                                      np.arange(deltas[t][field].shape[1])[:, None],
                                      np.arange(deltas[t][field].shape[2])[None, :]] for t in times}
        vmax = max(float(np.max(np.abs(x))) for x in maps.values()) or 1.0
        fig, axes = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
        for ax, t in zip(axes, times):
            im = ax.imshow(maps[t], origin="lower", cmap="RdBu_r", vmin=-vmax, vmax=vmax,
                           interpolation="nearest", aspect="auto")
            ax.set_title(f"{field}: max-|δ|-level envelope, {t}s")
            ax.set_xlabel("active i"); ax.set_ylabel("active j")
        fig.colorbar(im, ax=axes, label=f"COUPLED − OFF ({unit})", shrink=.82)
        path = output / f"{field.lower()}_response_maps.png"
        fig.savefig(path, dpi=140); plt.close(fig)
        artifacts[field] = {"path": str(path), "sha256": sha256(path),
                            "aggregation": "signed native-level δ at each column's largest |δ|; a vertical envelope, not a common pressure/geopotential surface"}
        if field in STATE or field == "W":
            zoom_maps = {t: maps[t][y0:y1, x0:x1] for t in times}
            zoom_vmax = max(float(np.max(np.abs(x))) for x in zoom_maps.values()) or 1.0
            fig, axes = plt.subplots(1, 3, figsize=(12, 4), constrained_layout=True)
            for ax, t in zip(axes, times):
                im = ax.imshow(zoom_maps[t], origin="lower", cmap="RdBu_r", vmin=-zoom_vmax,
                               vmax=zoom_vmax, interpolation="nearest", aspect="auto")
                ax.set_title(f"{field}: envelope, {t}s")
                ax.set_xlabel(f"active i, {x0}–{x1-1}")
                ax.set_ylabel(f"active j, {y0}–{y1-1}")
            fig.colorbar(im, ax=axes, label=f"COUPLED − OFF ({unit})", shrink=.82)
            zoom_path = output / f"{field.lower()}_response_maps_support_zoom.png"
            fig.savefig(zoom_path, dpi=140); plt.close(fig)
            artifacts[f"{field}_support_zoom"] = {
                "path": str(zoom_path), "sha256": sha256(zoom_path),
                "aggregation": artifacts[field]["aggregation"],
                "view": "fixed bounding box of the prespecified 5-cell Chebyshev buffer around original source support",
                "active_j_bounds_inclusive": [y0, y1 - 1],
                "active_i_bounds_inclusive": [x0, x1 - 1],
                "symmetric_color_limit": zoom_vmax}
    return artifacts


def analyze(run_roots: dict[str, Path], composition_path: Path, output: Path) -> dict[str, Any]:
    histories, receipts, identities = {}, {}, {}
    for arm, root in run_roots.items():
        histories[arm], receipts[arm], identities[arm] = verify_run(arm, root)
    if receipts["OFF"].get("candidate_wrfbdy_sha256") != receipts["COUPLED"].get("candidate_wrfbdy_sha256"):
        raise ValueError("paired arms do not share the same candidate boundary input")
    paired_grid = verify_paired_grid(run_roots)
    composition_doc = json.loads(composition_path.read_text())
    composition = composition_doc["composed_qc_vertical_influence"]
    masks = make_masks(composition, (39, 280, 232))
    records: dict[str, Any] = {}
    deltas_for_plot: dict[int, dict[str, np.ndarray]] = {}
    delta0: dict[str, dict[str, np.ndarray]] | None = None
    first_minute: dict[str, Any] = {}
    translation_inputs: dict[int, np.ndarray] = {}
    fixed_series: dict[str, dict[str, Any]] = {}
    for second in SECONDS:
        # The model advances every 20 s; this history stream writes every 60 s.
        frame = second // 60
        loaded = {}
        expected_time = (dt.datetime(2026, 8, 16, 13) + dt.timedelta(seconds=second)).strftime("%Y-%m-%d_%H:%M:%S")
        for arm in ("OFF", "COUPLED"):
            timestamp, fields, _ = load_history(histories[arm], frame)
            if timestamp != expected_time:
                raise ValueError(f"{arm} history frame {frame} is not requested time {expected_time}")
            loaded[arm] = fields
        if delta0 is None:
            delta0 = {name: {arm: loaded[arm][name].copy() for arm in loaded}
                      for name in (*SPECIES, *STATE, "U", "V", "W")}
        records[str(second)] = {}
        current_deltas = {}
        for name, unit in {**SPECIES, **STATE, "U": "m s-1", "V": "m s-1", "W": "m s-1"}.items():
            off, coupled = loaded["OFF"][name], loaded["COUPLED"][name]
            if off.shape != (39, 280, 232):
                raise ValueError(f"{name} shape is not active mass-grid geometry: {off.shape}")
            delta = coupled - off
            current_deltas[name] = delta
            per_mask = {}
            for mask_name, mask in masks.items():
                a, b = off[mask], coupled[mask]
                d = delta[mask]
                m = vector_metrics(a, b)
                if name in SPECIES:
                    baseline = (delta0[name]["COUPLED"] - delta0[name]["OFF"])[mask]
                    m.update(pattern_metrics(baseline, d))
                per_mask[mask_name] = {"selected_native_values": int(mask.sum()), "unit": unit, **m}
            records[str(second)][name] = per_mask
        if second in (60, 120, 600):
            deltas_for_plot[second] = {
                name: current_deltas[name].copy()
                for name in (*[n for n in SPECIES if n != "QVAPOR"], "pressure", "geopotential", "W")}
        if second in (60, 120, 600):
            translation_inputs[second] = current_deltas["QCLOUD"].copy()
        if second == 60:
            for name in ("pressure", "geopotential", "W"):
                for scope, mask in (("original_613_native_support", masks["original_613_native_support"]),
                                    ("full_active_history_domain", masks["full_active_history_domain"])):
                    coordinate = tuple(first_max(current_deltas[name], mask)["index_kji"])
                    initial_values = sample_coordinate(delta0[name]["OFF"], delta0[name]["COUPLED"], coordinate)
                    current_values = sample_coordinate(loaded["OFF"][name], loaded["COUPLED"][name], coordinate)
                    fixed_series.setdefault(name, {})[scope] = {
                        "selection_seconds": 60, "selection_rule": "maximum absolute paired delta within this fixed support/domain at T60",
                        "coordinate_kji": list(coordinate),
                        "samples": [{"elapsed_seconds": 0, **initial_values},
                                    {"elapsed_seconds": 60, **current_values}]}
        elif second > 60:
            for name, scopes in fixed_series.items():
                for scope_data in scopes.values():
                    coordinate = tuple(scope_data["coordinate_kji"])
                    scope_data["samples"].append({"elapsed_seconds": second,
                                                  **sample_coordinate(loaded["OFF"][name],
                                                                      loaded["COUPLED"][name], coordinate)})
        if second in (0, 60):
            fields = {}
            for name in ("pressure", "geopotential", "U", "V", "W"):
                delta = current_deltas[name]
                fields[name] = {scope: {"rms": float(np.sqrt(np.mean(delta[mask]**2))),
                                         **first_max(delta, mask)}
                                for scope, mask in masks.items()}
            face_fields = {}
            face_data = {arm: read_face_winds(histories[arm], frame) for arm in ("OFF", "COUPLED")}
            for name in ("U_face", "V_face", "W_face"):
                diff = face_data["COUPLED"][name] - face_data["OFF"][name]
                face_fields[name] = {"rms": float(np.sqrt(np.mean(diff**2))), **first_max(diff),
                                     "shape": list(diff.shape), "unit": "m s-1"}
            first_minute[str(second)] = {"elapsed_seconds": second, "masspoint_fields": fields,
                                         "actual_staggered_face_fields": face_fields}
    assert delta0 is not None
    output.mkdir(parents=True, exist_ok=True)
    fixed5_columns = masks["fixed_5_cell_chebyshev_buffer"].any(axis=0)
    plots = draw_maps(deltas_for_plot, output / "plots", fixed5_columns)
    qc_baseline = delta0["QCLOUD"]["COUPLED"] - delta0["QCLOUD"]["OFF"]
    translation = {str(second): horizontal_translation_scan(
        qc_baseline, current, masks["original_613_native_support"], max_shift=5)
        for second, current in translation_inputs.items()}
    return {
        "schema": "pr94_frozen_c4_cloud_response_v1", "physical_approval": "FAIL_OPEN",
        "run_scope": "Receipt-bound frozen-C4 OFF/COUPLED ten-minute paired history; 60-second samples.",
        "identities": identities, "paired_grid": paired_grid,
        "paired_input_identity": {"candidate_wrfinput_sha256_by_arm": {
                                      arm: receipts[arm].get("candidate_wrfinput_sha256") for arm in receipts},
                                  "candidate_wrfbdy_sha256_common": receipts["OFF"].get("candidate_wrfbdy_sha256"),
                                  "interpretation": "Candidate initial states are arm-specific and differ by design; the same-location delta at saved t=0 is retained as the pattern baseline."},
        "composition": {"path": str(composition_path), "sha256": sha256(composition_path),
                        "rule": "native eta level included iff its source-composed QC links are nonempty",
                        "support_native_values": 613, "support_columns": 16,
                        "fixed_masks": {name: int(mask.sum()) for name, mask in masks.items()},
                        "shape_kji": [39, 280, 232],
                        "fixed_5_cell_buffer_bounding_box_active_j_i_inclusive": [
                            int(np.nonzero(fixed5_columns)[0].min()),
                            int(np.nonzero(fixed5_columns)[0].max()),
                            int(np.nonzero(fixed5_columns)[1].min()),
                            int(np.nonzero(fixed5_columns)[1].max())],
                        "boundary_cropping": "History reader crops raw WRF mass grid [1:-1,1:-1]. Buffer expands support within this active domain and clips at its boundary; no wraparound."},
        "pattern_interpretation": "Cosine, projection, and orthogonal residual compare the actual paired-array delta(t) with delta(0) on an unchanged mask. They describe spatial pattern similarity only; they do not identify causes, observation destruction, or forecast skill.",
        "records": records, "first_minute_geometry_audit": first_minute,
        "state_response_maps": {name: plots[name] for name in ("pressure", "geopotential", "W")},
        "fixed_coordinate_state_series": {
            "selection_note": "Coordinates are selected by maximum absolute T60 paired delta in each stated scope, then held unchanged from 0 through 600 s. This is a selection-based diagnostic, not an independent validation or skill score.",
            "fields": fixed_series},
        "qcloud_horizontal_translation_scan": {
            "interpretation": "A descriptive alignment search over a prespecified ±5 active-grid-cell domain on the unchanged original 613-value support. A selected lag does not establish advection or a causal decomposition.",
            "times": translation},
        "process_attribution": {
            "advection_or_material_motion": "NOT_IDENTIFIED_FROM_PAIRED_HISTORY_PATTERN",
            "phase_species_conversion": "NOT_CAUSALLY_DECOMPOSED",
            "numerical_residual": {"status": "UNAVAILABLE",
                                    "reason": "No complete timestep-resolved water tendency and boundary-flux closure is available in these histories."}},
        "actual_observation_fit": {"status": "UNAVAILABLE", "reason": "No authoritative measurement array and matching observation operator are bound to this runtime evidence; H(X)-y was not computed."},
        "limits": ["RMS decline does not establish skill or explain a cloud-pattern change.",
                   "Changes can be consistent with advection, spatial redistribution, phase/species conversion, and nonlinear evolution, but these records do not causally decompose those effects.",
                   "T60-selected coordinates and maximum-cosine translation lags are selection-based descriptions; they do not establish skill or advective causation.",
                   "Mass-point U/V/W differences and staggered face differences are separate comparisons; neither is a continuity closure."],
        "plots": plots,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    result = analyze(RUNS, COMPOSITION, args.output)
    path = args.output / "cloud_response.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
