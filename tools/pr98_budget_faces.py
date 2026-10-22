#!/usr/bin/env python3
"""Reduce selected accepted sediment-face/store observations and cross-check ledgers."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import netCDF4
import numpy as np

from native_kdm6_trace import read_dump
from pr95_call_budget import HISTORY, _read_map_geometry
from pr97_t1_rounding import read_columns
from pr98_budget import WATER, cutoff_columns, same_call_bottom, sha256, stats

MODE_NAMES = {1: "ice", 2: "graupel", 3: "rain"}


def stage_rows(path: Path, prefix: str) -> dict[tuple[int, int, int], tuple[int, float, float, float]]:
    records = {}
    with path.open(encoding="ascii") as source:
        for line in source:
            fields = line.split()
            if not fields or fields[0] != prefix:
                continue
            if len(fields) != 17:
                raise ValueError(f"invalid {prefix} row width")
            i, j, substep, nlevels = map(int, fields[1:5])
            values = np.asarray(fields[5:], dtype=np.float64)
            if not np.isfinite(values).all() or nlevels < 1:
                raise ValueError(f"invalid {prefix} stage operands")
            key = (i, j, substep)
            if key in records:
                raise ValueError(f"duplicate {prefix} substep")
            records[key] = (nlevels, float(values[10]), float(values[8]), float(values[6]))
    return records


def face_rows(path: Path, bounds: dict, density: np.ndarray, thickness: np.ndarray,
              area: np.ndarray, rain_path: Path, ice_path: Path) -> dict:
    expected = {
        ("rain", 3): stage_rows(rain_path, "PR87_RAIN_SED"),
        ("ice", 1): stage_rows(ice_path, "PR85_ICE_SED"),
    }
    grouped: dict[tuple[int, int, int, int], list[tuple]] = defaultdict(list)
    seen = set()
    packet_counts = {mode: {"captured_accepted_face_records": 0,
                            "nonzero_approved_packets": 0,
                            "positive_approved_packets": 0,
                            "negative_approved_packets": 0,
                            "zero_approved_packets": 0}
                     for mode in MODE_NAMES}
    with path.open(encoding="ascii") as source:
        for line in source:
            fields = line.split()
            if not fields or fields[0] != "PR98_SED_FACE":
                continue
            if len(fields) != 18:
                raise ValueError("invalid PR98 face event width")
            i, j, substep, mode, donor, receiver, has_receiver = map(int, fields[1:8])
            values = np.asarray(fields[8:], dtype=np.float64)
            if not np.isfinite(values).all():
                raise ValueError("nonfinite PR98 face operand")
            if (mode not in MODE_NAMES or has_receiver not in (0, 1) or
                    not (bounds["its"] <= i <= bounds["ite"] and bounds["jts"] <= j <= bounds["jte"]) or
                    not (bounds["kts"] <= donor <= bounds["kte"]) or substep < 1):
                raise ValueError("PR98 face event outside call bounds")
            if has_receiver and not (bounds["kts"] <= receiver <= bounds["kte"]):
                raise ValueError("PR98 receiver outside call bounds")
            if not has_receiver and receiver != 0:
                raise ValueError("ground face must have receiver index zero")
            key = (i, j, substep, mode, donor)
            if key in seen:
                raise ValueError("duplicate PR98 face event")
            seen.add(key)
            theta, proposed_q, donor_before, donor_after, donor_rho, donor_dz, \
                recv_before, recv_after, recv_rho, recv_dz = map(float, values)
            if theta < 0.0 or theta > 1.0 or proposed_q < 0.0 or min(donor_rho, donor_dz) <= 0:
                raise ValueError("invalid accepted packet or donor carrier")
            if has_receiver and min(recv_rho, recv_dz) <= 0:
                raise ValueError("invalid receiver carrier")
            row, col = j - bounds["jts"], i - bounds["its"]
            if not np.isclose(donor_rho, density[row, donor - bounds["kts"], col], rtol=0, atol=0) or \
                    not np.isclose(donor_dz, thickness[row, donor - bounds["kts"], col], rtol=0, atol=0):
                raise ValueError("face donor carrier differs from same-call geometry")
            if has_receiver and (
                    recv_rho != density[row, receiver - bounds["kts"], col] or
                    recv_dz != thickness[row, receiver - bounds["kts"], col]):
                raise ValueError("face receiver carrier differs from same-call geometry")
            packet = theta * proposed_q
            counts = packet_counts[mode]
            counts["captured_accepted_face_records"] += 1
            counts["nonzero_approved_packets"] += int(packet != 0.0)
            counts["positive_approved_packets"] += int(packet > 0.0)
            counts["negative_approved_packets"] += int(packet < 0.0)
            counts["zero_approved_packets"] += int(packet == 0.0)
            donor_error = ((donor_after - donor_before) * donor_rho * donor_dz + packet) * area[row, col]
            receiver_error = (((recv_after - recv_before) * recv_rho * recv_dz - packet) * area[row, col]
                              if has_receiver else 0.0)
            grouped[(i, j, substep, mode)].append((donor, packet * area[row, col], donor_error, receiver_error))

    by_cell_mode: dict[tuple[int, int, int], list[float]] = defaultdict(list)
    cell_donor: dict[tuple[int, int, int], list[float]] = defaultdict(list)
    cell_receiver: dict[tuple[int, int, int], list[float]] = defaultdict(list)
    cell_packet: dict[tuple[int, int, int], list[float]] = defaultdict(list)
    cell_count: dict[tuple[int, int, int], int] = defaultdict(int)
    checked = 0
    for (i, j, substep, mode), rows in grouped.items():
        name = MODE_NAMES[mode]
        if (name, mode) not in expected:
            continue
        key = (i, j, substep)
        source = expected[(name, mode)].get(key)
        if source is None:
            raise ValueError("face event has no matching sediment stage row")
        nlevels, stage_residual, _, _ = source
        donors = [row[0] for row in rows]
        if len(rows) != nlevels or len(set(donors)) != nlevels:
            raise ValueError("face events are incomplete for a captured source substep")
        if set(donors) != set(range(bounds["kts"], bounds["kte"] + 1)):
            raise ValueError("face donor levels do not cover the captured column")
        direct = math.fsum(row[2] + row[3] for row in rows)
        stage_kg = stage_residual * area[j - bounds["jts"], i - bounds["its"]]
        absolute_scale = math.fsum(abs(row[2]) + abs(row[3]) for row in rows)
        tolerance = max(1e-9, 128 * np.finfo(np.float64).eps * max(absolute_scale, abs(stage_kg), 1.0))
        if abs(direct - stage_kg) > tolerance:
            raise ValueError(f"face/source stage closure mismatch at {(i, j, substep, name)}")
        cell_key = (i, j, mode)
        by_cell_mode[cell_key].extend(row[2] + row[3] for row in rows)
        cell_donor[cell_key].extend(row[2] for row in rows)
        cell_receiver[cell_key].extend(row[3] for row in rows)
        cell_packet[cell_key].extend(row[1] for row in rows)
        cell_count[cell_key] += len(rows)
        checked += 1
    if checked == 0:
        raise ValueError("no face events matched rain/ice source stage rows")

    result = {}
    for (i, j, mode), terms in sorted(by_cell_mode.items()):
        result.setdefault(f"{i},{j}", {})[MODE_NAMES[mode]] = {
            "accepted_face_records": cell_count[(i, j, mode)],
            "approved_packet_kg": math.fsum(cell_packet[(i, j, mode)]),
            "donor_store_packet_discrepancy_kg": math.fsum(cell_donor[(i, j, mode)]),
            "receiver_store_packet_discrepancy_kg": math.fsum(cell_receiver[(i, j, mode)]),
            "net_source_face_discrepancy_kg": math.fsum(terms),
            "source_stage_rows_independently_match": True,
        }
    return {"accepted_face_capture_counts_by_mode":
                {MODE_NAMES[mode]: counts for mode, counts in packet_counts.items()},
            "matched_substeps": checked, "selected_columns": result}


def compact_face_rows(path: Path, source_path: Path, prefix: str, mode: int,
                      bounds: dict, area: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Read per-column source-face sums and require one-to-one source-ledger agreement."""
    source_prefix = "PR87_RAIN_SED" if mode == 3 else "PR85_ICE_SED"
    source = stage_rows(source_path, source_prefix)
    records = {}
    shape = area.shape
    terms = np.zeros(shape, dtype=np.float64)
    compensation = np.zeros(shape, dtype=np.float64)
    column_events = np.zeros(shape, dtype=np.int64)
    face_event_l1_terms: list[float] = []
    max_face_event_error = 0.0
    with path.open(encoding="ascii") as stream:
        for line in stream:
            fields = line.split()
            if not fields or fields[0] != prefix:
                continue
            if len(fields) != 17:
                raise ValueError(f"invalid {prefix} compact row width")
            i, j, substep, row_mode, nlevels, nonzero_packets = map(int, fields[1:7])
            values = np.asarray(fields[7:], dtype=np.float64)
            if not np.isfinite(values).all() or row_mode != mode or nlevels < 1:
                raise ValueError(f"nonfinite or invalid {prefix} compact operands")
            if not 0 <= nonzero_packets <= nlevels:
                raise ValueError(f"invalid {prefix} nonzero packet count")
            key = (i, j, substep)
            if key in records:
                raise ValueError(f"duplicate {prefix} compact source event")
            stage = source.get(key)
            if stage is None or stage[0] != nlevels:
                raise ValueError(f"{prefix} compact row has no matching source stage")
            if len(values) != 10:
                raise ValueError(f"invalid {prefix} compact value count")
            (approved, packet_sum, donor_error, receiver_error, residual, stored_delta,
             ground_approved, store_change_abs, face_event_l1, max_face_error) = map(float, values)
            if approved != packet_sum:
                raise ValueError(f"{prefix} approved packet accumulator changed")
            row, col = j - bounds["jts"], i - bounds["its"]
            stage_kg = stage[1] * area[row, col]
            direct_kg = (donor_error + receiver_error) * area[row, col]
            operand_tolerance = 4 * np.finfo(np.float64).eps * max(
                abs(residual), abs(stage[1]), abs(stored_delta), abs(stage[2]),
                abs(ground_approved), abs(stage[3]), 1.0)
            if (abs(residual - stage[1]) > operand_tolerance or
                    abs(stored_delta - stage[2]) > operand_tolerance or
                    abs(ground_approved - stage[3]) > operand_tolerance):
                raise ValueError(f"{prefix} compact row does not repeat exact source operands")
            scale = max(abs(stage_kg), abs(stored_delta * area[row, col]),
                        abs(ground_approved * area[row, col]),
                        store_change_abs * area[row, col], 1.0)
            tolerance = 128 * np.finfo(np.float64).eps * scale * (nlevels + 2)
            if abs(residual - stage[1]) > tolerance / area[row, col] or abs(direct_kg - stage_kg) > tolerance:
                raise ValueError(f"{prefix} approved-face/store sum differs from independent source ledger")
            records[key] = (approved, packet_sum, donor_error, receiver_error, residual,
                            stored_delta, ground_approved, face_event_l1, max_face_error)
            records[key] = records[key] + (float(nonzero_packets),)
            face_event_l1_terms.append(face_event_l1 * area[row, col])
            max_face_event_error = max(max_face_event_error, max_face_error * area[row, col])
            value = direct_kg
            high = terms[row, col] + value
            back = high - terms[row, col]
            compensation[row, col] += (terms[row, col] - (high - back)) + (value - back)
            terms[row, col] = high
            column_events[row, col] += nlevels
    if set(records) != set(source):
        raise ValueError(f"{prefix} compact observer does not cover every source substep")
    terms += compensation
    return terms, column_events, {"substeps": len(records), "stage_rows": len(source),
        "columns_with_events": int(np.count_nonzero(column_events)),
        "accepted_face_records": int(np.sum(column_events)),
        "nonzero_approved_packet_records": int(sum(v[9] for v in records.values())),
        "L1_face_event_kg": math.fsum(face_event_l1_terms),
        "max_abs_face_event_kg": max_face_event_error,
        "approved_packet_kg": math.fsum(v[0] * area[k[1] - bounds["jts"], k[0] - bounds["its"]]
                                          for k, v in records.items()),
        "packet_sum_kg": math.fsum(v[1] * area[k[1] - bounds["jts"], k[0] - bounds["its"]]
                                    for k, v in records.items()),
        "donor_discrepancy_kg": math.fsum(v[2] * area[k[1] - bounds["jts"], k[0] - bounds["its"]]
                                           for k, v in records.items()),
        "receiver_discrepancy_kg": math.fsum(v[3] * area[k[1] - bounds["jts"], k[0] - bounds["its"]]
                                              for k, v in records.items()),
        "net_discrepancy": {"signed_kg": math.fsum(terms.flat),
                             "L1_column_kg": math.fsum(np.abs(terms).flat),
                             "max_abs_column_kg": float(np.max(np.abs(terms))),
                             "columns_with_events": int(np.count_nonzero(column_events))}}


def analyze(run_root: Path, pre_path: Path, post_path: Path, replay_post: Path,
            executable: Path, pre_source: Path, observer_source: Path,
            face_path: Path, rain_path: Path, ice_path: Path, cutoff_path: Path,
            liquid_path: Path, process_path: Path, manifest_path: Path,
            build_manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schema") != "pr98_face_replay_v1" or
            manifest.get("completion_marker") != "REPLAY COMPLETED FULL ACTIVE TILE" or
            manifest.get("completion_marker_observed") is not True or
            manifest.get("all_17_fields_and_XLAND_byte_equal") is not True):
        raise ValueError("face replay receipt lacks the full-tile marker and byte-equal state")
    if sha256(build_manifest_path) != manifest.get("build_manifest_sha256"):
        raise ValueError("face observer build receipt hash mismatch")
    build = json.loads(build_manifest_path.read_text(encoding="utf-8"))
    if (build.get("schema") != "pr98_face_observer_build_v1" or
            build.get("linked_executable_sha256") != manifest.get("executable_sha256") or
            build.get("pinned_ifx_sha256") != "909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef"):
        raise ValueError("face executable/compiler provenance is not pinned")
    if sha256(replay_post) != sha256(post_path):
        raise ValueError("face replay post state does not equal native returned state")
    for key, path in (("face_rows_sha256", face_path), ("executable_sha256", executable),
                      ("pre_sha256", pre_path), ("native_post_sha256", post_path),
                      ("replay_post_sha256", replay_post), ("prepared_source_sha256", pre_source),
                      ("observer_source_sha256", observer_source), ("rain_rows_sha256", rain_path),
                      ("ice_rows_sha256", ice_path), ("cutoff_rows_sha256", cutoff_path),
                      ("liquid_columns_sha256", liquid_path)):
        if sha256(path) != manifest.get(key):
            raise ValueError(f"face replay manifest mismatch: {key}")
    pre, post = read_dump(pre_path), read_dump(post_path)
    b = pre["bounds"]
    density = pre["fields"]["DEN"].astype(np.float64)
    thickness = pre["fields"]["DELZ"].astype(np.float64)
    history = run_root / "run" / HISTORY
    if sha256(history) != manifest["history_sha256"]:
        raise ValueError("face capture history geometry hash mismatch")
    with netCDF4.Dataset(history) as dataset:
        dataset.set_auto_mask(False)
        area, _, _ = _read_map_geometry(dataset,
            slice(b["jts"] - 1, b["jte"]), slice(b["its"] - 1, b["ite"]))
    terms = face_rows(face_path, b, density, thickness, area, rain_path, ice_path)
    rain, rain_counts, rain_stats = compact_face_rows(
        rain_path, rain_path, "PR98_SED_FACE_SUM", 3, b, area)
    ice, ice_counts, ice_stats = compact_face_rows(
        ice_path, ice_path, "PR98_SED_FACE_SUM", 1, b, area)
    combined = rain + ice
    combined_counts = np.maximum(rain_counts, ice_counts)
    baseline_report = json.loads((Path(__file__).resolve().parents[1] /
        "docs" / "evidence" / "pr98_t1_residual_20261022" / f"{manifest['arm']}.json").read_text())
    if baseline_report["identity"]["process_sha256"] != sha256(process_path):
        raise ValueError("native process stages differ from the same-arm baseline receipt")
    for label, path in (("pre_sha256", pre_path), ("post_sha256", post_path)):
        if baseline_report["identity"][label] != sha256(path):
            raise ValueError(f"same-arm baseline state differs: {label}")
    bottom = same_call_bottom(process_path, pre, area)
    water_delta = np.zeros_like(density * thickness * area[:, None, :])
    for field in WATER:
        water_delta += (post["fields"][field].astype(np.float64) -
                        pre["fields"][field].astype(np.float64)) * density * thickness * area[:, None, :]
    raw = np.sum(water_delta, axis=1, dtype=np.float64) + bottom
    cutoff, _, _, _ = cutoff_columns(cutoff_path, b, density, thickness, area)
    _, liquid_values = read_columns(liquid_path, b)
    liquid_term = (liquid_values[:, :, 0] + liquid_values[:, :, 1]) * area
    remaining = raw - liquid_term - cutoff
    remaining_after_face = remaining - combined

    def column_record(row: int, col: int) -> dict:
        return {
            "i": int(col + b["its"]), "j": int(row + b["jts"]),
            "R_raw_kg": float(raw[row, col]),
            "C_liquid_store_kg": float(liquid_term[row, col]),
            "C_cutoff_actual_store_change_kg": float(cutoff[row, col]),
            "C_accepted_rain_ice_face_store_discrepancy_kg": float(combined[row, col]),
            "remaining_after_cutoff_and_face_terms_kg": float(remaining_after_face[row, col]),
        }

    positive_index = int(np.argmax(remaining_after_face))
    negative_index = int(np.argmin(remaining_after_face))
    extreme_remaining_columns = {
        "largest_positive": column_record(*np.unravel_index(positive_index, remaining_after_face.shape)),
        "most_negative": column_record(*np.unravel_index(negative_index, remaining_after_face.shape)),
    }
    selected = {}
    for i, j in ((184, 147), (208, 79)):
        row, col = j - b["jts"], i - b["its"]
        selected[f"{i},{j}"] = {
            "R_raw_kg": float(raw[row, col]),
            "C_liquid_store_kg": float(liquid_term[row, col]),
            "C_cutoff_actual_store_change_kg": float(cutoff[row, col]),
            "C_accepted_rain_ice_face_store_discrepancy_kg": float(combined[row, col]),
            "remaining_after_cutoff_kg": float(remaining[row, col]),
            "remaining_after_cutoff_and_face_terms_kg": float(remaining_after_face[row, col]),
        }
    compact = {"rain": rain_stats, "ice": ice_stats,
        "combined_net_discrepancy": {"signed_kg": math.fsum(combined.flat),
            "L1_column_kg": math.fsum(np.abs(combined).flat),
            "max_abs_column_kg": float(np.max(np.abs(combined))),
            "columns_with_events": int(np.count_nonzero(combined_counts))},
        "open_residual_after_independent_face_term": stats(remaining_after_face),
        "extreme_remaining_columns_by_sign": extreme_remaining_columns,
        "selected_columns_after_independent_face_term": selected}
    return {"schema": "pr98_selected_sedimentation_face_account_v1", "arm": manifest["arm"],
            "source_terms_are_independent": True,
            "definition": "per accepted face, (stored donor Q change * DEN * DELZ + theta*pq) + (stored receiver Q change * DEN * DELZ - theta*pq); ground face has no receiver",
            "interpretation": "source-stage accepted-packet/store discrepancy, with local source-ledger agreement; includes REAL32 representation and REAL64 accumulation effects and is not labelled pure R32 rounding",
            "selected_face_capture": terms, "compact_full_tile_face_capture": compact,
        "same_call_budget_identity": {
            key: baseline_report["identity"][key]
            for key in ("receipt_sha256", "pre_sha256", "post_sha256", "process_sha256",
                        "replay_post_sha256", "all_17_fields_and_XLAND_byte_equal")},
        "pr99_reducer_source_sha256": sha256(Path(__file__).resolve()),
        "baseline_budget_report_sha256": sha256(Path(__file__).resolve().parents[1] /
            "docs" / "evidence" / "pr98_t1_residual_20261022" / f"{manifest['arm']}.json"),
            "identity": manifest,
            "physical_approval": "FAIL_OPEN"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-root", "pre", "post", "replay-post", "executable", "prepared-source",
                 "observer-source", "face-rows", "rain-rows", "ice-rows", "cutoff-rows",
                 "liquid-columns", "process", "manifest",
                 "build-manifest", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.run_root, args.pre, args.post, args.replay_post,
                     args.executable, args.prepared_source, args.observer_source,
                     args.face_rows, args.rain_rows, args.ice_rows, args.cutoff_rows,
                     args.liquid_columns, args.process, args.manifest,
                     args.build_manifest)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
