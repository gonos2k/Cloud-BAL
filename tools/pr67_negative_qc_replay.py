#!/usr/bin/env python3
"""Replay the PR67 QC RK observer against PR65 transition masks and KDM state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import stat
from collections import Counter
from pathlib import Path

import numpy as np

from native_kdm6_trace import read_dump
from pr63_transition_replay import read_masks


KDM_WINDOW = {"i": (2, 233), "j": (2, 281), "k": (1, 39)}
PRE_COLUMNS = (
    "qc_before", "base_q", "advect_tend", "msfty", "scaled_advect",
    "physical_tend", "total_tend", "dt", "c1", "c2", "mu_old",
    "mu_new", "mu_base", "old_mass", "new_mass", "predicted_q",
)
RUN3_CORE_INDICES = (0, 1, 2, 3, 4, 5, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20)
RUN3_CHANNELS = ("pbl", "cu", "shcu", "nc_cu", "nc_shcu")
RK_STAGES = ("PRE_RK", "RK_STAGE_END", "RK_STAGE_END", "RK_STAGE_END")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_receipt_file(root: Path, record: dict) -> Path:
    relative = Path(record["path"])
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name in (".", ".."):
        raise ValueError(f"receipt output escapes run root: {record['path']}")
    path = root / relative
    metadata = path.lstat()
    if (stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or
            metadata.st_nlink != 1 or metadata.st_dev != record["device"] or
            metadata.st_ino != record["inode"] or metadata.st_nlink != record["nlink"]):
        raise ValueError(f"output is not a regular single-link receipt file: {path}")
    if sha256(path) != record["sha256"]:
        raise ValueError(f"output hash differs from run receipt: {path}")
    return path


def in_kdm_window(coord: tuple[int, int, int]) -> bool:
    return all(KDM_WINDOW[axis][0] <= value <= KDM_WINDOW[axis][1]
               for axis, value in zip(("i", "j", "k"), coord, strict=True))


def read_observer(path: Path) -> tuple[dict, dict, dict]:
    before: dict[tuple[int, tuple[int, int, int]], np.ndarray] = {}
    after: dict[str, dict[tuple[int, tuple[int, int, int]], np.float32]] = {
        stage: {} for stage in ("AFTER_UPDATE", "AFTER_DIABATIC", "AFTER_FLOW_BDY")
    }
    counters: Counter[str] = Counter()
    with path.open(encoding="ascii") as stream:
        for number, line in enumerate(stream, 1):
            fields = line.split()
            if not fields:
                continue
            if fields[0] == "QC_PRE":
                if len(fields) not in (21, 26):
                    raise ValueError(f"malformed QC_PRE at line {number}")
                rk, i, j, k = map(int, fields[1:5])
                raw_values = np.asarray([float(value) for value in fields[5:]], dtype=np.float32)
                if len(fields) == 26:
                    for name, index in zip(RUN3_CHANNELS, range(6, 11), strict=True):
                        value = raw_values[index]
                        if not np.isfinite(value) or abs(float(value)) >= 1.0e30:
                            counters[f"ignored_run3_channel_invalid_{name}"] += 1
                    values = raw_values[list(RUN3_CORE_INDICES)]
                    counters["run3_channel_schema_rows"] += 1
                else:
                    values = raw_values
                    counters["run2_core_schema_rows"] += 1
                if values.size != len(PRE_COLUMNS):
                    raise ValueError(f"unexpected QC_PRE width at line {number}")
                if not np.isfinite(values).all():
                    raise ValueError(f"nonfinite active QC update term at line {number}")
                if rk not in (1, 2, 3) or not in_kdm_window((i, j, k)) and min(i, j, k) < 1:
                    raise ValueError(f"invalid QC_PRE coordinate or RK step at line {number}")
                if values[7] <= 0 or values[13] <= 0 or values[14] <= 0:
                    raise ValueError(f"nonpositive dt or mass at line {number}")
                key = (rk, (i, j, k))
                if key in before:
                    raise ValueError(f"duplicate QC_PRE event at line {number}")
                before[key] = values
                counters["qc_pre_total"] += 1
                counters[f"qc_pre_rk{rk}_total"] += 1
                if in_kdm_window((i, j, k)):
                    counters[f"qc_pre_rk{rk}_kdm_window"] += 1
            elif fields[0] == "QC_POST":
                if len(fields) != 7:
                    raise ValueError(f"malformed QC_POST at line {number}")
                stage = fields[1]
                if stage not in after:
                    raise ValueError(f"unexpected QC_POST stage at line {number}: {stage}")
                rk, i, j, k = map(int, fields[2:6])
                q = np.float32(float(fields[6]))
                key = (rk, (i, j, k))
                if rk not in (1, 2, 3) or not np.isfinite(q) or q >= 0:
                    raise ValueError(f"invalid negative QC_POST event at line {number}")
                if key in after[stage]:
                    raise ValueError(f"duplicate negative QC_POST at line {number}")
                after[stage][key] = q
                counters[f"{stage.lower()}_total"] += 1
                counters[f"{stage.lower()}_rk{rk}_total"] += 1
                if in_kdm_window((i, j, k)):
                    counters[f"{stage.lower()}_kdm_window"] += 1
                    counters[f"{stage.lower()}_rk{rk}_kdm_window"] += 1
            else:
                raise ValueError(f"unknown QC observer record at line {number}")
    return before, after, dict(counters)


def mask_negative_sets(path: Path) -> tuple[list[set[tuple[int, int, int]]],
                                            list[set[tuple[int, int, int]]]]:
    result = []
    kdm_result = []
    for record in read_masks(path):
        bounds, mask = record["bounds"], record["mask"]
        coords = set()
        coords = set()
        kdm_coords = set()
        for j, k, i in np.argwhere((mask & 2) != 0):
            coord = (int(i + bounds["its"]), int(j + bounds["jts"]),
                     int(k + bounds["kts"]))
            coords.add(coord)
            if in_kdm_window(coord):
                kdm_coords.add(coord)
        result.append(coords)
        kdm_result.append(kdm_coords)
    if len(result) < 4:
        raise ValueError("transition masks omit a completed RK state")
    return result, kdm_result


def first_appearance_sets(mask_sets: list[set[tuple[int, int, int]]],
                          final_coords: set[tuple[int, int, int]]) -> list[set[tuple[int, int, int]]]:
    seen = set(mask_sets[0])
    groups = []
    for current in mask_sets[1:4]:
        appearing = (current & final_coords) - seen
        groups.append(appearing)
        seen |= current
    if seen & final_coords != final_coords:
        raise ValueError("KDM-entry negative QC cells are absent from all RK masks")
    return groups


def float32_update(values: np.ndarray, omit: str = "") -> np.float32:
    v = dict(zip(PRE_COLUMNS, values, strict=True))
    adv = np.float32(0.0) if omit == "advection" else v["scaled_advect"]
    phys = np.float32(0.0) if omit == "physical" else v["physical_tend"]
    total = np.float32(adv + phys)
    numerator = np.float32(np.float32(v["old_mass"] * v["base_q"]) +
                            np.float32(v["dt"] * total))
    return np.float32(numerator / v["new_mass"])


def summarize(observer: Path, baseline: Path, expected_executable: Path | None = None,
              observer_source: Path | None = None,
              expected_input_count: int = 101) -> dict:
    receipt = json.loads((observer / "run-isolation.json").read_text())
    if (receipt.get("returncode") != 0 or receipt.get("input_integrity") != "PASS" or
            receipt.get("output_isolation") != "PASS" or receipt.get("changed_inputs") or
            receipt.get("input_read_issues") or receipt.get("output_issues")):
        raise ValueError("guarded observer run or its isolation checks did not pass")
    inputs = receipt.get("inputs", [])
    if len(inputs) != expected_input_count or any(item.get("sha256_before") != item.get("sha256_after")
                                  for item in inputs):
        raise ValueError("declared run inputs are incomplete or changed")
    executable_inputs = [item for item in inputs
                         if Path(item["path"]).absolute() == (observer / "wrf.exe").absolute()]
    if len(executable_inputs) != 1:
        raise ValueError("run executable is not uniquely bound as a declared input")
    executable_input = executable_inputs[0]
    output_records = {row["path"]: row for row in receipt["outputs"]}
    for name in ("pr67_qc_rk.raw", "pr63_transition_masks.bin",
                 "kdm6_first_call_pre.raw", "kdm6_first_call_post.raw"):
        if name not in output_records:
            raise ValueError(f"observer output hash does not match run receipt: {name}")
        verify_receipt_file(observer, output_records[name])
    executable_path = observer / "wrf.exe"
    executable_stat = executable_path.lstat()
    if (stat.S_ISLNK(executable_stat.st_mode) or not stat.S_ISREG(executable_stat.st_mode) or
            executable_stat.st_nlink != 1):
        raise ValueError("run executable is not a regular single-link file")
    executable_hash = sha256(executable_path)
    if executable_hash != executable_input["sha256_before"] or executable_hash != executable_input["sha256_after"]:
        raise ValueError("run executable hash differs from its unchanged receipt input row")
    expected_executable_hash = None
    if expected_executable is not None:
        expected_stat = expected_executable.lstat()
        if stat.S_ISLNK(expected_stat.st_mode) or not stat.S_ISREG(expected_stat.st_mode):
            raise ValueError("expected executable is not a regular file")
        expected_executable_hash = sha256(expected_executable)
        if executable_hash != expected_executable_hash:
            raise ValueError("run executable differs from linked observer executable")
    for name in ("wrfout_d01_2026-08-16_12:00:00", "namelist.output",
                 "pr63_transition_stages.raw"):
        if name not in output_records:
            raise ValueError(f"guarded run receipt omits matched baseline output: {name}")
        verify_receipt_file(observer, output_records[name])
    for name in ("pr63_transition_masks.bin", "kdm6_first_call_pre.raw",
                 "kdm6_first_call_post.raw", "pr63_transition_stages.raw",
                 "wrfout_d01_2026-08-16_12:00:00", "namelist.output"):
        if sha256(observer / name) != sha256(baseline / name):
            raise ValueError(f"observer state differs from pinned PR65 baseline: {name}")

    masks_full, masks_kdm = mask_negative_sets(baseline / "pr63_transition_masks.bin")
    if masks_full[0] or masks_kdm[0]:
        raise ValueError("pre-RK completed state already contains negative QC")
    kdm_pre = read_dump(baseline / "kdm6_first_call_pre.raw")
    q = kdm_pre["fields"]["QC"]
    b = kdm_pre["bounds"]
    if {axis: (b[f"{axis}ts"], b[f"{axis}te"]) for axis in ("i", "j", "k")} != KDM_WINDOW:
        raise ValueError("KDM trace bounds differ from the pinned active crop")
    final_coords = {
        (int(i + b["its"]), int(j + b["jts"]), int(k + b["kts"]))
        for j, k, i in np.argwhere(q < 0)
    }
    if final_coords != masks_kdm[3]:
        raise ValueError("KDM-entry negative QC set differs from completed RK3 KDM mask")
    groups = first_appearance_sets(masks_kdm, final_coords)
    before, after, counts = read_observer(observer / "pr67_qc_rk.raw")

    replay_rows = {rk: [] for rk in (1, 2, 3)}
    exact_equation = 0
    exact_after_update = 0
    exact_scaled_advection = 0
    exact_total_tendency = 0
    exact_old_mass = 0
    exact_new_mass = 0
    for rk, coords in enumerate(groups, 1):
        for coord in coords:
            key = (rk, coord)
            if key not in before:
                raise ValueError(f"first-negative RK event lacks predictor terms: {key}")
            values = before[key]
            predicted = float32_update(values)
            v = dict(zip(PRE_COLUMNS, values, strict=True))
            f32 = np.float32
            expected_scaled = f32(f32(v["advect_tend"]) * f32(v["msfty"]))
            expected_total = f32(expected_scaled + f32(v["physical_tend"]))
            expected_old_mass = f32(f32(v["c1"]) * f32(f32(v["mu_old"]) + f32(v["mu_base"])) + f32(v["c2"]))
            expected_new_mass = f32(f32(v["c1"]) * f32(f32(v["mu_new"]) + f32(v["mu_base"])) + f32(v["c2"]))
            if (expected_scaled != v["scaled_advect"] or expected_total != v["total_tend"] or
                    expected_old_mass != v["old_mass"] or expected_new_mass != v["new_mass"] or
                    predicted != v["predicted_q"] or v["qc_before"] < 0 or predicted >= 0):
                raise ValueError(f"float32 update does not reproduce captured negative: {key}")
            exact_scaled_advection += 1
            exact_total_tendency += 1
            exact_old_mass += 1
            exact_new_mass += 1
            exact_equation += 1
            output = after["AFTER_UPDATE"].get(key)
            if output is None or output != predicted:
                raise ValueError(f"after-update QC differs from reconstructed value: {key}")
            exact_after_update += 1
            replay_rows[rk].append(values)

    stage_sets = {}
    for stage in ("AFTER_UPDATE", "AFTER_DIABATIC", "AFTER_FLOW_BDY"):
        stage_sets[stage] = {
            rk: {coord for (event_rk, coord), value in after[stage].items()
                 if event_rk == rk}
            for rk in (1, 2, 3)
        }
    state_counts = [len(mask_set) for mask_set in masks_kdm[:4]]
    for rk, mask_index in zip((1, 2, 3), (1, 2, 3), strict=True):
        for stage in ("AFTER_UPDATE", "AFTER_DIABATIC"):
            observed_kdm = {coord for coord in stage_sets[stage][rk] if in_kdm_window(coord)}
            if observed_kdm != masks_kdm[mask_index]:
                raise ValueError(f"negative QC set at {stage}/RK{rk} differs from transition mask")
        if stage_sets["AFTER_FLOW_BDY"][rk] != masks_full[mask_index]:
            raise ValueError(f"negative QC set at AFTER_FLOW_BDY/RK{rk} differs from transition mask")
        flow_additions = stage_sets["AFTER_FLOW_BDY"][rk] - stage_sets["AFTER_UPDATE"][rk]
        if any(in_kdm_window(coord) for coord in flow_additions):
            raise ValueError(f"flow boundary adds negative QC inside KDM window at RK{rk}")

    attribution = {}
    for rk, rows in replay_rows.items():
        if not rows:
            raise ValueError(f"no first-negative rows for RK{rk}")
        arr = np.stack(rows)
        attribution[f"rk{rk}"] = {
            "first_negative_cells": len(rows),
            "advect_tendency_sign": dict(Counter(
                "negative" if x < 0 else "positive" if x > 0 else "zero" for x in arr[:, 2])),
            "scaled_advect_sign": dict(Counter(
                "negative" if x < 0 else "positive" if x > 0 else "zero" for x in arr[:, 4])),
            "physical_tendency_sign": dict(Counter(
                "negative" if x < 0 else "positive" if x > 0 else "zero" for x in arr[:, 5])),
            "base_q_sign": dict(Counter(
                "negative" if x < 0 else "positive" if x > 0 else "zero" for x in arr[:, 1])),
            "negative_if_advection_omitted": int(sum(float32_update(row, "advection") < 0 for row in rows)),
            "negative_if_physical_term_omitted": int(sum(float32_update(row, "physical") < 0 for row in rows)),
            "minimum_old_mass": float(np.min(arr[:, 13])),
            "minimum_new_mass": float(np.min(arr[:, 14])),
            "minimum_dt": float(np.min(arr[:, 7])),
            "maximum_dt": float(np.max(arr[:, 7])),
        }

    if len(final_coords) != 23494 or exact_equation != len(final_coords):
        raise ValueError("unexpected KDM-entry or equation-replay count")
    return {
        "schema": "pr67_negative_qc_replay_v1",
        "provenance": {
            "observer_dir": str(observer),
            "baseline_dir": str(baseline),
            "observer_run_receipt_sha256": sha256(observer / "run-isolation.json"),
            "observer_raw_sha256": sha256(observer / "pr67_qc_rk.raw"),
            "replay_tool_sha256": sha256(Path(__file__)),
            "observer_source_path": str(observer_source) if observer_source else None,
            "observer_source_sha256": sha256(observer_source) if observer_source else None,
            "run_executable_sha256": executable_hash,
            "run_executable_receipt_input_sha256": executable_input["sha256_before"],
            "declared_unchanged_input_count": len(inputs),
            "expected_executable_sha256": expected_executable_hash,
            "transition_masks_sha256": sha256(baseline / "pr63_transition_masks.bin"),
            "kdm_pre_sha256": sha256(baseline / "kdm6_first_call_pre.raw"),
            "kdm_post_sha256": sha256(baseline / "kdm6_first_call_post.raw"),
            "baseline_hashes_match_observer": True,
        },
        "negative_qc": {
            "kdm_entry_cells": len(final_coords),
            "first_negative_after_rk1": len(groups[0]),
            "first_negative_after_rk2": len(groups[1]),
            "first_negative_after_rk3": len(groups[2]),
            "negative_cells_at_completed_rk1_kdm_window": state_counts[1],
            "negative_cells_at_completed_rk2_kdm_window": state_counts[2],
            "negative_cells_at_completed_rk3_kdm_window": state_counts[3],
            "negative_cells_at_completed_rk1_full_transition_mask": len(masks_full[1]),
            "negative_cells_at_completed_rk2_full_transition_mask": len(masks_full[2]),
            "negative_cells_at_completed_rk3_full_transition_mask": len(masks_full[3]),
            "transition_mask_negatives_outside_kdm_window": {
                "rk1": len(masks_full[1]) - len(masks_kdm[1]),
                "rk2": len(masks_full[2]) - len(masks_kdm[2]),
                "rk3": len(masks_full[3]) - len(masks_kdm[3]),
            },
            "negative_cell_sets_match_transition_masks_at_each_captured_boundary": True,
            "flow_boundary_added_negatives_outside_kdm_window": {
                f"rk{rk}": len({coord for coord in stage_sets["AFTER_FLOW_BDY"][rk] - stage_sets["AFTER_UPDATE"][rk]
                                if not in_kdm_window(coord)})
                for rk in (1, 2, 3)
            },
            "all_first_negative_cells_reconstructed_by_binary32_update": exact_equation,
            "all_reconstructed_values_match_native_after_update": exact_after_update,
            "all_scaled_advection_terms_reconstructed": exact_scaled_advection,
            "all_combined_tendencies_reconstructed": exact_total_tendency,
            "all_old_mass_denominators_reconstructed": exact_old_mass,
            "all_new_mass_denominators_reconstructed": exact_new_mass,
        },
        "first_negative_cell_term_evidence": attribution,
        "observer_record_counts": counts,
        "interpretation_limits": [
            "The no-advection and no-physical counts are binary32 component-omission screens; they are not independent causal interventions or a conserved-flux replay.",
            "The source observer records the native advection tendency and mass factor, not face-by-face advection fluxes.",
            "The physical tendency also includes RK1 horizontal diffusion when enabled; it cannot be identified with PBL mixing alone.",
            "The PBL channel columns in the run3 record are ignored because SHCU/NC-SHCU values were invalid and process-channel closure failed; only the aggregate physical tendency passed to the update is replayed.",
            "The replay identifies the first completed negative-QC boundary and verifies the local update equation. It does not establish which physical process should be changed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observer", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("--expected-executable", type=Path)
    parser.add_argument("--observer-source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = summarize(args.observer, args.baseline, args.expected_executable,
                       args.observer_source)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
