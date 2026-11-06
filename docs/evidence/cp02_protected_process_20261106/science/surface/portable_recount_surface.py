#!/usr/bin/env python3
"""Rebuild and byte-compare the hourly point surface table from its compact NPZ packet."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import numpy as np

FIELDS = ("arm", "frozen_score_case", "point_id", "flat_index_yx", "sample_index_zero_based",
          "latitude", "longitude", "lead_hour", "valid_hour_utc", "window_start_hour_utc",
          "window_end_hour_utc", "RAINNC_hour_mm", "RAINC_hour_mm", "total_hour_mm",
          "frozen_3688_hour_total_mm", "actual_minus_frozen_mm")
ARMS = ("OLD", "FIX")
HISTORY_HOURS = tuple(range(12, 18))
LEADS = tuple(range(1, 6))


def sha(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def rebuild(packet_path: Path, packet_receipt_path: Path, reference_csv: Path) -> tuple[bytes, dict]:
    receipt = json.loads(packet_receipt_path.read_text(encoding="utf-8"))
    if receipt.get("status") != "PASS_PACKET_EXTRACTED_FROM_VALIDATED_HISTORY_AND_FROZEN_SCORE_ARRAYS":
        raise ValueError("portable packet receipt is not a validated extraction")
    if (packet_path.stat().st_size != receipt.get("packet_size_bytes")
            or sha(packet_path) != receipt.get("packet_sha256")):
        raise ValueError("portable packet identity differs from its receipt")
    if (reference_csv.stat().st_size != receipt.get("reference_table_size_bytes")
            or sha(reference_csv) != receipt.get("reference_table_sha256")):
        raise ValueError("reference CSV identity differs from its packet receipt")
    if len(receipt.get("native_surface_endpoint_checks", {})) != 2:
        raise ValueError("packet receipt lacks both-arm native surface endpoint checks")
    for arm in ARMS:
        checks = receipt["native_surface_endpoint_checks"].get(arm, {})
        if set(checks) != {str(lead) for lead in LEADS} or not all(
                row.get("bitwise_equal_to_RAINNC") and row.get("mismatch_count") == 0
                and row.get("native_columns") == 381 for row in checks.values()):
            raise ValueError(f"{arm}: packet receipt lacks exact five-hour RAINNC endpoint validation")

    with np.load(packet_path, allow_pickle=False) as archive:
        packet = {key: archive[key].copy() for key in archive.files}
    required = {"arm_labels", "score_case_labels", "history_hours_utc", "history_timestamps_utc",
                "native_column_ids", "native_i_1based", "native_j_1based", "RAINNC_history_mm",
                "RAINC_history_mm", "KDM6_surface_rain_cumulative_lead_end_mm", "point_ids",
                "point_flat_index_yx", "point_sample_index_zero_based", "point_latitude",
                "point_longitude", "point_native_corner_indices", "point_corner_weights",
                "frozen_score_hour_total_mm"}
    if not required <= packet.keys():
        raise ValueError(f"portable packet is missing fields: {sorted(required - packet.keys())}")
    if (not np.array_equal(packet["arm_labels"], np.asarray(ARMS))
            or not np.array_equal(packet["score_case_labels"], np.asarray(["ORIGINAL_B1_100", "IMPROVED_BG_FIXED"]))
            or not np.array_equal(packet["history_hours_utc"], np.asarray(HISTORY_HOURS))
            or not np.array_equal(packet["history_timestamps_utc"],
                                  np.asarray([[f"2026-08-16_{hour:02d}:00:00" for hour in HISTORY_HOURS]] * 2))
            or packet["native_column_ids"].shape != (381,)
            or len(set(packet["native_column_ids"].tolist())) != 381
            or packet["native_i_1based"].shape != (381,) or packet["native_j_1based"].shape != (381,)
            or (packet["native_i_1based"] < 1).any() or (packet["native_j_1based"] < 1).any()
            or len(set(zip(packet["native_i_1based"], packet["native_j_1based"]))) != 381):
        raise ValueError("portable packet native arm/time/column mapping is invalid")
    if (packet["RAINNC_history_mm"].shape != (2, 6, 381)
            or packet["RAINC_history_mm"].shape != (2, 6, 381)
            or packet["KDM6_surface_rain_cumulative_lead_end_mm"].shape != (2, 5, 381)
            or packet["point_ids"].shape != (150,)
            or len(set(packet["point_ids"].tolist())) != 150
            or packet["point_flat_index_yx"].shape != (150,)
            or packet["point_sample_index_zero_based"].shape != (150,)
            or packet["point_latitude"].shape != (150,) or packet["point_longitude"].shape != (150,)
            or packet["point_native_corner_indices"].shape != (150, 4)
            or packet["point_corner_weights"].shape != (150, 4)
            or packet["frozen_score_hour_total_mm"].shape != (2, 5, 150)):
        raise ValueError("portable packet selected-point or endpoint shape is invalid")
    if (packet["RAINNC_history_mm"].dtype != np.float32
            or packet["RAINC_history_mm"].dtype != np.float32
            or packet["KDM6_surface_rain_cumulative_lead_end_mm"].dtype != np.float32
            or packet["point_corner_weights"].dtype != np.float64):
        raise ValueError("portable packet violates exact history/weight dtype contract")
    for key in ("RAINNC_history_mm", "RAINC_history_mm", "KDM6_surface_rain_cumulative_lead_end_mm",
                "point_latitude", "point_longitude", "point_corner_weights", "frozen_score_hour_total_mm"):
        if not np.isfinite(packet[key]).all():
            raise ValueError(f"portable packet contains nonfinite values: {key}")
    if (packet["point_native_corner_indices"].min() < 0 or packet["point_native_corner_indices"].max() >= 381
            or (packet["point_corner_weights"] < 0).any()
            or not np.allclose(packet["point_corner_weights"].sum(axis=1), 1.0, rtol=0, atol=1e-12)):
        raise ValueError("portable packet has invalid bilinear point stencils")
    for arm_index, _arm in enumerate(ARMS):
        if not np.array_equal(packet["KDM6_surface_rain_cumulative_lead_end_mm"][arm_index].view(np.uint32),
                              packet["RAINNC_history_mm"][arm_index, 1:].view(np.uint32)):
            raise ValueError(f"{_arm}: packet KDM6 endpoints differ from its RAINNC history values")

    rows = []
    for arm_index, arm in enumerate(ARMS):
        score_case = str(packet["score_case_labels"][arm_index])
        for lead_index, lead in enumerate(LEADS):
            start_index = lead_index
            end_index = lead_index + 1
            delta_nc = (packet["RAINNC_history_mm"][arm_index, end_index].astype(np.float64)
                        - packet["RAINNC_history_mm"][arm_index, start_index].astype(np.float64))
            delta_c = (packet["RAINC_history_mm"][arm_index, end_index].astype(np.float64)
                       - packet["RAINC_history_mm"][arm_index, start_index].astype(np.float64))
            for point_index, point_id in enumerate(packet["point_ids"]):
                corner_ids = packet["point_native_corner_indices"][point_index]
                weights = packet["point_corner_weights"][point_index]
                nc_hour = float(np.dot(delta_nc[corner_ids], weights))
                c_hour = float(np.dot(delta_c[corner_ids], weights))
                total = nc_hour + c_hour
                frozen = float(packet["frozen_score_hour_total_mm"][arm_index, lead_index, point_index])
                if abs(total - frozen) > 1e-12:
                    raise ValueError(f"{arm} lead {lead} {point_id}: hourly total differs from the frozen score")
                rows.append({"arm": arm, "frozen_score_case": score_case, "point_id": str(point_id),
                             "flat_index_yx": int(packet["point_flat_index_yx"][point_index]),
                             "sample_index_zero_based": int(packet["point_sample_index_zero_based"][point_index]),
                             "latitude": float(packet["point_latitude"][point_index]),
                             "longitude": float(packet["point_longitude"][point_index]),
                             "lead_hour": lead, "valid_hour_utc": 12 + lead,
                             "window_start_hour_utc": 11 + lead, "window_end_hour_utc": 12 + lead,
                             "RAINNC_hour_mm": nc_hour, "RAINC_hour_mm": c_hour,
                             "total_hour_mm": total, "frozen_3688_hour_total_mm": frozen,
                             "actual_minus_frozen_mm": total - frozen})
    if len(rows) != 1500:
        raise ValueError(f"portable packet produced {len(rows)} rows, expected 1500")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    rebuilt = stream.getvalue().encode("utf-8")
    if rebuilt != reference_csv.read_bytes():
        raise ValueError("portable packet reconstruction is not byte-identical to the reference CSV")
    result = {"status": "PASS_PORTABLE_PACKET_RECOUNT_BYTEWISE_IDENTICAL",
              "recounter_sha256": sha(Path(__file__)),
              "rows": len(rows), "arm_count": len(ARMS), "points_per_arm": 150,
              "hour_windows_per_arm": list(LEADS), "native_columns": 381,
              "max_absolute_difference_from_frozen_score_mm": max(abs(row["actual_minus_frozen_mm"]) for row in rows),
              "absolute_tolerance_mm": 1e-12,
              "endpoint_history_hours_utc": list(HISTORY_HOURS),
              "packet_sha256": sha(packet_path), "packet_receipt_sha256": sha(packet_receipt_path),
              "reference_csv_sha256": sha(reference_csv), "rebuilt_csv_sha256": hashlib.sha256(rebuilt).hexdigest(),
              "byte_identical": True,
              "external_dependencies_used": [],
              "limits": ["This recounter uses only the portable NPZ packet, its receipt, and the reference CSV; NetCDF and frozen source score arrays are not opened.",
                         "It verifies the packet’s recorded endpoint match and repeats packet-internal endpoint equality; original NetCDF source hashes and timestamps are preserved in the packet receipt.",
                         "The portable recomputation validates the table derivation, not the provenance of the original history extraction."]}
    return rebuilt, result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--packet-receipt", type=Path, required=True)
    parser.add_argument("--reference-csv", type=Path, required=True)
    parser.add_argument("--output-receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.output_receipt.exists() or args.output_receipt.is_symlink():
        raise FileExistsError(args.output_receipt)
    _rebuilt, result = rebuild(args.packet, args.packet_receipt, args.reference_csv)
    args.output_receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output_receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "rows": result["rows"], "byte_identical": result["byte_identical"]}, sort_keys=True))


if __name__ == "__main__":
    main()
