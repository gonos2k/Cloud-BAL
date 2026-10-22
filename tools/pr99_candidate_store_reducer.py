#!/usr/bin/env python3
"""Reduce captured public-Q stores and graupel sedimentation for the T1 account."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path

import netCDF4
import numpy as np

from native_kdm6_trace import read_dump
from pr95_call_budget import _read_map_geometry
from pr97_t1_rounding import read_columns
from pr98_budget import WATER, cutoff_columns, same_call_bottom
from pr98_budget_faces import compact_face_rows
from pr99_compact_stage_reducer import STAGES, reduce_compact


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def column_summary(values: np.ndarray, bounds: dict) -> dict:
    positive = np.unravel_index(int(np.argmax(values)), values.shape)
    negative = np.unravel_index(int(np.argmin(values)), values.shape)

    def point_detail(point: tuple[int, int]) -> dict:
        row, col = point
        return {"i": int(col + bounds["its"]), "j": int(row + bounds["jts"]),
                "kg": float(values[point])}

    return {
        "signed_kg": math.fsum(values.flat),
        "L1_column_kg": math.fsum(np.abs(values).flat),
        "max_abs_column_kg": float(np.max(np.abs(values))),
        "largest_positive": point_detail(positive),
        "most_negative": point_detail(negative),
    }


def reduce_public_store(path: Path, bounds: dict, area: np.ndarray) -> tuple[dict, np.ndarray, np.ndarray]:
    by_kind = {"PR87_CLOUD_PUBLIC_STORE": np.zeros(area.shape),
               "PR87_RAIN_PUBLIC_STORE": np.zeros(area.shape)}
    row_counts = np.zeros(area.shape, dtype=np.int64)
    counts = {name: 0 for name in by_kind}
    seen = set()
    with path.open(encoding="ascii") as stream:
        for line_number, line in enumerate(stream, 1):
            fields = line.split()
            if not fields:
                continue
            name = fields[0]
            if name not in by_kind:
                raise ValueError(f"unexpected public-store row {name!r}")
            if len(fields) != 16:
                raise ValueError(f"{path.name}:{line_number}: expected 16 tokens")
            timestep, j, i, k, adjustment = map(int, fields[1:6])
            values = np.asarray(fields[6:], dtype=np.float64)
            if values.shape != (10,) or not np.isfinite(values).all():
                raise ValueError(f"{path.name}:{line_number}: invalid numeric fields")
            if timestep != 1 or not (bounds["its"] <= i <= bounds["ite"] and
                                     bounds["jts"] <= j <= bounds["jte"] and
                                     bounds["kts"] <= k <= bounds["kte"]):
                raise ValueError(f"{path.name}:{line_number}: row outside T1 bounds")
            key = (name, i, j, k)
            if key in seen:
                raise ValueError(f"duplicate public-store row {key}")
            seen.add(key)
            q_input, n_input, n_roundtrip, q_public, n_public, density, dz, delta_q = values[:8]
            if density <= 0.0 or dz <= 0.0:
                raise ValueError(f"{path.name}:{line_number}: invalid source geometry")
            if (q_input < 0.0 or q_public < 0.0 or
                    q_input != float(np.float32(q_input)) or
                    q_public != float(np.float32(q_public))):
                raise ValueError(f"{path.name}:{line_number}: public Q endpoint is not nonnegative R32")
            expected_delta = q_public - q_input
            if (delta_q != expected_delta or
                    struct.pack(">d", delta_q) != struct.pack(">d", expected_delta)):
                raise ValueError(f"{path.name}:{line_number}: Q delta differs from emitted endpoints")
            if not (adjustment != 0 or n_public != n_roundtrip):
                raise ValueError(f"{path.name}:{line_number}: writer guard not satisfied")
            if adjustment == 0:
                # With no repair, Q remains the same R32 value passed to the R64 store.
                if q_public != q_input:
                    raise ValueError(f"{path.name}:{line_number}: adjustment-zero Q changed")
                if delta_q != 0.0:
                    raise ValueError(f"{path.name}:{line_number}: unlogged Q adjustment")
            row, col = j - bounds["jts"], i - bounds["its"]
            by_kind[name][row, col] += delta_q * density * dz * area[row, col]
            row_counts[row, col] += 1
            counts[name] += 1
    combined = by_kind["PR87_CLOUD_PUBLIC_STORE"] + by_kind["PR87_RAIN_PUBLIC_STORE"]
    report = {
        "source_formula": "(Q_public_R32 - Q_internal_R32) * emitted DEN * DELZ * same-call map area",
        "writer_coverage_proof": (
            "source calls the public store for every active rain/cloud level; it writes when "
            "adjustment!=0 or public N differs from ordinary N conversion. In the store routine, "
            "adjustment=0 keeps rounded input Q, so its Q delta is exactly zero. Thus every "
            "nonzero public Q delta is logged. Logged values are reduced as emitted."),
        "rows_by_kind": counts,
        "cloud": column_summary(by_kind["PR87_CLOUD_PUBLIC_STORE"], bounds),
        "rain": column_summary(by_kind["PR87_RAIN_PUBLIC_STORE"], bounds),
        "combined": column_summary(combined, bounds),
        "rows": len(seen),
    }
    return report, combined, row_counts


def reduce_graupel(path: Path, bounds: dict, area: np.ndarray) -> tuple[dict, np.ndarray, np.ndarray]:
    column_terms = np.zeros(area.shape)
    events = np.zeros(area.shape, dtype=np.int64)
    levels = bounds["kte"] - bounds["kts"] + 1
    by_column: dict[tuple[int, int], list[int]] = defaultdict(list)
    row_l1: list[float] = []
    row_max = 0.0
    seen = set()
    with path.open(encoding="ascii") as stream:
        header = False
        for line_number, line in enumerate(stream, 1):
            if line.startswith("# PR85_G_SED:"):
                header = True
                continue
            fields = line.split()
            if not fields or fields[0] != "PR85_G_SED":
                continue
            if len(fields) != 17:
                raise ValueError(f"{path.name}:{line_number}: expected 17 tokens")
            i, j, substep, nlevels = map(int, fields[1:5])
            values = np.asarray(fields[5:], dtype=np.float64)
            if values.shape != (12,) or not np.isfinite(values).all():
                raise ValueError(f"{path.name}:{line_number}: invalid numeric fields")
            if not (bounds["its"] <= i <= bounds["ite"] and
                    bounds["jts"] <= j <= bounds["jte"] and substep >= 1):
                raise ValueError(f"{path.name}:{line_number}: row outside call bounds")
            if nlevels != levels:
                raise ValueError(f"{path.name}:{line_number}: incomplete vertical column")
            key = (i, j, substep)
            if key in seen:
                raise ValueError(f"duplicate graupel row {key}")
            seen.add(key)
            row, col = j - bounds["jts"], i - bounds["its"]
            # Source field 10 (zero-based values[10]) is stored_delta_q + ground_approved_q.
            source_residual = float(values[10])
            expected = float(values[8] + values[6])
            if (source_residual != expected or
                    struct.pack(">d", source_residual) != struct.pack(">d", expected)):
                raise ValueError(f"{path.name}:{line_number}: source residual identity failed")
            event_kg = source_residual * area[row, col]
            column_terms[row, col] += event_kg
            events[row, col] += 1
            by_column[(i, j)].append(substep)
            row_l1.append(abs(event_kg))
            row_max = max(row_max, abs(event_kg))
    if not header:
        raise ValueError("graupel source header missing")
    expected_columns = area.size
    if len(by_column) != expected_columns:
        raise ValueError(f"graupel columns {len(by_column)} != {expected_columns}")
    if any(sorted(steps) != list(range(1, len(steps) + 1)) for steps in by_column.values()):
        raise ValueError("graupel substep coverage has a gap")
    report = {
        "source_formula": "(stored_delta_q + ground_approved_q) * same-call map area; source residual is kg m-2 and stored_delta_q uses actual DEN*DELZ over kts:kte",
        "ownership_proof": (
            "the source column operator freezes G packets, sweeps all kts:kte faces, updates only "
            "QG/BG for this species, sums stored QG delta with each level's actual DEN*DELZ, "
            "adds approved ground Q, writes residual_q=stored_delta_q+ground_approved_q, then "
            "commits qwork to QG. This G-only source term is separate from rain/ice face terms "
            "and the six compact process stages."),
        "rows": len(seen),
        "columns": len(by_column),
        "min_substeps_per_column": min(map(len, by_column.values())),
        "max_substeps_per_column": max(map(len, by_column.values())),
        "vertical_levels_per_row": levels,
        "event_L1_kg": math.fsum(row_l1),
        "max_abs_event_kg": row_max,
        "column_account": column_summary(column_terms, bounds),
        "event_rows_cover_all_active_columns_and_contiguous_substeps": True,
    }
    return report, column_terms, events


def baseline_arrays(run: Path, native: Path, face_path: Path, history: Path,
                    area: np.ndarray, bounds: dict, arm: str,
                    pre_sha256: str, post_sha256: str) -> np.ndarray:
    pre_path = native / "kdm6_first_call_pre.raw"
    post_path = native / "kdm6_first_call_post.raw"
    pre, post = read_dump(pre_path), read_dump(post_path)
    density = pre["fields"]["DEN"].astype(np.float64)
    thickness = pre["fields"]["DELZ"].astype(np.float64)
    water_delta = np.zeros_like(density * thickness * area[:, None, :])
    for field in WATER:
        water_delta += (post["fields"][field].astype(np.float64) -
                        pre["fields"][field].astype(np.float64)) * density * thickness * area[:, None, :]
    raw = np.sum(water_delta, axis=1, dtype=np.float64) + same_call_bottom(
        run / "pr67_kdm6_process.raw", pre, area)
    cutoff, _, _, _ = cutoff_columns(run / "pr85_kdm6_cutoff_budget.raw", bounds,
                                     density, thickness, area)
    _, liquid = read_columns(run / "pr97_liquid_columns.raw", bounds)
    rain, _, _ = compact_face_rows(run / "pr87_rain_sedimentation_budget.raw",
        run / "pr87_rain_sedimentation_budget.raw", "PR98_SED_FACE_SUM", 3, bounds, area)
    ice, _, _ = compact_face_rows(run / "pr85_ice_sedimentation_budget.raw",
        run / "pr85_ice_sedimentation_budget.raw", "PR98_SED_FACE_SUM", 1, bounds, area)
    baseline = raw - (liquid[:, :, 0] + liquid[:, :, 1]) * area - cutoff - rain - ice
    face = json.loads(face_path.read_text())
    if (face.get("arm") != arm or
            face.get("identity", {}).get("history_sha256") != sha256(history) or
            face.get("identity", {}).get("pre_sha256") != pre_sha256 or
            face.get("identity", {}).get("native_post_sha256") != post_sha256):
        raise ValueError("face report arm/history identity does not match this replay")
    receipt_baseline = face["compact_full_tile_face_capture"]["open_residual_after_independent_face_term"]
    for key, value in (("signed_kg", math.fsum(baseline.flat)),
                       ("L1_column_kg", math.fsum(np.abs(baseline).flat)),
                       ("max_abs_column_kg", float(np.max(np.abs(baseline))))):
        if abs(value - receipt_baseline[key]) > 1e-7 * max(1.0, abs(receipt_baseline[key])):
            raise ValueError(f"reconstructed baseline {key} differs from face receipt")
    return baseline


def analyze(arm: str, run: Path, native: Path, history: Path, manifest_path: Path,
            face_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get("arm") != arm or manifest.get("returncode") != 0 or
            manifest.get("completion_marker_observed") is not True or
            manifest.get("all_17_fields_and_XLAND_byte_equal") is not True):
        raise ValueError("replay receipt does not establish successful T1 identity")
    pre_path = native / "kdm6_first_call_pre.raw"
    post_path = native / "kdm6_first_call_post.raw"
    pre_dump, post_dump = read_dump(pre_path), read_dump(post_path)
    if (sha256(pre_path) != manifest.get("pre_sha256") or
            sha256(post_path) != manifest.get("native_post_sha256") or
            manifest.get("native_post_sha256") != manifest.get("replay_post_sha256")):
        raise ValueError("pre/post native state hashes differ from the replay receipt")
    replay_post = run / "replay_post.raw"
    executable = run / "replay.exe"
    if (sha256(replay_post) != manifest["replay_post_sha256"] or
            sha256(executable) != manifest["executable_sha256"]):
        raise ValueError("replay post-state or executable differs from the replay receipt")
    bounds = pre_dump["bounds"]
    inputs = ("pr67_kdm6_process.raw", "pr85_kdm6_cutoff_budget.raw",
              "pr87_rain_sedimentation_budget.raw", "pr85_ice_sedimentation_budget.raw",
              "pr87_qn_public_store.raw", "pr85_graupel_sedimentation_budget.raw",
              "pr99_process_stage_compact.raw")
    recorded_inputs = manifest.get("stage_file_sha256", {})
    for name in inputs:
        path = run / name
        if name not in recorded_inputs or sha256(path) != recorded_inputs[name]:
            raise ValueError(f"{name} differs from or is absent in the replay inventory")
    face_receipt = json.loads(face_path.read_text())
    liquid_path = run / "pr97_liquid_columns.raw"
    liquid_sha = face_receipt.get("identity", {}).get("liquid_columns_sha256")
    if not liquid_sha or sha256(liquid_path) != liquid_sha:
        raise ValueError("liquid-column ledger differs from the face replay identity")
    with netCDF4.Dataset(history) as dataset:
        dataset.set_auto_mask(False)
        area, _, _ = _read_map_geometry(dataset, slice(bounds["jts"]-1, bounds["jte"]),
                                        slice(bounds["its"]-1, bounds["ite"]))
    baseline = baseline_arrays(run, native, face_path, history, area, bounds, arm,
                               manifest["pre_sha256"], manifest["native_post_sha256"])
    stages = reduce_compact(run / "pr99_process_stage_compact.raw", bounds, area)
    process = sum(stages["stage_column_arrays"].values(), np.zeros_like(baseline))
    packet = sum(stages["packet_column_arrays"].values(), np.zeros_like(baseline))
    open_v4 = baseline - process - packet
    public, public_columns, public_counts = reduce_public_store(
        run / "pr87_qn_public_store.raw", bounds, area)
    graupel, graupel_columns, graupel_counts = reduce_graupel(
        run / "pr85_graupel_sedimentation_budget.raw", bounds, area)
    final = open_v4 - public_columns - graupel_columns
    final_extrema = column_summary(final, bounds)
    selected = {}
    check_points = [(169, 227), (32, 116),
                 (final_extrema["largest_positive"]["i"], final_extrema["largest_positive"]["j"]),
                 (final_extrema["most_negative"]["i"], final_extrema["most_negative"]["j"]),
                 (public["combined"]["largest_positive"]["i"], public["combined"]["largest_positive"]["j"]),
                 (public["combined"]["most_negative"]["i"], public["combined"]["most_negative"]["j"]),
                 (graupel["column_account"]["largest_positive"]["i"],
                  graupel["column_account"]["largest_positive"]["j"]),
                 (graupel["column_account"]["most_negative"]["i"],
                  graupel["column_account"]["most_negative"]["j"])]
    for i, j in dict.fromkeys(check_points):
        row, col = j - bounds["jts"], i - bounds["its"]
        key = f"{i},{j}"
        selected[key] = {
            "v4_open_kg": float(open_v4[row, col]),
            "public_store_Q_change_kg": float(public_columns[row, col]),
            "graupel_sedimentation_Q_change_kg": float(graupel_columns[row, col]),
            "open_after_two_additional_terms_kg": float(final[row, col]),
            "public_store_rows": int(public_counts[row, col]),
            "graupel_substeps": int(graupel_counts[row, col]),
        }
    return {
        "schema": "pr99_t1_candidate_store_supplement_v5",
        "arm": arm,
        "source_sha256": manifest["prepared_source_sha256"],
        "executable_sha256": manifest["executable_sha256"],
        "manifest_sha256": sha256(manifest_path),
        "replay_post_sha256": sha256(run / "replay_post.raw"),
        "replay_executable_sha256": sha256(run / "replay.exe"),
        "input_inventory_sha256": {name: recorded_inputs[name] for name in inputs},
        "liquid_columns_sha256": liquid_sha,
        "baseline_face_report_sha256": sha256(face_path),
        "history_sha256": sha256(history),
        "public_store_sha256": sha256(run / "pr87_qn_public_store.raw"),
        "graupel_ledger_sha256": sha256(run / "pr85_graupel_sedimentation_budget.raw"),
        "all_17_fields_and_XLAND_byte_equal": True,
        "fixed_active_tile_columns": int(area.size),
        "v4_open_after_six_stages_and_separate_approved_packet": column_summary(open_v4, bounds),
        "public_store_Q_change": public,
        "graupel_sedimentation_Q_change": graupel,
        "open_after_two_additional_source_terms": final_extrema,
        "selected_column_checks": selected,
        "balance_convention": "R_final = R_v4 - public_Q_store_change - graupel_source_residual; positive C is positive Q storage change",
        "limits": [
            "Supplemental terms use existing successful C1 first-call T1 replay artifacts; no forecast was run.",
            "Only the full active-tile measure is reported; no exact 613-cell vertical mask is reconstructed here.",
            "The resulting remainder is still open and is not attributed to rounding or a physical loss.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("OFF", "HYDRO", "COUPLED"), required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--face-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.arm, args.run, args.native, args.history, args.manifest, args.face_report)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(args.arm, json.dumps({"public": result["public_store_Q_change"]["combined"]["signed_kg"],
                                "graupel": result["graupel_sedimentation_Q_change"]["column_account"]["signed_kg"],
                                "open": result["open_after_two_additional_source_terms"]["signed_kg"]},
                               sort_keys=True))


if __name__ == "__main__":
    main()
