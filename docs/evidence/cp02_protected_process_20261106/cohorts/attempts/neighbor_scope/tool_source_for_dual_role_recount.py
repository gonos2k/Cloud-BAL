#!/usr/bin/env python3
"""Recount protected CP02 process cohorts and export native point stencils."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/cp02_protected_process_20261106/cohorts"
OLD_ANALYSIS = ROOT / "docs/evidence/weak_strong_balance_20261030/analysis"
GROUPED_ANALYSIS = ROOT / "docs/evidence/cp02_grouped_forecast_20261105/analysis"
PRIOR_MATCHED_CONTROLS = ROOT / "docs/evidence/cp02_failure_focus_20261105/targets/matched_controls.csv"
PLAN = ROOT / "docs/evidence/cp02_protected_process_20261106/analysis_plan.json"
PLAN_SHA256 = "c14da5350a21957eea0e320e5b6cb4da3c8ca82430c38b98cfc096c0c4b24d6f"
MAPPING = ROOT / "docs/evidence/cp02_rain_number_process_20261104/followup/analysis_dm065/bilinear_mapping.npz"
LAYER_FEATURES = ROOT / "docs/evidence/cp02_failure_focus_20261105/context/layer_features.csv"
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
HOURS = tuple(range(13, 19))
WEAK_LOW, WEAK_HIGH = 0.1, 1.0
EARTH_KM = 6371.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key].copy() for key in archive.files}


def validate_pair(old: dict[str, np.ndarray], grouped: dict[str, np.ndarray], label: str) -> None:
    required_old = {"reference", "latitude", "longitude", "flat_index_yx", "ORIGINAL", "FIXED_ORIGINAL_100", "ORIGINAL_B1_100", "IMPROVED_BG_FIXED"}
    required_new = {"reference", "latitude", "longitude", "flat_index_yx", "ORIGINAL", "A", "B", "C", "D"}
    if missing := required_old - old.keys():
        raise ValueError(f"{label}: old analysis arrays missing {sorted(missing)}")
    if missing := required_new - grouped.keys():
        raise ValueError(f"{label}: grouped analysis arrays missing {sorted(missing)}")
    for key in ("reference", "latitude", "longitude", "flat_index_yx"):
        if old[key].shape != (3688,) or grouped[key].shape != (3688,):
            raise ValueError(f"{label}: {key} must have 3688 canonical samples")
        if not np.array_equal(old[key], grouped[key]):
            raise ValueError(f"{label}: weak/strong and grouped arrays disagree on {key}")
    if len(np.unique(old["flat_index_yx"])) != 3688:
        raise ValueError(f"{label}: duplicated canonical RN1 flat IDs")
    for key in ("reference", "latitude", "longitude", "ORIGINAL", "FIXED_ORIGINAL_100", "ORIGINAL_B1_100", "IMPROVED_BG_FIXED"):
        if not np.isfinite(np.asarray(old[key], dtype=np.float64)).all():
            raise ValueError(f"{label}: nonfinite old array {key}")
    for key in ("reference", "ORIGINAL", "A", "B", "C", "D"):
        if not np.isfinite(np.asarray(grouped[key], dtype=np.float64)).all():
            raise ValueError(f"{label}: nonfinite grouped array {key}")


def categorical_score(obs: np.ndarray, forecast: np.ndarray, threshold: float) -> dict[str, int | float]:
    observed = obs >= threshold
    predicted = forecast >= threshold
    hit = int(np.count_nonzero(observed & predicted))
    miss = int(np.count_nonzero(observed & ~predicted))
    false_alarm = int(np.count_nonzero(~observed & predicted))
    correct_negative = int(np.count_nonzero(~observed & ~predicted))
    denominator = hit + miss + false_alarm
    return {"n": int(obs.size), "hit": hit, "miss": miss, "false_alarm": false_alarm,
            "correct_negative": correct_negative, "CSI": hit / denominator if denominator else float("nan")}


def transition_counts(obs: np.ndarray, before: np.ndarray, after: np.ndarray, threshold: float) -> dict[str, int]:
    observed = obs >= threshold
    old_hit, new_hit = before >= threshold, after >= threshold
    return {
        "observed_points": int(observed.sum()),
        "hit_gains": int(np.count_nonzero(observed & ~old_hit & new_hit)),
        "hit_losses": int(np.count_nonzero(observed & old_hit & ~new_hit)),
        "new_false_alarms": int(np.count_nonzero(~observed & ~old_hit & new_hit)),
        "resolved_false_alarms": int(np.count_nonzero(~observed & old_hit & ~new_hit)),
    }


def haversine_km(lat: np.ndarray, lon: np.ndarray, index: int) -> np.ndarray:
    lat_rad, lon_rad = np.radians(lat), np.radians(lon)
    dlat, dlon = lat_rad - lat_rad[index], lon_rad - lon_rad[index]
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat_rad[index]) * np.cos(lat_rad) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def neighborhood_counts(values: dict[str, np.ndarray], source: int, wet: np.ndarray) -> dict[int, tuple[int, int]]:
    distances = haversine_km(values["latitude"], values["longitude"], source)
    return {radius: (int(np.count_nonzero(distances <= radius)),
                     int(np.count_nonzero((distances <= radius) & wet))) for radius in (5, 10, 20)}


def domain_5km_singleton_count(values: dict[str, np.ndarray]) -> int:
    """Count canonical points whose 5 km RN1 neighborhood contains only itself."""
    flat = values["flat_index_yx"]
    return sum(int(np.count_nonzero(haversine_km(values["latitude"], values["longitude"], i) <= 5.0) == 1)
               for i in range(flat.size))


def nearest_neighbor(values: dict[str, np.ndarray], source: int, eligible: np.ndarray) -> tuple[int, float]:
    candidates = np.flatnonzero(eligible)
    candidates = candidates[candidates != source]
    if candidates.size == 0:
        raise ValueError("no eligible neighbor remains after excluding source point")
    distance = haversine_km(values["latitude"], values["longitude"], source)
    target = min(map(int, candidates), key=lambda i: (float(distance[i]), int(values["flat_index_yx"][i])))
    return target, float(distance[target])


def native_corners(values: dict[str, np.ndarray], mapping: dict[str, np.ndarray], point_indices: list[int]) -> list[dict]:
    flat = np.asarray(values["flat_index_yx"], dtype=np.int64)
    y, x = np.divmod(flat, 149)
    if flat.shape != (3688,) or np.any(y < 0) or np.any(y >= 253):
        raise ValueError("canonical sample IDs are outside the 253×149 RN1 crop")
    for key in ("j0", "i0", "u", "v", "valid"):
        if key not in mapping or mapping[key].shape != (253, 149):
            raise ValueError(f"native mapping has invalid {key} array")
    if not np.asarray(mapping["valid"])[y, x].all():
        raise ValueError("one or more selected points lack a valid native bilinear mapping")
    rows = []
    for index in point_indices:
        iy, ix = int(y[index]), int(x[index])
        j, i = int(mapping["j0"][iy, ix]) + 5, int(mapping["i0"][iy, ix]) + 74
        u, v = float(mapping["u"][iy, ix]), float(mapping["v"][iy, ix])
        cells = ((j, i), (j, i + 1), (j + 1, i), (j + 1, i + 1))
        weights = ((1-u)*(1-v), u*(1-v), (1-u)*v, u*v)
        if not np.isfinite(weights).all() or min(weights) < -1e-12 or abs(sum(weights) - 1.0) > 1e-12:
            raise ValueError(f"flat ID {int(flat[index])}: invalid native corner weights")
        for corner, (jj, ii), weight in zip(("00", "10", "01", "11"), cells, weights):
            rows.append({"flat_index_yx": int(flat[index]), "sample_index_zero_based": index, "corner": corner,
                         "native_j_zero_based": jj, "native_i_zero_based": ii,
                         "wrf_j_1based": jj + 1, "wrf_i_1based": ii + 1, "weight": float(weight)})
    return rows


def build_roles(old: dict[str, np.ndarray], old_plus5: dict[str, np.ndarray],
                grouped: dict[str, np.ndarray]) -> dict[str, dict[str, str]]:
    obs, old_ref, x, a = (old[key] for key in ("reference", "ORIGINAL", "ORIGINAL_B1_100", "IMPROVED_BG_FIXED"))
    weak = (obs >= WEAK_LOW) & (obs < WEAK_HIGH)
    dry = obs < WEAK_LOW
    masks: dict[str, np.ndarray] = {
        "plus2_XA_weak_gain": weak & (x < WEAK_LOW) & (a >= WEAK_LOW),
        "plus2_XA_weak_loss": weak & (x >= WEAK_LOW) & (a < WEAK_LOW),
        "plus2_OA_weak_loss": weak & (old_ref >= WEAK_LOW) & (a < WEAK_LOW),
        "plus2_XA_new_false_alarm": dry & (x < WEAK_LOW) & (a >= WEAK_LOW),
        "plus2_XA_resolved_false_alarm": dry & (x >= WEAK_LOW) & (a < WEAK_LOW),
        "plus2_OA_new_false_alarm": dry & (old_ref < WEAK_LOW) & (a >= WEAK_LOW),
        "plus2_OA_resolved_false_alarm": dry & (old_ref >= WEAK_LOW) & (a < WEAK_LOW),
    }
    prior_rows = list(csv.DictReader(PRIOR_MATCHED_CONTROLS.open(newline="", encoding="utf-8")))
    control_rows = [row for row in prior_rows if row["cohort_label"] == "h02_original_A_weak_hit_loss"
                    and row["control_state"] == "retained_hit" and row["valid_match"] == "True"]
    control_ids = {int(row["control_flat_index_yx"]) for row in control_rows}
    if len(control_ids) != 10:
        raise ValueError(f"expected exactly 10 frozen prior weak-loss controls; got {len(control_ids)}")
    prior_weak = weak
    control_membership = np.isin(old["flat_index_yx"], list(control_ids))
    if not np.array_equal(control_membership, control_membership & prior_weak & (old_ref >= WEAK_LOW) & (a >= WEAK_LOW)):
        raise ValueError("frozen OA weak-loss controls are not retained observed weak hits under ORIGINAL/A")
    masks["plus2_prior_retained_controls"] = np.isin(old["flat_index_yx"], list(control_ids))
    robs, rx, ra, rc = grouped["reference"], old_plus5["ORIGINAL_B1_100"], grouped["A"], grouped["C"]
    h5 = (robs >= 0.1) & (robs < 1.0) & (ra >= 0.1) & (rc < 0.1)
    masks["plus5_C_A_weak_loss"] = h5
    masks["plus5_protected_weak_X_miss_A_hit_C_miss"] = h5 & (rx < 0.1)
    masks["plus5_remaining_weak_loss_X_hit_A_hit_C_miss"] = h5 & (rx >= 0.1)
    masks["plus5_strong_protected_hit_12299"] = (grouped["flat_index_yx"] == 12299) & (robs >= 5.0) & (rx < 5.0) & (ra >= 5.0) & (rc < 5.0)
    c_fa = (robs < 5.0) & (ra < 5.0) & (rc >= 5.0)
    masks["plus5_C_strong_new_false_alarm"] = c_fa
    masks["plus5_protected_strong_X_FA_A_resolved_C_FA"] = c_fa & (rx >= 5.0)
    counts = {name: int(mask.sum()) for name, mask in masks.items()}
    expected = {"plus2_XA_weak_gain": 2, "plus2_XA_weak_loss": 10,
                "plus2_XA_new_false_alarm": 33, "plus2_XA_resolved_false_alarm": 30,
                "plus2_OA_weak_loss": 10,
                "plus2_OA_new_false_alarm": 53, "plus2_OA_resolved_false_alarm": 24,
                "plus2_prior_retained_controls": 10, "plus5_C_A_weak_loss": 17,
                "plus5_protected_weak_X_miss_A_hit_C_miss": 11,
                "plus5_remaining_weak_loss_X_hit_A_hit_C_miss": 6,
                "plus5_strong_protected_hit_12299": 1, "plus5_C_strong_new_false_alarm": 12,
                "plus5_protected_strong_X_FA_A_resolved_C_FA": 7}
    if counts != expected:
        raise ValueError(f"cohort counts differ from frozen targets: {counts}")
    return {name: {str(int(old["flat_index_yx"][i])): name for i in map(int, np.flatnonzero(mask))}
            for name, mask in masks.items()}


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty table {path}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(output: Path = EVIDENCE, old_dir: Path = OLD_ANALYSIS, grouped_dir: Path = GROUPED_ANALYSIS,
        mapping_path: Path = MAPPING) -> dict:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    if sha256(PLAN) != PLAN_SHA256:
        raise ValueError("frozen protected-process analysis plan hash mismatch")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    for relative, record in plan["frozen_source_pins"].items():
        pinned = ROOT / relative
        if not pinned.is_file() or sha256(pinned) != record["sha256"]:
            raise ValueError(f"analysis-plan source pin mismatch: {relative}")
    scores, transitions = [], []
    arrays_by_hour = {}
    for hour in HOURS:
        old = load_npz(Path(old_dir) / f"hour_{hour}_arrays.npz")
        grouped = load_npz(Path(grouped_dir) / f"hour_{hour}_arrays.npz")
        validate_pair(old, grouped, f"hour {hour}")
        arrays_by_hour[hour] = (old, grouped)
        pair_arrays = {"ORIGINAL_to_FIX": (old["ORIGINAL"], old["FIXED_ORIGINAL_100"]),
                       "X_to_A": (old["ORIGINAL_B1_100"], old["IMPROVED_BG_FIXED"]),
                       "ORIGINAL_to_A": (old["ORIGINAL"], old["IMPROVED_BG_FIXED"]),
                       "C_to_A": (grouped["C"], grouped["A"]),
                       "A_to_C": (grouped["A"], grouped["C"])}
        for pair, (before, after) in pair_arrays.items():
            for threshold in THRESHOLDS:
                scores.append({"valid_hour_utc": hour, "lead_hour": hour - 12, "comparison": pair,
                               "threshold_mm": threshold, **categorical_score(old["reference"], after, threshold)})
                transitions.append({"valid_hour_utc": hour, "lead_hour": hour - 12, "comparison": pair,
                                    "threshold_mm": threshold, **transition_counts(old["reference"], before, after, threshold)})
    old, _ = arrays_by_hour[14]
    old_plus5, _ = arrays_by_hour[17]
    _, grouped = arrays_by_hour[17]
    role_map = build_roles(old, old_plus5, grouped)
    oa_losses = np.flatnonzero((old["reference"] >= 0.1) & (old["reference"] < 1.0) &
                               (old["ORIGINAL"] >= 0.1) & (old["IMPROVED_BG_FIXED"] < 0.1))
    xa_losses = np.flatnonzero((old["reference"] >= 0.1) & (old["reference"] < 1.0) &
                               (old["ORIGINAL_B1_100"] >= 0.1) & (old["IMPROVED_BG_FIXED"] < 0.1))
    eligible_neighbors = old["IMPROVED_BG_FIXED"] >= 0.1
    rn1_zero_neighbors: set[int] = set()
    for index in map(int, oa_losses):
        neighbor, _ = nearest_neighbor(old, index, eligible_neighbors)
        if old["reference"][neighbor] == 0.0:
            rn1_zero_neighbors.add(int(old["flat_index_yx"][neighbor]))
    if len(rn1_zero_neighbors) != 4 or not {8540, 11091, 11092, 11241}.issubset(rn1_zero_neighbors):
        raise ValueError(f"OA nearest wet RN1-zero neighbor role changed: {sorted(rn1_zero_neighbors)}")
    role_map["plus2_OA_nearest_Awet_RN1zero_neighbor"] = {str(flat_id): "plus2_OA_nearest_Awet_RN1zero_neighbor"
                                                          for flat_id in rn1_zero_neighbors}
    point_roles: dict[str, list[str]] = {}
    for role, members in role_map.items():
        for flat in members:
            point_roles.setdefault(flat, []).append(role)
    points = []
    flat = old["flat_index_yx"]
    old_ix = {int(value): i for i, value in enumerate(flat)}
    grouped_h17 = arrays_by_hour[17][1]
    for flat_id in sorted(map(int, point_roles)):
        i = old_ix[flat_id]
        g = int(np.flatnonzero(grouped_h17["flat_index_yx"] == flat_id)[0])
        points.append({"point_id": f"RN1_{flat_id}", "flat_index_yx": flat_id, "sample_index_zero_based": i,
                       "latitude": float(old["latitude"][i]), "longitude": float(old["longitude"][i]),
                       "roles": ";".join(sorted(point_roles[str(flat_id)])),
                       "plus2_reference_mm": float(old["reference"][i]),
                       "plus2_X_mm": float(old["ORIGINAL_B1_100"][i]), "plus2_A_mm": float(old["IMPROVED_BG_FIXED"][i]),
                       "plus5_reference_mm": float(grouped_h17["reference"][g]), "plus5_X_mm": float(old_plus5["ORIGINAL_B1_100"][i]),
                       "plus5_A_mm": float(grouped_h17["A"][g]), "plus5_C_mm": float(grouped_h17["C"][g])})
    selected_indices = [old_ix[int(row["flat_index_yx"])] for row in points]
    mapping = load_npz(mapping_path)
    corner_rows = native_corners(old, mapping, selected_indices)
    # Stable native-cell IDs are globally deduplicated across all overlapping roles.
    cells = sorted({(int(row["native_j_zero_based"]), int(row["native_i_zero_based"])) for row in corner_rows})
    cell_ids = {cell: f"GC{k:04d}" for k, cell in enumerate(cells, 1)}
    point_id_by_flat = {int(row["flat_index_yx"]): row["point_id"] for row in points}
    role_by_flat = {int(row["flat_index_yx"]): row["roles"] for row in points}
    for row in corner_rows:
        cell = (row["native_j_zero_based"], row["native_i_zero_based"])
        row.update({"point_id": point_id_by_flat[row["flat_index_yx"]], "roles": role_by_flat[row["flat_index_yx"]],
                    "global_corner_id": cell_ids[cell]})
    unique_corners = [{"global_corner_id": cell_ids[cell], "native_j_zero_based": cell[0], "native_i_zero_based": cell[1],
                       "wrf_j_1based": cell[0] + 1, "wrf_i_1based": cell[1] + 1} for cell in cells]
    membership = [{"point_id": f"RN1_{flat_id}", "flat_index_yx": int(flat_id), "role": role}
                  for role, members in role_map.items() for flat_id in sorted(map(int, members))]
    qrain_rows, qrain_summary = layer_qrain_contrasts(role_map, LAYER_FEATURES)
    neighbors = []
    for role, indices in (("plus2_OA_weak_loss", oa_losses), ("plus2_XA_weak_loss", xa_losses)):
        for i in sorted(map(int, indices), key=lambda k: int(flat[k])):
            near, distance = nearest_neighbor(old, i, eligible_neighbors)
            radii = neighborhood_counts(old, i, eligible_neighbors)
            neighbors.append({"role": role, "loss_flat_index_yx": int(flat[i]), "nearest_A_hit_flat_index_yx": int(flat[near]),
                              "nearest_distance_km": distance, "loss_reference_mm": float(old["reference"][i]),
                              "loss_prior_ORIGINAL_mm": float(old["ORIGINAL"][i]),
                              "loss_X_mm": float(old["ORIGINAL_B1_100"][i]), "loss_A_mm": float(old["IMPROVED_BG_FIXED"][i]),
                              "neighbor_reference_mm": float(old["reference"][near]), "neighbor_X_mm": float(old["ORIGINAL_B1_100"][near]),
                              "neighbor_A_mm": float(old["IMPROVED_BG_FIXED"][near]),
                              **{f"canonical_points_within_{radius}km": counts[0] for radius, counts in radii.items()},
                              **{f"A_hit_points_within_{radius}km": counts[1] for radius, counts in radii.items()},
                              "5km_radius_self_only": radii[5][0] == 1})
    if len(oa_losses) != 10 or len(xa_losses) != 10 or len(neighbors) != 20:
        raise ValueError(f"expected 10 OA and 10 XA weak-loss neighborhood rows, got {len(oa_losses)}, {len(xa_losses)}")
    inputs = [*(Path(old_dir) / f"hour_{h}_arrays.npz" for h in HOURS),
              *(Path(grouped_dir) / f"hour_{h}_arrays.npz" for h in HOURS),
              PRIOR_MATCHED_CONTROLS, mapping_path, LAYER_FEATURES, PLAN, Path(__file__)]
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".protected-cohorts-", dir=output.parent))
    try:
        for name, rows in (("categorical_scores.csv", scores), ("transitions.csv", transitions), ("selected_points.csv", points),
                           ("role_membership.csv", membership), ("point_corners.csv", corner_rows),
                           ("unique_global_corners.csv", unique_corners), ("nearest_neighbors.csv", neighbors),
                           ("qrain_point_contrasts.csv", qrain_rows), ("qrain_group_summary.csv", qrain_summary)):
            write_csv(stage / name, rows)
        receipt = {"status": "COMPLETE", "hours_utc": list(HOURS), "thresholds_mm": list(THRESHOLDS),
                   "point_count_deduplicated": len(points), "role_membership_rows": len(membership),
                   "point_corner_rows": len(corner_rows), "unique_native_global_corners": len(cells),
                   "deduplicated_corner_overlap_count": len(corner_rows) - len(cells),
                   "nearest_neighbor_rows": len(neighbors),
                   "oa_zero_rn1_neighbor_flat_ids": sorted(rn1_zero_neighbors),
                   "plan_sha256": PLAN_SHA256,
                   "full_grid_5km_singleton_count": domain_5km_singleton_count(old),
                   "role_counts": {role: len(members) for role, members in role_map.items()},
                   "inputs": {str(path.relative_to(ROOT)): sha256(path) for path in inputs},
                   "outputs": {path.name: sha256(path) for path in sorted(stage.glob("*.csv"))},
                   "limitations": ["Cohort and score extraction uses frozen paired 3,688-point arrays.",
                                  "Native stencil indices/weights are reused from the pinned canonical bilinear mapping; runtime process state is not inferred.",
                                  "Neighborhood counts include the evaluated canonical point grid and describe geographic context only."]}
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return receipt


def layer_qrain_contrasts(role_map: dict[str, dict[str, str]], path: Path = LAYER_FEATURES) -> tuple[list[dict], list[dict]]:
    """Join frozen +2 OA loss/control identities to UTC13 lowest-layer QRAIN."""
    groups = {
        "plus2_OA_weak_loss": role_map["plus2_OA_weak_loss"],
        "plus2_prior_retained_controls": role_map["plus2_prior_retained_controls"],
    }
    needed = {flat: role for role, members in groups.items() for flat in members}
    values: dict[tuple[str, str], dict[str, float]] = {}
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            flat = row["flat_index_yx"]
            if flat not in needed or row["hour_utc"] != "13" or row["layer_agl"] != "[0,1000)m":
                continue
            if row["case"] not in {"A", "B1_OLD_KDM6"}:
                continue
            values.setdefault((needed[flat], flat), {})[row["case"]] = float(row["QRAIN_kgkg"]) * 1e6
    rows = []
    for (role, flat), cases in sorted(values.items(), key=lambda item: (item[0][0], int(item[0][1]))):
        if set(cases) != {"A", "B1_OLD_KDM6"}:
            raise ValueError(f"{role}/{flat}: expected both UTC13 QRAIN cases in layer_features.csv")
        rows.append({"role": role, "flat_index_yx": int(flat), "point_id": f"RN1_{flat}", "hour_utc": 13,
                     "layer_agl": "[0,1000)m", "X_case": "B1_OLD_KDM6", "A_case": "A",
                     "X_QRAIN_mgkg": cases["B1_OLD_KDM6"], "A_QRAIN_mgkg": cases["A"],
                     "pointwise_A_minus_X_mgkg": cases["A"] - cases["B1_OLD_KDM6"]})
    summary = []
    for role, members in groups.items():
        role_rows = [row for row in rows if row["role"] == role]
        if len(role_rows) != len(members):
            raise ValueError(f"{role}: layer feature join returned {len(role_rows)} of {len(members)} points")
        x = np.asarray([row["X_QRAIN_mgkg"] for row in role_rows], dtype=np.float64)
        a = np.asarray([row["A_QRAIN_mgkg"] for row in role_rows], dtype=np.float64)
        delta = a - x
        summary.append({"role": role, "n": len(role_rows), "median_X_QRAIN_mgkg": float(np.median(x)),
                        "median_A_QRAIN_mgkg": float(np.median(a)),
                        "median_pointwise_A_minus_X_mgkg": float(np.median(delta)),
                        "interpretation": "medians are calculated separately; delta is median of pointwise paired A−X values"})
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2))


if __name__ == "__main__":
    main()
