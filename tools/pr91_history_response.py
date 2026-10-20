#!/usr/bin/env python3
"""Receipt-bound C5/C7 history interaction and C7 transient maps."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "pr89_paired_history", ROOT / "tools/pr89_paired_history.py")
paired = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(paired)
FIELDS = {"pressure": ("P+PB", "Pa"), "geopotential": ("PH+PHB", "m2 s-2"),
          "vertical_velocity": ("W", "m s-1")}
COMMON_TIMES = (0, 60, 120)
C7_TIMES = (0, 60, 120, 180)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _receipt_identity(receipt: Path, history: Path, arm: str, endpoint: int) -> dict[str, Any]:
    data = json.loads(receipt.read_text())
    if data.get("arm") != arm:
        raise ValueError(f"{receipt} arm is {data.get('arm')!r}; expected {arm!r}")
    if data.get("status") != "COMPLETE" or data.get("returncode") != 0:
        raise ValueError(f"{receipt} is not a completed successful run receipt")
    files = {row["path"]: row["sha256"] for row in data.get("generated_files", [])}
    name = history.name
    if name not in files or files[name] != sha256(history):
        raise ValueError(f"{history} is not hash-bound by {receipt}")
    if len(data.get("expected_model_timestamps", [])) < endpoint // 20:
        raise ValueError(f"{receipt} does not cover {endpoint} seconds")
    if not data.get("candidate_wrfinput_sha256") or not data.get("candidate_wrfbdy_sha256"):
        raise ValueError(f"{receipt} lacks candidate initial or boundary input identity")
    return {"receipt_path": str(receipt), "receipt_sha256": sha256(receipt),
            "arm": arm, "status": data["status"], "returncode": data["returncode"],
            "history_path": str(history), "history_sha256": sha256(history),
            "candidate_wrfinput_sha256": data.get("candidate_wrfinput_sha256"),
            "candidate_wrfbdy_sha256": data.get("candidate_wrfbdy_sha256"),
            "candidate_namelist_sha256": data.get("candidate_namelist_sha256"),
            "frozen_executable_sha256": data.get("frozen_executable_sha256"),
            "executed_executable_sha256": data.get("executed_executable_sha256"),
            "expected_model_timestamps": data.get("expected_model_timestamps", [])}


def _verify_cross_case_static_geometry(reference: Path, candidate: Path) -> dict[str, Any]:
    matches = {}
    with netCDF4.Dataset(reference) as ref, netCDF4.Dataset(candidate) as other:
        ref.set_auto_mask(False); other.set_auto_mask(False)
        for required in ("XLAT", "XLONG"):
            if required not in ref.variables or required not in other.variables:
                raise ValueError(f"required static grid coordinate {required} is missing")
        dx, dy = float(ref.DX), float(ref.DY)
        if (dx, dy) != (float(other.DX), float(other.DY)):
            raise ValueError("C5 and C7 DX/DY differ")
        ref_dims = {name: len(dim) for name, dim in ref.dimensions.items() if name != "Time"}
        other_dims = {name: len(dim) for name, dim in other.dimensions.items() if name != "Time"}
        if ref_dims != other_dims:
            raise ValueError(f"C5 and C7 non-Time dimensions differ: {ref_dims} != {other_dims}")
        for name in paired.STATIC_GEOMETRY:
            in_ref, in_other = name in ref.variables, name in other.variables
            if in_ref != in_other:
                raise ValueError(f"static geometry variable {name} is present in only one history")
            if not in_ref:
                continue
            a, b = ref.variables[name], other.variables[name]
            a_values = np.asarray(a[0] if a.dimensions and a.dimensions[0] == "Time" else a[:])
            b_values = np.asarray(b[0] if b.dimensions and b.dimensions[0] == "Time" else b[:])
            exact = a_values.shape == b_values.shape and np.array_equal(a_values, b_values, equal_nan=True)
            matches[name] = {"shape_without_time": list(a_values.shape), "exact_match": bool(exact)}
            if not exact:
                raise ValueError(f"C5/C7 static grid field {name} differs")
    return {"dx_m": dx, "dy_m": dy, "non_Time_dimensions_exact_match": True,
            "static_fields": matches}


def _read_delta(off: Path, coupled: Path, times: dict, grid: dict,
                elapsed_times: tuple[int, ...]) -> dict[int, np.ndarray]:
    out = {}
    for seconds in elapsed_times:
        when = sorted(times)[seconds // 60]
        a = paired._load_snapshot(off, times, when, grid, 9.8100004196167)
        b = paired._load_snapshot(coupled, times, when, grid, 9.8100004196167)
        for label, (field, _) in FIELDS.items():
            if a[field].shape != b[field].shape:
                raise ValueError(f"{label} C5/C7 paired array shapes differ")
            out.setdefault(seconds, {})[label] = b[field] - a[field]
    return out


def _masks(grid: dict, support: np.ndarray) -> dict[str, np.ndarray]:
    ny, nx = grid["shape"]
    interior = np.zeros((ny, nx), dtype=bool)
    interior[1:-1, 1:-1] = True
    neighbor = np.zeros_like(support)
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            if (dj, di) == (0, 0):
                continue
            neighbor[max(0, dj):ny + min(0, dj), max(0, di):nx + min(0, di)] |= \
                support[max(0, -dj):ny - max(0, dj), max(0, -di):nx - max(0, di)]
    return {"whole_grid": np.ones((ny, nx), bool), "interior_boundary_ring_excluded": interior,
            "C7_T0_water_support_27_columns": support,
            "one_cell_neighbor_of_C7_T0_support": neighbor & ~support}


def _summary(array: np.ndarray, mask: np.ndarray) -> dict[str, Any]:
    selected = array[..., mask]
    return {"horizontal_columns": int(mask.sum()), "selected_values": int(selected.size),
            "signed_total": float(selected.sum(dtype=np.float64)),
            "mean": float(selected.mean()) if selected.size else None,
            "max_abs": float(np.max(np.abs(selected))) if selected.size else None,
            "rms": float(np.sqrt(np.mean(selected * selected))) if selected.size else None}


def _interaction_delta(d7: np.ndarray, d5: np.ndarray) -> np.ndarray:
    if d7.shape != d5.shape:
        raise ValueError(f"C5/C7 interaction arrays differ in shape: {d5.shape} != {d7.shape}")
    return d7 - d5


def _draw_maps(deltas: dict[int, dict[str, np.ndarray]], lats: np.ndarray,
               lons: np.ndarray, support: np.ndarray, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for label, (_, units) in FIELDS.items():
        arrays = {t: deltas[t][label] for t in C7_TIMES}
        # The map at each time is the signed value at the native vertical level
        # with the largest absolute arm difference in that column.
        maps = {t: np.take_along_axis(a, np.abs(a).argmax(axis=0)[None, ...], axis=0)[0]
                for t, a in arrays.items()}
        fig, axes = plt.subplots(1, 4, figsize=(18, 4), constrained_layout=True)
        vmax = max(float(np.max(np.abs(x))) for x in maps.values()) or 1.0
        for ax, t in zip(axes, C7_TIMES):
            im = ax.pcolormesh(lons, lats, maps[t], cmap="RdBu_r", vmin=-vmax, vmax=vmax,
                               shading="auto")
            ax.set_title(f"T{t}: signed δ at local max-|δ| level")
            ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
            if np.any(support):
                ax.set_xlim(float(lons[support].min()) - .75, float(lons[support].max()) + .75)
                ax.set_ylim(float(lats[support].min()) - .75, float(lats[support].max()) + .75)
        fig.colorbar(im, ax=axes, label=units, shrink=.82)
        path = output / f"c7_{label}_transient_maps.png"
        fig.savefig(path, dpi=150); plt.close(fig)
        artifacts[label] = {"path": str(path), "sha256": sha256(path),
                            "aggregation": "per column, signed field value at native vertical level with largest |COUPLED−OFF|",
                            "view": "zoomed to fixed C7 T0 water-support bounding box plus 0.75 degree margin"}
    return artifacts


def analyze(paths: dict[str, Path], output: Path) -> dict[str, Any]:
    identities = {}
    for case, endpoint in (("C5", 120), ("C7", 180)):
        for arm in ("OFF", "COUPLED"):
            key = f"{case}_{arm}"
            identities[key] = _receipt_identity(paths[key + "_receipt"], paths[key + "_history"], arm, endpoint)
    for arm in ("OFF", "COUPLED"):
        if identities[f"C5_{arm}"]["candidate_wrfinput_sha256"] != identities[f"C7_{arm}"]["candidate_wrfinput_sha256"]:
            raise ValueError(f"C5 and C7 {arm} runs do not share exact candidate initial input")
    if len({v["candidate_wrfbdy_sha256"] for v in identities.values()}) != 1:
        raise ValueError("C5 and C7 do not share exact candidate boundary input")
    off5, grid5 = paired._records(paths["C5_OFF_history"])
    on5, grid5b = paired._records(paths["C5_COUPLED_history"])
    off7, grid7 = paired._records(paths["C7_OFF_history"])
    on7, grid7b = paired._records(paths["C7_COUPLED_history"])
    for g in (grid5b, grid7, grid7b):
        paired._pair_geometry(grid5, g)
    grid_checks = {
        "C5_OFF_vs_C5_COUPLED": paired._verify_static_geometry(
            paths["C5_OFF_history"], paths["C5_COUPLED_history"]),
        "C7_OFF_vs_C7_COUPLED": paired._verify_static_geometry(
            paths["C7_OFF_history"], paths["C7_COUPLED_history"]),
        "C5_OFF_vs_C7_OFF": _verify_cross_case_static_geometry(
            paths["C5_OFF_history"], paths["C7_OFF_history"]),
        "C5_COUPLED_vs_C7_COUPLED": _verify_cross_case_static_geometry(
            paths["C5_COUPLED_history"], paths["C7_COUPLED_history"])}
    windows = {}
    for case, endpoint, indices in (("C5", 120, off5), ("C7", 180, off7)):
        for arm, mapping in (("OFF", off5 if case == "C5" else off7),
                             ("COUPLED", on5 if case == "C5" else on7)):
            path = paths[f"{case}_{arm}_history"]
            window = paired.native._receipt_window(
                paths[f"{case}_{arm}_receipt"], [path], sorted(mapping), endpoint, 60, False)
            windows[f"{case}_{arm}"] = window
    for case in ("C5", "C7"):
        if windows[f"{case}_OFF"]["run_start_timestamp"] != windows[f"{case}_COUPLED"]["run_start_timestamp"]:
            raise ValueError(f"{case} OFF and COUPLED history origins differ")
    if windows["C5_OFF"]["run_start_timestamp"] != windows["C7_OFF"]["run_start_timestamp"]:
        raise ValueError("C5 and C7 paired histories do not share the same run origin")
    d5 = _read_delta(paths["C5_OFF_history"], paths["C5_COUPLED_history"], off5, grid5,
                     COMMON_TIMES)
    d7 = _read_delta(paths["C7_OFF_history"], paths["C7_COUPLED_history"], off7, grid7,
                     C7_TIMES)
    if not (set(off5) == set(on5) and set(off7) == set(on7)):
        raise ValueError("paired arm timestamps differ within C5 or C7")
    if any(sorted(off5)[t // 60] != sorted(off7)[t // 60] for t in COMMON_TIMES):
        raise ValueError("C5 and C7 requested timestamps differ")
    with netCDF4.Dataset(paths["C7_OFF_history"]) as ds:
        lat, lon = np.asarray(ds.variables["XLAT"][0]), np.asarray(ds.variables["XLONG"][0])
    with netCDF4.Dataset(paths["C7_OFF_history"]) as ds_off, netCDF4.Dataset(paths["C7_COUPLED_history"]) as ds_on:
        support = np.zeros(grid7["shape"], dtype=bool)
        for name in paired.native.WATER:
            support |= np.any(np.asarray(ds_off.variables[name][0]) != np.asarray(ds_on.variables[name][0]), axis=0)
    masks = _masks(grid7, support)
    maps = _draw_maps(d7, lat, lon, support, output / "maps")
    interaction = {}
    for label, (_, units) in FIELDS.items():
        interaction[label] = {f"T{t}": {scope: _summary(_interaction_delta(d7[t][label], d5[t][label]), mask)
                                          for scope, mask in masks.items()} for t in COMMON_TIMES}
    transient = {}
    for label, (_, units) in FIELDS.items():
        field = {}
        values = {t: d7[t][label] for t in C7_TIMES}
        for scope, mask in masks.items():
            selection = np.broadcast_to(mask, values[0].shape)
            maxima = {}
            for t, array in values.items():
                k, j, i = np.unravel_index(np.argmax(np.where(selection, np.abs(array), -1)), array.shape)
                maximum = float(abs(array[k,j,i]))
                maxima[f"T{t}"] = {
                    "k": int(k) if maximum else None, "j": int(j) if maximum else None,
                    "i": int(i) if maximum else None,
                    "lat": float(lat[j,i]) if maximum else None,
                    "lon": float(lon[j,i]) if maximum else None,
                    "value": float(array[k,j,i]), "max_abs": maximum,
                    "location_status": "UNIQUE_MAX_LOCATION_REPORTED" if maximum else "ALL_SELECTED_VALUES_TIE_AT_ZERO"}
            field[scope] = maxima
        field["same_location_trajectory"] = {}
        all_candidates = np.stack([np.abs(values[t]) for t in C7_TIMES])
        _, k, j, i = np.unravel_index(int(np.argmax(all_candidates)), all_candidates.shape)
        for t in C7_TIMES:
            field["same_location_trajectory"][f"T{t}"] = float(values[t][k,j,i])
        field["same_location"] = {"k": int(k), "j": int(j), "i": int(i),
                                  "lat": float(lat[j,i]), "lon": float(lon[j,i]),
                                  "selection_rule": "global maximum |C7 COUPLED−OFF| over T0/T60/T120/T180 and all native levels/columns"}
        field["units"] = units
        transient[label] = field
    return {"schema": "pr91_history_response_v1", "physical_approval": False,
            "interaction_definition": "(C7 COUPLED−C7 OFF) − (C5 COUPLED−C5 OFF); run-variant interaction contrast, not a pure single-physics effect",
            "identity": identities, "interaction_elapsed_seconds": list(COMMON_TIMES),
            "C7_transient_elapsed_seconds": list(C7_TIMES),
            "receipt_windows": windows,
            "grid": {"mass_shape": list(grid7["shape"]), "dx_m": grid7["dx"], "dy_m": grid7["dy"],
                     "exact_grid_match_across_all_histories": True,
                     "cross_history_static_geometry_checks": grid_checks},
            "scopes": {k: {"horizontal_columns": int(v.sum()), "definition": k} for k,v in masks.items()},
            "C5_C7_interaction_delta_d": interaction, "C7_transient_maxima": transient,
            "C7_maps": maps,
            "interpretation_limits": ["WRF T is perturbation potential temperature and is not used as absolute air temperature.",
                                      "P+PB and PH+PHB remain native mass and vertically staggered arrays; W remains vertically staggered.",
                                      "No observation fit, continuity, initial-shock approval, or physical closure is established."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for case, endpoint in (("C5", 120), ("C7", 180)):
        for arm in ("OFF", "COUPLED"):
            parser.add_argument(f"--{case.lower()}-{arm.lower()}-history", type=Path, required=True)
            parser.add_argument(f"--{case.lower()}-{arm.lower()}-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {f"{case}_{arm}_{suffix}": getattr(args, f"{case.lower()}_{arm.lower()}_{suffix}")
             for case in ("C5", "C7") for arm in ("OFF", "COUPLED")
             for suffix in ("history", "receipt")}
    result = analyze(paths, args.output.parent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
