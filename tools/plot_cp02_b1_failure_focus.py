#!/usr/bin/env python3
"""Render receipt-bound CP02 failure-focus maps and exact CSI diagnostics."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import plot_cp02_grouped_forecast as grouped

ANALYSIS = ROOT / "docs/evidence/cp02_grouped_forecast_20261105/analysis"
OUTPUT = ROOT / "docs/evidence/cp02_failure_focus_20261105/figures"
TARGETS = ROOT / "docs/evidence/cp02_failure_focus_20261105/targets"
TARGET_PLAN = ROOT / "docs/evidence/cp02_failure_focus_20261105/analysis_plan.json"
STATE = ROOT / "docs/evidence/cp02_failure_focus_20261105/state/extracted"
TARGET_RECEIPT_SHA256 = "3ea1a834f61fa7a88c8f199c5ef8710298c489abc83c3c11965241d5dd7a420f"
STATE_RECEIPT_SHA256 = "39f1cede1e47b173491a47e5f4f0182ef7f682be834fbea0f0e1ab37889e23ba"
STATE_PLAN_SHA256 = "c3961eee66da7e1979d47baad64df15e75701ea586462b6b4a634c184d798c27"
CONTEXT = ROOT / "docs/evidence/cp02_failure_focus_20261105/context"
CONTEXT_RECEIPT_SHA256 = "a63d4b0d43f94b7456a9ebd8dde68b1616aec521f28bab04e73ee8d48c3e014e"
FONT = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")
FONT_SHA256 = "48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733"
WEAK = 0.1
STRONG = 5.0
SERIES_POINTS = (12737, 16479, 17492, 12299, 10942, 11093, 11242)
SERIES_LABELS = {
    12737: "+5 h weak hit loss, index 12737",
    16479: "+5 h weak hit loss, index 16479",
    17492: "+5 h 5 mm new false alarm, index 17492",
    12299: "+5 h 5 mm hit loss, index 12299",
    10942: "recovered +2 h index 10942",
    11093: "recovered +2 h index 11093",
    11242: "recovered +2 h index 11242",
}
COLORS = {"ORIGINAL": "#5c6066", "A": "#2166ac", "C": "#009e73"}
CASE_LABELS = {"ORIGINAL": "규준실험 (ORIGINAL)", "A": "현재 B1 (A)", "C": "합산식 후보 (C, 미채택)",
               "B1_OLD_KDM6": "B1_OLD_KDM6 (X, state diagnostic)"}


def configure_font() -> None:
    if not FONT.is_file() or sha256(FONT) != FONT_SHA256:
        raise ValueError("pinned local Nanum font is missing or changed")
    font_manager.fontManager.addfont(str(FONT))
    family = font_manager.FontProperties(fname=str(FONT)).get_name()
    plt.rcParams.update({"font.family": family, "axes.unicode_minus": False, "savefig.dpi": 130})


def sha256(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def verify_targets(folder: Path, hourly: dict[int, dict[str, np.ndarray]], analysis: Path,
                   masks: dict[str, np.ndarray], counts: dict[str, int | float]
                   ) -> tuple[dict, dict[str, set[int]], dict[str, set[int]], dict[str, str]]:
    folder = Path(folder)
    receipt_path = folder / "bundle_receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError("failure-focus target bundle receipt is missing or a symlink")
    if sha256(receipt_path) != TARGET_RECEIPT_SHA256:
        raise ValueError("failure-focus target bundle receipt differs from the reviewed output")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    plan_sha = sha256(TARGET_PLAN)
    if (receipt.get("schema") != "cp02_failure_focus_targets_v1" or receipt.get("status") != "COMPLETE"
            or receipt.get("analysis_plan_sha256") != plan_sha
            or receipt.get("source_receipt_sha256") != sha256(Path(analysis) / "receipt.json")
            or receipt.get("points_per_hour") != 3688 or receipt.get("lead_hours") != list(range(1, 7))
            or receipt.get("thresholds_mm") != [0.1, 0.5, 1.0, 2.5, 5.0, 10.0]
            or receipt.get("unique_focus_points") != 270 or receipt.get("matched_control_pairs") != 158
            or receipt.get("missing_control_pairs") != 0
            or receipt.get("reused_control_ids_across_cohorts") != 21):
        raise ValueError("failure-focus target bundle scope differs from the frozen plan/source")
    expected_files = {"focus_membership.csv", "event_membership.csv", "matched_controls.csv",
                      "control_reuse_audit.csv",
                      "transition_counts.csv", "temporal_diagnostics.csv", "temporal_cohort_summary.csv",
                      "spatial_neighbors.csv", "conditional_weak_detections.csv", "csi_algebra.csv",
                      "source_receipt.json"}
    outputs = receipt.get("outputs", {})
    if set(outputs) != expected_files:
        raise ValueError("failure-focus target output inventory is incomplete or unexpected")
    tables = {}
    for name, record in outputs.items():
        path = folder / name
        if (path.is_symlink() or not path.is_file() or path.stat().st_size != record.get("size_bytes")
                or sha256(path) != record.get("sha256") or Path(record.get("path", "")).name != name):
            raise ValueError(f"failure-focus target output hash mismatch: {name}")
        tables[name.removesuffix(".csv").removesuffix(".json")] = (
            read_csv(path) if name.endswith(".csv") else json.loads(path.read_text(encoding="utf-8")))
    source_record = tables["source_receipt"]
    if source_record.get("plan_sha256") != plan_sha:
        raise ValueError("target source receipt has a different analysis plan")
    source_files = source_record.get("files", [])
    required_source_names = {"analysis_plan.json", "cp02_b1_failure_targets.py", "receipt.json",
                             *(f"hour_{hour}_arrays.npz" for hour in range(13, 19))}
    if {Path(item.get("path", "")).name for item in source_files} != required_source_names:
        raise ValueError("target source receipt does not bind the plan, score receipt, and six arrays")
    for item in source_files:
        name = Path(item["path"]).name
        path = TARGET_PLAN if name == "analysis_plan.json" else (
            ROOT / "tools/cp02_b1_failure_targets.py" if name == "cp02_b1_failure_targets.py" else (
            Path(analysis) / name if name == "receipt.json" or name.endswith("_arrays.npz") else None)
            )
        if path is None or path.is_symlink() or not path.is_file() or path.stat().st_size != item.get("size_bytes") or sha256(path) != item.get("sha256"):
            raise ValueError(f"target source receipt input hash mismatch: {name}")

    point_to_index = {int(point): index for index, point in enumerate(hourly[13]["flat_index_yx"])}
    membership_rows = tables["focus_membership"]
    if len(membership_rows) != receipt.get("unique_focus_points") or len(membership_rows) != receipt.get("cohort_membership_rows"):
        raise ValueError("focus membership row count differs from the target receipt")
    labels_by_point: dict[int, set[str]] = {}
    for row in membership_rows:
        point = int(row["flat_index_yx"])
        if point in labels_by_point or point not in point_to_index:
            raise ValueError("focus membership has a duplicate or unknown paired point")
        index = point_to_index[point]
        if (int(row["point_index"]) != index
                or not np.isclose(float(row["latitude"]), hourly[13]["latitude"][index], rtol=0, atol=1e-12)
                or not np.isclose(float(row["longitude"]), hourly[13]["longitude"][index], rtol=0, atol=1e-12)):
            raise ValueError("focus membership point index or coordinates differ from the score arrays")
        labels = set(filter(None, row["cohort_labels"].split(";")))
        if not labels or row["is_control"].lower() not in ("true", "false"):
            raise ValueError("focus membership labels or control flag are invalid")
        if (row["is_control"].lower() == "true") != any(label.startswith("control_for:") for label in labels):
            raise ValueError("focus membership control flag differs from its role labels")
        labels_by_point[point] = labels

    label_masks = {
        "h02_original_A_weak_hit_loss": (masks["h2_weak_c_recovered"] | masks["h2_weak_still_lost"]),
        "h02_loss_recovered_by_C": masks["h2_weak_c_recovered"],
        "h02_loss_unrecovered_by_C": masks["h2_weak_still_lost"],
        "h02_original_A_weak_hit_gain": masks["h2_weak_gain"],
        "h02_original_A_new_FA": masks["h2_new_fa"],
        "h02_original_A_resolved_FA": masks["h2_resolved_fa"],
        "h05_A_C_5mm_new_FA": masks["h5_new_5mm_fa"],
        "h05_A_C_5mm_resolved_FA": masks["h5_resolved_5mm_fa"],
        "h05_A_C_5mm_hit_loss": masks["h5_5mm_hit_loss"],
        "h05_A_C_5mm_hit_gain": masks["h5_5mm_hit_gain"],
        "h05_A_C_weak_hit_loss": masks["h5_weak_c_lost"],
        "h05_A_C_weak_hit_gain": masks["h5_weak_c_gain"],
        "h06_A_C_weak_hit_loss": masks["h6_weak_c_lost"],
        "h06_A_C_weak_hit_gain": masks["h6_weak_c_gain"],
    }
    for label, mask in label_masks.items():
        actual = {int(hourly[13]["flat_index_yx"][index]) for index in np.flatnonzero(mask)}
        observed = {point for point, labels in labels_by_point.items() if label in labels}
        if actual != observed:
            raise ValueError(f"target cohort membership differs from paired-array recount: {label}")

    controls_by_cohort: dict[str, set[int]] = {}
    controls_rows = tables["matched_controls"]
    required_control_fields = {"cohort_label", "control_flat_index_yx", "control_state", "baseline_case",
                               "candidate_case", "valid_match"}
    if controls_rows and not required_control_fields.issubset(controls_rows[0]):
        raise ValueError("matched controls omit experiment identities")
    expected_case_pair = {
        "h02_original_A_weak_hit_loss": ("ORIGINAL", "A"),
        "h02_original_A_weak_hit_gain": ("ORIGINAL", "A"),
        "h02_original_A_new_FA": ("ORIGINAL", "A"),
        "h02_original_A_resolved_FA": ("ORIGINAL", "A"),
        "h02_loss_recovered_by_C": ("ORIGINAL", "A"),
        "h02_loss_unrecovered_by_C": ("ORIGINAL", "A"),
        "h05_A_C_5mm_new_FA": ("A", "C"),
        "h05_A_C_5mm_resolved_FA": ("A", "C"),
        "h05_A_C_5mm_hit_loss": ("A", "C"),
        "h05_A_C_5mm_hit_gain": ("A", "C"),
        "h05_A_C_weak_hit_loss": ("A", "C"),
        "h05_A_C_weak_hit_gain": ("A", "C"),
        "h06_A_C_weak_hit_loss": ("A", "C"),
        "h06_A_C_weak_hit_gain": ("A", "C"),
    }
    pairs = set()
    for row in controls_rows:
        target, control, cohort = int(row["target_flat_index_yx"]), int(row["control_flat_index_yx"]), row["cohort_label"]
        pair = (cohort, target)
        if pair in pairs or row["valid_match"].lower() != "true" or control not in point_to_index or target not in point_to_index:
            raise ValueError("matched-control row is invalid, missing, duplicated, or unpaired")
        pair_expected = expected_case_pair.get(cohort)
        if pair_expected is None:
            pair_expected = ("ORIGINAL", "A") if cohort.startswith("h02_") else ("A", "C")
        if (row["baseline_case"], row["candidate_case"]) != pair_expected:
            raise ValueError("matched-control case labels are outside the frozen diagnostic comparisons")
        if f"control_for:{cohort}" not in labels_by_point.get(control, set()):
            raise ValueError("matched-control point is missing its membership label")
        if (cohort in {"h02_original_A_weak_hit_loss", "h02_loss_recovered_by_C",
                       "h02_loss_unrecovered_by_C", "h05_A_C_weak_hit_loss"}
                and row["control_state"] != "retained_hit"):
            raise ValueError("weak-hit control is not classified as a retained hit")
        pairs.add(pair)
        controls_by_cohort.setdefault(cohort, set()).add(control)
    if len(controls_rows) != receipt.get("matched_control_pairs") or receipt.get("missing_control_pairs") != 0:
        raise ValueError("matched-control coverage differs from the target receipt")
    reuse_rows = tables["control_reuse_audit"]
    control_use = {}
    for cohort, ids in controls_by_cohort.items():
        for control in ids:
            control_use.setdefault(control, []).append(cohort)
    expected_reuse = {point: cohorts for point, cohorts in control_use.items() if len(cohorts) > 1}
    actual_reuse = {int(row["control_flat_index_yx"]): row for row in reuse_rows}
    if set(actual_reuse) != set(expected_reuse) or len(expected_reuse) != receipt.get("reused_control_ids_across_cohorts"):
        raise ValueError("matched-control reuse audit differs from the pair table")
    for point, cohorts in expected_reuse.items():
        row = actual_reuse[point]
        if int(row["reuse_count"]) != len(cohorts) or set(row["cohort_labels"].split(";")) != set(cohorts):
            raise ValueError("matched-control reuse audit has an incorrect cohort list")
    grouped_controls = {
        "h2_weak_matched_controls": set().union(*(controls_by_cohort.get(label, set()) for label in (
            "h02_original_A_weak_hit_loss", "h02_loss_recovered_by_C", "h02_loss_unrecovered_by_C"))),
        "h5_strong_matched_controls": set().union(*(controls_by_cohort.get(label, set()) for label in (
            "h05_A_C_5mm_new_FA", "h05_A_C_5mm_resolved_FA", "h05_A_C_5mm_hit_loss"))),
        "h5_weak_matched_controls": controls_by_cohort.get("h05_A_C_weak_hit_loss", set()),
    }
    algebra_rows = tables["csi_algebra"]
    algebra = [row for row in algebra_rows if int(row["lead_hour"]) == 5
               and float(row["threshold_mm"]) == STRONG and row["contrast"] == "C-A"]
    if len(algebra) != 1:
        raise ValueError("target CSI algebra table does not have one +5 h, 5 mm C-A row")
    row = algebra[0]
    for key, expected in (("observed_O_H_plus_M", counts["h5_reference_count"]),
                          ("A_H", counts["h5_A_hit_count"]), ("A_F", counts["h5_A_fa_count"]),
                          ("C_H", counts["h5_C_hit_count"]), ("C_F", counts["h5_C_fa_count"])):
        if int(row[key]) != expected:
            raise ValueError(f"target CSI algebra count differs from recount: {key}")
    if Fraction(row["restored_baseline_hit_with_candidate_F_exact_CSI"]) != Fraction(110, 564):
        raise ValueError("hit-only repair exact fraction differs from 110/564")
    if not np.isclose(float(row["A_H_with_candidate_F_CSI"]), 110 / 564, rtol=0, atol=1e-15):
        raise ValueError("hit-only repair decimal differs from the exact fraction")
    if not np.isclose(float(row["candidate_H_with_A_F_CSI"]), 109 / 553, rtol=0, atol=1e-15):
        raise ValueError("candidate-hit-only counterfactual differs from 109/553")
    delta_csi = Fraction(109, 564) - Fraction(110, 553)
    if (Fraction(row["delta_CSI_reconstructed"]) != delta_csi
            or Fraction(row["delta_CSI_recount"]) != delta_csi
            or Fraction(row["hit_algebra_term"]) + Fraction(row["false_alarm_algebra_term"]) != delta_csi
            or row["hit_only_repair_below_A_with_candidate_F"].lower() != "true"):
        raise ValueError("target CSI decomposition or hit-only repair gate differs from exact recount")
    return receipt, label_masks, grouped_controls, row


def load_state_bundle(folder: Path, hourly: dict[int, dict[str, np.ndarray]],
                      target_receipt: dict) -> tuple[dict[tuple[str, int], dict[str, np.ndarray]], dict]:
    folder = Path(folder)
    plan_path = folder.parent / "extraction_plan.json"
    proposal_path = folder.parent / "inputs_proposal.json"
    receipt_path = folder / "receipt.json"
    if (plan_path.is_symlink() or not plan_path.is_file() or sha256(plan_path) != STATE_PLAN_SHA256
            or proposal_path.is_symlink() or not proposal_path.is_file()
            or receipt_path.is_symlink() or not receipt_path.is_file()
            or sha256(receipt_path) != STATE_RECEIPT_SHA256):
        raise ValueError("state bundle receipt is missing or differs from the verified extraction")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    cases = ("ORIGINAL", "A", "C", "B1_OLD_KDM6")
    hours = tuple(range(12, 19))
    if (receipt.get("status") != "PASS" or receipt.get("cases") != list(cases)
            or receipt.get("hours_utc") != list(hours) or receipt.get("points") != 270
            or receipt.get("levels") != 39 or receipt.get("plan_sha256") != STATE_PLAN_SHA256
            or receipt.get("inputs_proposal_sha256") != sha256(proposal_path)
            or receipt.get("targets_receipt_sha256") != sha256(TARGETS / "bundle_receipt.json")
            or receipt.get("membership_sha256") != target_receipt["outputs"]["focus_membership.csv"]["sha256"]
            or receipt.get("matched_controls_sha256") != target_receipt["outputs"]["matched_controls.csv"]["sha256"]):
        raise ValueError("state extraction scope differs from the reviewed plan and target bundle")
    expected = {(case, hour) for case in cases for hour in hours}
    records = {(row["case"], int(row["hour_utc"])): row for row in receipt.get("records", [])}
    if len(records) != len(expected) or set(records) != expected:
        raise ValueError("state bundle does not contain the complete four-case, seven-hour grid")
    membership = read_csv(TARGETS / "focus_membership.csv")
    membership_by_id = {int(row["flat_index_yx"]): row for row in membership}
    score_positions = {int(point): index for index, point in enumerate(hourly[13]["flat_index_yx"])}
    states = {}
    for key, record in records.items():
        path = folder / record["output"]
        if (path.name != record["output"] or path.is_symlink() or not path.is_file()
                or path.stat().st_size != record.get("output_size_bytes")
                or sha256(path) != record.get("output_sha256")):
            raise ValueError(f"state output hash mismatch: {record.get('output')}")
        with np.load(path, allow_pickle=False) as archive:
            required = {"flat_index_yx", "latitude", "longitude", "weighted_raw_QVAPOR", "weighted_raw_QRAIN",
                        "weighted_raw_QNRAIN", "weighted_temperature_K", "weighted_rh_liquid",
                        "corner_weights", "corner_height_agl_m", "corner_QVAPOR", "corner_QRAIN",
                        "corner_rh_liquid",
                        "weighted_rainc_increment_mm", "weighted_rainnc_increment_mm"}
            if not required.issubset(archive.files):
                raise ValueError(f"state output omits required weighted fields: {path.name}")
            values = {name: np.array(archive[name], copy=True) for name in required}
        ids = values["flat_index_yx"]
        if ids.shape != (270,) or len(np.unique(ids)) != 270 or set(map(int, ids)) != set(membership_by_id):
            raise ValueError(f"state point membership differs from focus membership: {path.name}")
        if not np.issubdtype(ids.dtype, np.integer):
            raise ValueError(f"state point IDs are not integers: {path.name}")
        for index, point in enumerate(map(int, ids)):
            row = membership_by_id[point]
            if (not np.isclose(values["latitude"][index], float(row["latitude"]), rtol=0, atol=1e-12)
                    or not np.isclose(values["longitude"][index], float(row["longitude"]), rtol=0, atol=1e-12)):
                raise ValueError(f"state point coordinates differ from focus membership: {path.name}")
        for name in ("weighted_raw_QVAPOR", "weighted_raw_QRAIN", "weighted_raw_QNRAIN",
                     "weighted_temperature_K", "weighted_rh_liquid"):
            if values[name].shape != (270, 39) or not np.isfinite(values[name]).all():
                raise ValueError(f"invalid state field {name}: {path.name}")
        for name in ("weighted_rainc_increment_mm", "weighted_rainnc_increment_mm"):
            if values[name].shape != (270,) or (key[1] > 12 and not np.isfinite(values[name]).all()):
                raise ValueError(f"invalid state surface increment {name}: {path.name}")
        states[key] = values

    for case in ("ORIGINAL", "A", "C"):
        for hour in range(13, 19):
            state = states[case, hour]
            score_hour = hourly[hour]
            for point_index, point in enumerate(map(int, state["flat_index_yx"])):
                score_index = score_positions[point]
                surface = state["weighted_rainc_increment_mm"][point_index] + state["weighted_rainnc_increment_mm"][point_index]
                if not np.isclose(surface, score_hour[case][score_index], rtol=1e-12, atol=1e-10):
                    raise ValueError(f"state surface increment differs from scored {case}/h{hour}: {point}")
    return states, receipt


def focus_masks(hourly: dict[int, dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    h2, h5, h6 = hourly[14], hourly[17], hourly[18]
    obs2, old2, a2, c2 = h2["reference"], h2["ORIGINAL"], h2["A"], h2["C"]
    obs5, a5, c5 = h5["reference"], h5["A"], h5["C"]
    weak2 = (obs2 >= WEAK) & (obs2 < 1.0) & (old2 >= WEAK)
    dry2 = obs2 < WEAK
    weak5 = (obs5 >= WEAK) & (obs5 < 1.0)
    dry5 = obs5 < STRONG
    heavy5 = obs5 >= STRONG
    weak6 = (h6["reference"] >= WEAK) & (h6["reference"] < 1.0)
    return {
        "h2_weak_c_recovered": weak2 & (a2 < WEAK) & (c2 >= WEAK),
        "h2_weak_still_lost": weak2 & (a2 < WEAK) & (c2 < WEAK),
        "h2_weak_retained": weak2 & (a2 >= WEAK) & (c2 >= WEAK),
        "h2_weak_gain": (obs2 >= WEAK) & (obs2 < 1.0) & (old2 < WEAK) & (a2 >= WEAK),
        "h2_new_fa": dry2 & (old2 < WEAK) & (a2 >= WEAK),
        "h2_resolved_fa": dry2 & (old2 >= WEAK) & (a2 < WEAK),
        "h5_new_5mm_fa": dry5 & (a5 < STRONG) & (c5 >= STRONG),
        "h5_resolved_5mm_fa": dry5 & (a5 >= STRONG) & (c5 < STRONG),
        "h5_5mm_hit_loss": heavy5 & (a5 >= STRONG) & (c5 < STRONG),
        "h5_5mm_hit_gain": heavy5 & (a5 < STRONG) & (c5 >= STRONG),
        "h5_weak_c_lost": weak5 & (a5 >= WEAK) & (c5 < WEAK),
        "h5_weak_retained": weak5 & (a5 >= WEAK) & (c5 >= WEAK),
        "h5_weak_c_gain": weak5 & (a5 < WEAK) & (c5 >= WEAK),
        "h6_weak_c_lost": weak6 & (h6["A"] >= WEAK) & (h6["C"] < WEAK),
        "h6_weak_c_gain": weak6 & (h6["A"] < WEAK) & (h6["C"] >= WEAK),
    }


def exact_counts(hourly: dict[int, dict[str, np.ndarray]]) -> dict[str, int | float]:
    masks = focus_masks(hourly)
    h5 = hourly[17]
    reference, baseline, candidate = h5["reference"], h5["A"], h5["C"]
    obs, old, new = reference >= STRONG, baseline >= STRONG, candidate >= STRONG
    hit_a, miss_a, fa_a = (int(np.count_nonzero(obs & old)), int(np.count_nonzero(obs & ~old)),
                           int(np.count_nonzero(~obs & old)))
    hit_c, miss_c, fa_c = (int(np.count_nonzero(obs & new)), int(np.count_nonzero(obs & ~new)),
                           int(np.count_nonzero(~obs & new)))
    denominator_a = hit_a + miss_a + fa_a
    denominator_c = hit_c + miss_c + fa_c
    if not denominator_a or not denominator_c:
        raise ValueError("5 mm CSI denominator is empty")
    delta_hit, delta_fa = hit_c - hit_a, fa_c - fa_a
    csi_delta_denominator = denominator_a * denominator_c
    csi_delta_hit_numerator = delta_hit * denominator_a
    csi_delta_fa_numerator = -hit_a * delta_fa
    counts = {name: int(mask.sum()) for name, mask in masks.items()}
    counts.update({"h5_A_hit": hit_a, "h5_A_miss": miss_a, "h5_A_fa": fa_a,
                   "h5_C_hit": hit_c, "h5_C_miss": miss_c, "h5_C_fa": fa_c,
                   "h5_reference_count": int(np.count_nonzero(obs)),
                   "h5_A_hit_count": hit_a, "h5_A_fa_count": fa_a,
                   "h5_C_hit_count": hit_c, "h5_C_fa_count": fa_c,
                   "h5_A_denominator": denominator_a, "h5_C_denominator": denominator_c,
                   "h5_delta_hit": delta_hit, "h5_delta_fa": delta_fa,
                   "h5_csi_delta_hit_numerator": csi_delta_hit_numerator,
                   "h5_csi_delta_fa_numerator": csi_delta_fa_numerator,
                   "h5_csi_delta_numerator": csi_delta_hit_numerator + csi_delta_fa_numerator,
                   "h5_csi_delta_denominator": csi_delta_denominator,
                   "h5_CSI_delta": (hit_c / denominator_c) - (hit_a / denominator_a),
                   "h5_A_CSI": hit_a / denominator_a, "h5_C_CSI": hit_c / denominator_c,
                   "h5_hit_only_repair_CSI": hit_a / (hit_a + miss_a + fa_c)})
    expected = {"h2_weak_c_recovered": 3, "h2_weak_still_lost": 7,
                "h2_new_fa": 53, "h2_resolved_fa": 24,
                "h5_new_5mm_fa": 12, "h5_resolved_5mm_fa": 1,
                "h5_5mm_hit_loss": 1, "h5_5mm_hit_gain": 0,
                "h5_weak_c_lost": 17}
    for name, value in expected.items():
        if counts[name] != value:
            raise ValueError(f"recount mismatch for {name}: expected {value}, found {counts[name]}")
    if hit_a - hit_c != 1 or fa_c - fa_a != 11:
        raise ValueError("5 mm C-A hit/false-alarm deltas differ from the frozen target")
    return counts


def point_mask(values: dict[str, np.ndarray], flat_ids: set[int]) -> np.ndarray:
    return np.isin(values["flat_index_yx"], np.fromiter(flat_ids, dtype=np.int64))


def draw_map(ax, longitude: np.ndarray, latitude: np.ndarray,
             categories: tuple[tuple[np.ndarray, str, str, str, bool], ...],
             coast: list[np.ndarray]) -> None:
    ax.scatter(longitude, latitude, s=2, color="#d8dde1", alpha=.55, linewidths=0,
               rasterized=True, label="All paired grid points")
    for mask, label, color, marker, hollow in categories:
        if np.any(mask):
            style = {"facecolors": "none", "edgecolors": color} if hollow else {
                "color": color, "edgecolors": "white"}
            ax.scatter(longitude[mask], latitude[mask], s=30, marker=marker,
                       linewidths=.8 if hollow else .35, rasterized=True,
                       label=f"{label} (n={int(mask.sum())})", **style)
    for line in coast:
        ax.plot(line[:, 0], line[:, 1], color="#687780", linewidth=.55, alpha=.8)
    ax.set_xlabel("Longitude (degrees east)")
    ax.set_ylabel("Latitude (degrees north)")
    ax.set_xlim(float(longitude.min()), float(longitude.max()))
    ax.set_ylim(float(latitude.min()), float(latitude.max()))
    ax.set_aspect(1.0 / np.cos(np.deg2rad(float(latitude.mean()))), adjustable="box")
    ax.grid(alpha=.12)
    ax.legend(loc="best", fontsize=7, framealpha=.95)


def draw_weak_map(hourly, masks, coast, output: Path) -> None:
    values = hourly[14]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    draw_map(axes[0], values["longitude"], values["latitude"], (
        (masks["h02_loss_recovered_by_C"], "C restored", "#009e73", "o", False),
        (masks["h02_loss_unrecovered_by_C"], "Still missed by C", "#d55e00", "s", False),
        (masks["h2_weak_matched_controls"], "Matched retained-hit controls", "#222222", "o", True),
    ), coast)
    axes[0].set_title("+2 h weak observed rain, threshold 0.1 mm\n규준실험 (ORIGINAL) hits lost by current B1 (A); C partitions losses")
    draw_map(axes[1], values["longitude"], values["latitude"], (
        (masks["h02_original_A_new_FA"], "New false alarm in A", "#d55e00", "o", False),
        (masks["h02_original_A_resolved_FA"], "False alarm resolved in A", "#009e73", "s", False),
    ), coast)
    axes[1].set_title("+2 h observations below 0.1 mm\nORIGINAL to A false alarm transitions")
    fig.suptitle("Post hoc transition locations; categories describe this diagnostic only")
    fig.savefig(output, dpi=180, metadata={"Software": "plot_cp02_b1_failure_focus"})
    plt.close(fig)


def draw_h5_map(hourly, masks, coast, output: Path) -> None:
    values = hourly[17]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    draw_map(axes[0], values["longitude"], values["latitude"], (
        (masks["h05_A_C_5mm_new_FA"], "New 5 mm false alarm", "#d55e00", "o", False),
        (masks["h05_A_C_5mm_resolved_FA"], "5 mm false alarm resolved", "#009e73", "s", False),
        (masks["h05_A_C_5mm_hit_loss"], "5 mm hit lost", "#cc3311", "D", False),
        (masks["h05_A_C_5mm_hit_gain"], "5 mm hit gained", "#0077bb", "^", False),
        (masks["h5_strong_matched_controls"], "Matched transition controls", "#222222", "o", True),
    ), coast)
    axes[0].set_title("+5 h, threshold 5 mm\n합산식 후보 (C, 미채택) compared with 현재 B1 (A)")
    draw_map(axes[1], values["longitude"], values["latitude"], (
        (masks["h05_A_C_weak_hit_loss"], "Weak hit lost in C", "#d55e00", "o", False),
        (masks["h5_weak_matched_controls"], "Matched retained-hit controls", "#222222", "o", True),
    ), coast)
    axes[1].set_title("+5 h weak observed rain, threshold 0.1 mm\n합산식 후보 (C, 미채택) compared with 현재 B1 (A)")
    fig.suptitle("Post hoc transition locations; not a transport or evaporation diagnosis")
    fig.savefig(output, dpi=180, metadata={"Software": "plot_cp02_b1_failure_focus"})
    plt.close(fig)


def draw_csi_algebra(counts: dict[str, int | float], output: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 7), constrained_layout=True)
    ax.axis("off")
    h_a, m_a, f_a = counts["h5_A_hit"], counts["h5_A_miss"], counts["h5_A_fa"]
    h_c, m_c, f_c = counts["h5_C_hit"], counts["h5_C_miss"], counts["h5_C_fa"]
    ax.text(.5, .92, "+5 h, 5 mm: exact CSI transition accounting", ha="center", va="center",
            transform=ax.transAxes, fontsize=18, weight="bold")
    ax.text(.5, .83, "CSI = H / (H + M + F)", ha="center", transform=ax.transAxes, fontsize=17)
    ax.text(.05, .68, f"현재 B1 (A): H={h_a}, M={m_a}, F={f_a}\nCSI = {h_a} / ({h_a} + {m_a} + {f_a}) = {counts['h5_A_CSI']:.6f}",
            ha="left", va="center", transform=ax.transAxes, fontsize=13,
            bbox={"boxstyle": "round,pad=.6", "facecolor": "#e8f0f8", "edgecolor": "#2166ac"})
    ax.text(.95, .68, f"합산식 후보 (C, 미채택): H={h_c}, M={m_c}, F={f_c}\nCSI = {h_c} / ({h_c} + {m_c} + {f_c}) = {counts['h5_C_CSI']:.6f}",
            ha="right", va="center", transform=ax.transAxes, fontsize=13,
            bbox={"boxstyle": "round,pad=.6", "facecolor": "#e8f4ee", "edgecolor": "#009e73"})
    ax.text(.5, .48, "C - A transitions: hit gain 0, hit loss 1, new false alarms 12, resolved false alarms 1\n"
            f"ΔH = {counts['h5_delta_hit']}, ΔF = {counts['h5_delta_fa']}; O = H + M = {h_a + m_a}",
            ha="center", va="center", transform=ax.transAxes, fontsize=11)
    ax.text(.5, .31, "ΔCSI = [ΔH(O + F_A) - H_A ΔF] / [(O + F_A)(O + F_C)]\n"
            f"= [{counts['h5_csi_delta_hit_numerator']} + ({counts['h5_csi_delta_fa_numerator']})] / "
            f"({counts['h5_A_denominator']} x {counts['h5_C_denominator']})\n"
            f"= {counts['h5_csi_delta_numerator']} / {counts['h5_csi_delta_denominator']} "
            f"= {counts['h5_CSI_delta']:.6f}",
            ha="center", va="center", transform=ax.transAxes, fontsize=11)
    ax.text(.5, .12, f"Hit-only repair (restore A's one hit; keep C's F): {h_a} / ({h_a + m_a} + {f_c}) "
            f"= {h_a}/{h_a + m_a + f_c} = {Fraction(h_a, h_a + m_a + f_c)} "
            f"= {counts['h5_hit_only_repair_CSI']:.6f} < A CSI {counts['h5_A_CSI']:.6f}",
            ha="center", va="center", transform=ax.transAxes, fontsize=11,
            bbox={"boxstyle": "round,pad=.5", "facecolor": "#fff5e6", "edgecolor": "#bf6b00"})
    ax.text(.5, .025, "Count decomposition is arithmetic, not a physical causal attribution. 5 mm false alarm count does not mean new rain area.",
            ha="center", va="center", transform=ax.transAxes, fontsize=8, color="#7a2e2e")
    fig.savefig(output, dpi=180, metadata={"Software": "plot_cp02_b1_failure_focus"})
    plt.close(fig)


def draw_point_paths(hourly, states, output: Path) -> None:
    first = hourly[13]
    indices = first["flat_index_yx"]
    positions = {int(point): int(np.flatnonzero(indices == point)[0])
                 for point in SERIES_POINTS if np.any(indices == point)}
    missing = set(SERIES_POINTS) - set(positions)
    if missing:
        raise ValueError(f"selected point IDs are missing from paired arrays: {sorted(missing)}")
    amounts = [float(hourly[12 + lead][case][positions[point]])
               for point in SERIES_POINTS for lead in range(1, 7)
               for case in ("reference", "ORIGINAL", "A", "C")]
    for lead in range(1, 7):
        state = states[("B1_OLD_KDM6", 12 + lead)]
        state_positions = {int(point): index for index, point in enumerate(state["flat_index_yx"])}
        amounts.extend(float(state["weighted_rainc_increment_mm"][state_positions[point]]
                             + state["weighted_rainnc_increment_mm"][state_positions[point]])
                       for point in SERIES_POINTS)
    maximum = max(amounts)
    upper = max(0.1, maximum)
    ticks = [value for value in (0, 0.1, 0.5, 1, 2.5, 5, 10, 20, 50, 100) if value <= upper]
    if ticks[-1] < upper:
        ticks.append(upper)
    fig, axes = plt.subplots(2, 4, figsize=(16, 8), sharex=True, sharey=True, constrained_layout=True)
    hours = tuple(range(1, 7))
    for ax, point in zip(axes.flat, SERIES_POINTS):
        index = positions[point]
        for case in ("reference", "ORIGINAL", "A", "C", "B1_OLD_KDM6"):
            label = "RN1 기준량" if case == "reference" else CASE_LABELS[case]
            color = ("#111111" if case == "reference" else
                     ("#cc79a7" if case == "B1_OLD_KDM6" else COLORS[case]))
            style = "--" if case == "reference" else (":" if case == "B1_OLD_KDM6" else "-")
            values = []
            for lead in hours:
                if case == "B1_OLD_KDM6":
                    state = states[(case, 12 + lead)]
                    state_index = int(np.flatnonzero(state["flat_index_yx"] == point)[0])
                    amount = (state["weighted_rainc_increment_mm"][state_index]
                              + state["weighted_rainnc_increment_mm"][state_index])
                    values.append(float(amount))
                else:
                    values.append(hourly[12 + lead][case][index])
            ax.plot(hours, values, marker="o",
                    linewidth=1.5, markersize=3, color=color, linestyle=style, label=label)
        for threshold in (0.1, 1.0, 5.0):
            ax.axhline(threshold, color="#777777", linewidth=.6, alpha=.45)
        ax.set_title(SERIES_LABELS[point], fontsize=9)
        ax.set_xticks(hours, [f"+{hour}" for hour in hours])
        ax.set_yscale("symlog", linthresh=0.1, linscale=1)
        ax.set_ylim(0, upper)
        ax.set_yticks(ticks)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        ax.grid(alpha=.2)
    axes.flat[-1].axis("off")
    axes[0, 0].set_ylabel("One-hour rain increment (mm)")
    axes[1, 0].set_ylabel("One-hour rain increment (mm)")
    axes[0, 0].legend(frameon=False, fontsize=7)
    fig.suptitle("Selected paired point paths across six hourly increments\nX=B1_OLD_KDM6 is a state-only diagnostic; no spatial or CSI averaging")
    fig.savefig(output, dpi=180, metadata={"Software": "plot_cp02_b1_failure_focus"})
    plt.close(fig)


def load_context(folder: Path, target_receipt: dict, state_receipt: dict) -> tuple[list[dict], dict]:
    folder = Path(folder)
    receipt_path = folder / "bundle_receipt.json"
    if (receipt_path.is_symlink() or not receipt_path.is_file()
            or sha256(receipt_path) != CONTEXT_RECEIPT_SHA256):
        raise ValueError("failure-focus context receipt is missing or differs from the reviewed bundle")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (receipt.get("schema") != "cp02_b1_failure_context_v1" or receipt.get("status") != "COMPLETE"
            or receipt.get("state_receipt_sha256") != sha256(STATE / "receipt.json")
            or receipt.get("state_plan_sha256") != STATE_PLAN_SHA256
            or receipt.get("target_receipt_sha256") != sha256(TARGETS / "bundle_receipt.json")
            or receipt.get("focus_points") != 270 or receipt.get("matched_control_rows") != 158):
        raise ValueError("context bundle scope differs from the verified state and target bundles")
    output_records = receipt.get("outputs", {})
    expected_outputs = {"point_surface_paths.csv", "layer_features.csv", "cohort_physical_contrasts.csv",
                        "cohort_surface_context.csv", "cohort_surface_context_summary.csv"}
    if set(output_records) != expected_outputs:
        raise ValueError("context bundle output inventory differs from its frozen schema")
    expected_sources = {"receipt.json": STATE / "receipt.json",
                        "extraction_plan.json": STATE.parent / "extraction_plan.json",
                        "bundle_receipt.json": TARGETS / "bundle_receipt.json",
                        "source_receipt.json": TARGETS / "source_receipt.json"}
    sources = receipt.get("sources", [])
    source_by_name = {Path(row.get("path", "")).name: row for row in sources}
    if len(source_by_name) != len(sources) or not set(expected_sources).issubset(source_by_name):
        raise ValueError("context receipt omits or duplicates a local provenance identity")
    for name, path in expected_sources.items():
        record = source_by_name[name]
        if (path.is_symlink() or not path.is_file() or sha256(path) != record.get("sha256")
                or path.stat().st_size != record.get("size_bytes")):
            raise ValueError(f"context provenance source differs: {name}")
    for name, record in output_records.items():
        path = folder / name
        if (path.name != name or path.is_symlink() or not path.is_file()
                or path.stat().st_size != record.get("size_bytes") or sha256(path) != record.get("sha256")):
            raise ValueError(f"context output hash mismatch: {name}")
    rows = read_csv(folder / "layer_features.csv")
    if len(rows) != 270 * 4 * 7 * 2:
        raise ValueError("context layer feature table has unexpected row coverage")
    keys = set()
    focus = read_csv(TARGETS / "focus_membership.csv")
    membership = {int(row["flat_index_yx"]): row for row in focus}
    if len(membership) != 270:
        raise ValueError("target focus membership is not a unique 270 point table")
    layer_names = ("[0,1000)m", "[1000,3000)m")
    for row in rows:
        point = int(row["flat_index_yx"])
        key = (point, row["case"], int(row["hour_utc"]), row["layer_agl"])
        if key in keys:
            raise ValueError("context layer feature table has duplicate point/case/hour/layer keys")
        if (point not in membership or row["case"] not in ("ORIGINAL", "A", "C", "B1_OLD_KDM6")
                or not 12 <= int(row["hour_utc"]) <= 18 or row["layer_agl"] not in layer_names):
            raise ValueError("context layer feature table has an unexpected layer label")
        member = membership[point]
        if (row["cohort_labels"] != member["cohort_labels"]
                or row["is_control"].lower() != member["is_control"].lower()
                or int(row["point_index"]) != int(member["point_index"])):
            raise ValueError("context membership columns differ from the sealed target membership")
        keys.add(key)
    required_keys = {(int(point), case, hour, layer)
                     for point in [int(row["flat_index_yx"]) for row in read_csv(TARGETS / "focus_membership.csv")]
                     for case in ("ORIGINAL", "A", "C", "B1_OLD_KDM6")
                     for hour in range(12, 19) for layer in layer_names}
    if keys != required_keys:
        raise ValueError("context layer feature table does not cover the expected paired state grid")
    return rows, receipt


def layer_values_for_points(rows: list[dict], states, case: str, hour: int,
                            point_ids: set[int]) -> dict[int, dict[str, float]]:
    label = "[0,1000)m"
    by_id = {}
    for row in rows:
        if (row["case"] == case and int(row["hour_utc"]) == hour and row["layer_agl"] == label
                and int(row["flat_index_yx"]) in point_ids):
            point = int(row["flat_index_yx"])
            if point in by_id:
                raise ValueError("duplicate selected layer feature row")
            by_id[point] = row
    if set(by_id) != point_ids:
        raise ValueError(f"selected {case}/h{hour} state layer rows are incomplete")
    state = states[case, hour]
    state_ids = {int(point): index for index, point in enumerate(state["flat_index_yx"])}
    result = {}
    for point, row in by_id.items():
        index = state_ids.get(point)
        if index is None:
            raise ValueError("context point is absent from its state archive")
        height = state["corner_height_agl_m"][index]
        weights = state["corner_weights"][index]
        fields = {"QVAPOR_kgkg": "corner_QVAPOR", "RH_liquid": "corner_rh_liquid",
                  "QRAIN_kgkg": "corner_QRAIN"}
        values = {}
        for field, source in fields.items():
            corner = state[source][index].astype(np.float64)
            selected = np.isfinite(height) & np.isfinite(corner) & (height >= 0.0) & (height < 1000.0)
            count = selected.sum(axis=0)
            means = np.divide(np.where(selected, corner, 0.0).sum(axis=0, dtype=np.float64), count,
                              out=np.full(4, np.nan), where=count > 0)
            valid = np.all((count > 0) | (weights <= 0.0))
            if not valid:
                raise ValueError(f"no valid native levels for {field} at point {point}")
            weighted = float(np.sum(np.where(np.isfinite(means), means, 0.0) * weights))
            table_value = float(row[field])
            if not np.isclose(weighted, table_value, rtol=2e-13, atol=2e-13):
                raise ValueError(f"context {field} differs from direct corner recount at point {point}")
            values[field] = weighted
        result[point] = values
    return result


def draw_physical_context(layer_rows: list[dict], controls_rows: list[dict], membership_rows: list[dict],
                          states, output: Path) -> dict:
    membership = {int(row["flat_index_yx"]): set(row["cohort_labels"].split(";")) for row in membership_rows}
    control_groups: dict[str, set[int]] = {}
    for row in controls_rows:
        if row["valid_match"].lower() != "true":
            continue
        control_groups.setdefault(row["cohort_label"], set()).add(int(row["control_flat_index_yx"]))
    required = {"h02_original_A_weak_hit_loss", "h05_A_C_5mm_new_FA"}
    if not required.issubset(control_groups):
        raise ValueError("required matched-control cohorts are missing for the physical figure")
    specifications = [
        {"hour": 13, "baseline": "B1_OLD_KDM6", "candidate": "A", "multiplier": 1e3,
         "label": "ΔQVAPOR (g kg⁻¹)", "field": "QVAPOR_kgkg", "panel": 0},
        {"hour": 13, "baseline": "B1_OLD_KDM6", "candidate": "A", "multiplier": 100,
         "label": "ΔRH liquid (percentage points)", "field": "RH_liquid", "panel": 0},
        {"hour": 13, "baseline": "B1_OLD_KDM6", "candidate": "A", "multiplier": 1e6,
         "label": "ΔQRAIN (mg kg⁻¹)", "field": "QRAIN_kgkg", "panel": 0},
        {"hour": 16, "baseline": "A", "candidate": "C", "multiplier": 1e3,
         "label": "ΔQVAPOR (g kg⁻¹)", "field": "QVAPOR_kgkg", "panel": 1},
        {"hour": 16, "baseline": "A", "candidate": "C", "multiplier": 100,
         "label": "ΔRH liquid (percentage points)", "field": "RH_liquid", "panel": 1},
        {"hour": 16, "baseline": "A", "candidate": "C", "multiplier": 1e6,
         "label": "ΔQRAIN (mg kg⁻¹)", "field": "QRAIN_kgkg", "panel": 1},
    ]
    groups = [
        ("h02_loss_recovered_by_C", "Recovered (n=3)", "h02_original_A_weak_hit_loss"),
        ("h02_loss_unrecovered_by_C", "Unrecovered (n=7)", "h02_original_A_weak_hit_loss"),
        ("control_for:h02_original_A_weak_hit_loss", "Matched retained-hit controls (n=10)",
         "h02_original_A_weak_hit_loss"),
        ("h05_A_C_5mm_new_FA", "New 5 mm false alarms (n=12)", "h05_A_C_5mm_new_FA"),
        ("control_for:h05_A_C_5mm_new_FA", "Matched stable-below-threshold controls (n=12)",
         "h05_A_C_5mm_new_FA"),
    ]
    group_ids: dict[str, set[int]] = {}
    for role, label, control_cohort in groups:
        if role.startswith("control_for:"):
            ids = control_groups[control_cohort]
        else:
            ids = {point for point, labels in membership.items() if role in labels}
        expected_n = 10 if control_cohort == "h02_original_A_weak_hit_loss" and role.startswith("control_for:") else (
            12 if role.startswith("control_for:") else (3 if role == "h02_loss_recovered_by_C" else (
                7 if role == "h02_loss_unrecovered_by_C" else 12)))
        if len(ids) != expected_n:
            raise ValueError(f"physical figure group {label} has {len(ids)} points, expected {expected_n}")
        group_ids[label] = ids
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), constrained_layout=True)
    summary = {}
    for row_index in range(2):
        row_groups = groups[:3] if row_index == 0 else groups[3:]
        for column, spec in enumerate(item for item in specifications if item["panel"] == row_index):
            ax = axes[row_index, column]
            field = spec["field"]
            values_by_group = []
            for group_index, (role, label, _) in enumerate(row_groups):
                ids = group_ids[label]
                baseline = layer_values_for_points(layer_rows, states, spec["baseline"], spec["hour"], ids)
                candidate = layer_values_for_points(layer_rows, states, spec["candidate"], spec["hour"], ids)
                values = np.asarray([(candidate[p][field] - baseline[p][field]) * spec["multiplier"]
                                     for p in sorted(ids)], dtype=float)
                if not np.isfinite(values).all():
                    raise ValueError("physical figure contains nonfinite layer contrasts")
                values_by_group.append(values)
            box = ax.boxplot(values_by_group, positions=np.arange(1, len(values_by_group) + 1),
                             widths=.42, showfliers=False, patch_artist=True,
                             medianprops={"color": "#111111", "linewidth": 1.5},
                             whiskerprops={"color": "#555555"}, capprops={"color": "#555555"})
            palette = ("#009e73", "#d55e00", "#6c757d") if row_index == 0 else ("#d55e00", "#6c757d")
            for patch, color in zip(box["boxes"], palette):
                patch.set_facecolor(color)
                patch.set_alpha(.2)
                patch.set_edgecolor(color)
            for group_index, values in enumerate(values_by_group):
                x = group_index + 1
                point_ids = sorted(group_ids[row_groups[group_index][1]])
                jitter = np.asarray([(((point * 2654435761) % 1009) / 1008.0 - .5) * .14 for point in point_ids])
                color = palette[group_index]
                ax.scatter(x + jitter, values, s=29, color=color, edgecolor="white", linewidth=.45, zorder=3)
                summary[f"{row_index}_{column}_{row_groups[group_index][0]}"] = {
                    "n": int(values.size), "median": float(np.median(values)),
                    "q25": float(np.quantile(values, .25)), "q75": float(np.quantile(values, .75)),
                }
            ax.axhline(0, color="#333333", linewidth=.8, alpha=.7)
            ax.set_xticks(range(1, len(row_groups) + 1), [g[1] for g in row_groups], rotation=18, ha="right", fontsize=8)
            ax.set_title(spec["label"])
            ax.grid(axis="y", alpha=.2)
            if column == 0:
                ax.set_ylabel("A - X at +1 h (U13)" if row_index == 0 else "C - A at +4 h (U16)")
    fig.suptitle("0–1 km native model-level mean differences; points, median, and IQR\n"
                 "Eulerian history diagnostics; not mass-weighted or causal")
    fig.savefig(output, dpi=180, metadata={"Software": "plot_cp02_b1_failure_focus"})
    plt.close(fig)
    return summary


def write_gallery(folder: Path, names: list[str], metadata: dict) -> None:
    descriptions = {
        "csi_algebra_h5_5mm.png": "Exact +5 h, 5 mm CSI and transition-count algebra.",
        "h2_transition_maps.png": "+2 h weak-hit and false-alarm transition locations.",
        "h5_transition_maps.png": "+5 h 5 mm and weak-hit transition locations.",
        "selected_point_hourly_paths.png": "Selected paired-point one-hour precipitation paths from +1 through +6 h.",
        "conditional_layer_contrasts.png": "0–1 km native model-level moisture and rain mixing-ratio contrasts for frozen event groups and their matched controls.",
    }
    markdown = ["# CP02 failure-focus figures", "",
                "All maps and point paths are post hoc diagnostics for the 2026-08-16 12 UTC initialization. "
                "Rain amounts are one-hour increments, not cumulative lead totals. Transition labels are not model initialization rules.", ""]
    html_parts = ["<!doctype html><html lang='en'><meta charset='utf-8'><title>CP02 failure-focus figures</title>",
                  "<style>body{font:16px system-ui;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#222}img{max-width:100%;height:auto}figure{margin:2rem 0}figcaption{margin:.5rem 0}</style><body><h1>CP02 failure-focus figures</h1>",
                  "<p>Post hoc diagnostics for the 2026-08-16 12 UTC initialization. Rain amounts are one-hour increments, not cumulative lead totals. Transition labels are not initialization rules.</p>"]
    for name in names:
        caption = descriptions[name]
        markdown += [f"## {caption}", "", f"![{caption}]({name})", ""]
        html_parts.append(f"<figure><img src='{html.escape(name)}' alt='{html.escape(caption)}'><figcaption>{html.escape(caption)}</figcaption></figure>")
    html_parts.append("</body></html>")
    (folder / "gallery.md").write_text("\n".join(markdown), encoding="utf-8")
    (folder / "index.html").write_text("\n".join(html_parts) + "\n", encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def package_gallery(folder: Path, names: list[str]) -> dict:
    package_path = folder / "offline_gallery.zip"
    members = ["gallery.md", "index.html", "metadata.json", *names]
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in members:
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (folder / name).read_bytes())
    with zipfile.ZipFile(package_path) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(members):
            raise ValueError("offline gallery archive failed member/CRC validation")
        for name in members:
            if archive.read(name) != (folder / name).read_bytes():
                raise ValueError(f"offline gallery member differs: {name}")
    return {"path": package_path.name, "sha256": sha256(package_path),
            "size_bytes": package_path.stat().st_size, "members": members,
            "member_sha256": {name: sha256(folder / name) for name in members}}


def render(analysis: Path = ANALYSIS, output: Path = OUTPUT) -> dict:
    analysis, output = Path(analysis).resolve(), Path(output).resolve()
    if os.path.lexists(output):
        raise FileExistsError(f"output already exists: {output}")
    receipt, hourly, _, _ = grouped.verify_analysis(analysis)
    configure_font()
    counts = exact_counts(hourly)
    event_masks = focus_masks(hourly)
    target_receipt, cohort_masks, control_ids, csi_row = verify_targets(
        TARGETS, hourly, analysis, event_masks, counts)
    states, state_receipt = load_state_bundle(STATE, hourly, target_receipt)
    context_rows, context_receipt = load_context(CONTEXT, target_receipt, state_receipt)
    event_masks.update(cohort_masks)
    for name, points in control_ids.items():
        event_masks[name] = point_mask(hourly[13], points)
    coast_path = grouped.BOUNDARY_PATH
    if grouped.sha256(coast_path) != grouped.BOUNDARY_SHA256:
        raise ValueError("pinned Natural Earth coastline hash differs")
    coast = grouped.read_boundary(coast_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".cp02-b1-failure-focus-", dir=output.parent))
    try:
        draw_csi_algebra(counts, stage / "csi_algebra_h5_5mm.png")
        draw_weak_map(hourly, event_masks, coast, stage / "h2_transition_maps.png")
        draw_h5_map(hourly, event_masks, coast, stage / "h5_transition_maps.png")
        draw_point_paths(hourly, states, stage / "selected_point_hourly_paths.png")
        physical_summary = draw_physical_context(
            context_rows, read_csv(TARGETS / "matched_controls.csv"),
            read_csv(TARGETS / "focus_membership.csv"), states, stage / "conditional_layer_contrasts.png")
        names = ["csi_algebra_h5_5mm.png", "h2_transition_maps.png",
                 "h5_transition_maps.png", "selected_point_hourly_paths.png",
                 "conditional_layer_contrasts.png"]
        metadata = {
            "status": "PASS",
            "scope": "post hoc paired transition diagnostics; no causal or forecast-selection claim",
            "initial_time_utc": receipt["initial_time_utc"],
            "precipitation_window": receipt["precipitation_window"],
            "source_analysis": str(analysis.relative_to(ROOT)),
            "analysis_receipt_sha256": sha256(analysis / "receipt.json"),
            "target_bundle_receipt_sha256": sha256(TARGETS / "bundle_receipt.json"),
            "state_bundle_receipt_sha256": sha256(STATE / "receipt.json"),
            "context_bundle_receipt_sha256": sha256(CONTEXT / "bundle_receipt.json"),
            "context_layer_features_sha256": context_receipt["outputs"]["layer_features.csv"]["sha256"],
            "target_output_hashes": {name: record["sha256"] for name, record in sorted(target_receipt["outputs"].items())},
            "grouped_forecast_plan_sha256": grouped.PLAN_SHA256,
            "source_scorer": receipt["scorer"],
            "source_arrays": {name: {"sha256": record["sha256"], "size_bytes": record["size_bytes"]}
                              for name, record in sorted(receipt["outputs"].items())
                              if name.startswith("hour_") and name.endswith("_arrays.npz")},
            "renderer_sha256": sha256(Path(__file__)),
            "coastline": {"path": str(coast_path.relative_to(ROOT)), "sha256": sha256(coast_path),
                          "source_url": grouped.BOUNDARY_URL},
            "counts": counts,
            "matched_control_pairs": target_receipt["matched_control_pairs"],
            "unique_reused_control_ids": target_receipt["reused_control_ids_across_cohorts"],
            "state_surface_score_checks": state_receipt["surface_score_checks"],
            "conditional_layer_contrasts": physical_summary,
            "csi_algebra_row": csi_row,
            "outputs": {name: {"sha256": sha256(stage / name), "size_bytes": (stage / name).stat().st_size}
                        for name in names},
            "font": {"path": str(FONT), "sha256": FONT_SHA256, "bundled": False},
        }
        write_gallery(stage, names, metadata)
        (stage / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        package = package_gallery(stage, names)
        (stage / "package_receipt.json").write_text(
            json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if os.path.lexists(output):
            raise FileExistsError(f"output already exists: {output}")
        grouped.verify_analysis(analysis)
        stage.rename(output)
        return metadata
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=ANALYSIS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(render(args.analysis, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
