#!/usr/bin/env python3
"""Summarize the RN1_10942 OLD phase-15/phase-05 corner-event diagnostic."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


POINT_ID = "RN1_10942"
FIELDS = (
    "phase15_prevp",
    "phase15_prevp_present",
    "phase05_prevp",
    "phase05_prevp_present",
    "phase06_q",
    "phase08_q",
    "phase06_t",
    "phase08_t",
    "phase8_minus_phase6_QV",
    "phase8_minus_phase6_TK",
    "PREVP_times_dtcld_source_term",
)
WINDOWS = ((1, 1, 180), (2, 181, 360))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_point_field(root: Path, field: str, lead: int) -> tuple[np.ndarray, np.ndarray, tuple[int, ...]]:
    path = root / field / f"lead_{lead:02d}" / f"{field}.npz"
    with np.load(path, allow_pickle=False) as data:
        point_ids = data["point_ids"].astype(str)
        matches = np.flatnonzero(point_ids == POINT_ID)
        if len(matches) != 1:
            raise ValueError(f"{path}: expected exactly one {POINT_ID} row")
        row = int(matches[0])
        columns = data["point_native_corner_indices"][row]
        weights = data["point_corner_weights"][row]
        if columns.shape != (4,) or np.count_nonzero(weights > 0) != 4:
            raise ValueError(f"{path}: expected four positive-weight native corners")
        values = np.take(data["native_values"], columns[weights > 0], axis=-1)
        return data["actual_timestep"].copy(), values, tuple(map(int, columns))


def summarize(root: Path) -> tuple[list[dict], list[Path], dict, np.ndarray, np.ndarray, np.ndarray]:
    rows = []
    inputs = []
    retained = {field: [] for field in FIELDS}
    all_times = []
    point_columns = None
    point_weights = None
    for lead, start, end in WINDOWS:
        arrays = {}
        times_ref = None
        corners_ref = None
        for field in FIELDS:
            path = root / field / f"lead_{lead:02d}" / f"{field}.npz"
            times, values, corners = load_point_field(root, field, lead)
            inputs.append(path)
            if times_ref is None:
                times_ref = times
                corners_ref = corners
            elif not np.array_equal(times, times_ref) or corners != corners_ref:
                raise ValueError(f"{path}: actual timestep/corner mapping changed between channels")
            arrays[field] = values

        assert times_ref is not None
        if point_columns is None:
            point_columns = np.asarray(corners_ref, dtype=np.int32)
            weights_path = root / FIELDS[0] / f"lead_{lead:02d}" / f"{FIELDS[0]}.npz"
            with np.load(weights_path, allow_pickle=False) as data:
                q = int(np.flatnonzero(data["point_ids"].astype(str) == POINT_ID)[0])
                point_weights = data["point_corner_weights"][q].copy()
        elif tuple(map(int, point_columns)) != corners_ref:
            raise ValueError("point corner indices changed between lead blocks")
        all_times.append(times_ref)
        for field in FIELDS:
            retained[field].append(arrays[field])
        step_mask = (times_ref >= start) & (times_ref <= end)
        if int(step_mask.sum()) != end - start + 1:
            raise ValueError(f"lead {lead}: missing steps inside {start}–{end}")
        if int(times_ref[step_mask][0]) != start or int(times_ref[step_mask][-1]) != end:
            raise ValueError(f"lead {lead}: unexpected timestep bounds")

        phase15_present = arrays["phase15_prevp_present"].astype(bool)
        phase05_present = arrays["phase05_prevp_present"].astype(bool)
        event = (phase15_present & phase05_present &
                 (arrays["phase15_prevp"] == 0) & (arrays["phase05_prevp"] < 0))
        event &= step_mask[:, None, None]
        qv_nonzero = event & (arrays["phase8_minus_phase6_QV"] != 0)
        tk_nonzero = event & (arrays["phase8_minus_phase6_TK"] != 0)
        nominal = np.abs(arrays["PREVP_times_dtcld_source_term"])
        selected_nominal = nominal[event]
        rows.append({
            "arm": "OLD",
            "point_id": POINT_ID,
            "lead_block": lead,
            "first_actual_timestep": start,
            "last_actual_timestep": end,
            "positive_weight_corner_count": 4,
            "vertical_levels": 39,
            "phase15_prev_zero_and_phase05_prev_negative_corner_events": int(event.sum()),
            "events_with_nonzero_actual_qv_delta": int(qv_nonzero.sum()),
            "events_with_nonzero_actual_tk_delta": int(tk_nonzero.sum()),
            "events_with_either_nonzero_actual_delta": int((qv_nonzero | tk_nonzero).sum()),
            "max_abs_phase05_prevp_times_dtcld": float(selected_nominal.max()) if selected_nominal.size else None,
            "event_unit": "native corner × level × actual timestep; not independent observations",
        })

    assert point_columns is not None and point_weights is not None
    return rows, inputs, retained, np.concatenate(all_times), point_columns, point_weights


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--capture-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    rows, inputs, retained, actual_timestep, corner_indices, corner_weights = summarize(args.capture_root)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    csv_path = args.output_dir / "p01_prevp_zero_actual_delta.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    native_path = args.output_dir / "p01_native_corner_process.npz"
    native_arrays = {
        "actual_timestep": actual_timestep.astype(np.int32),
        "point_id": np.asarray(POINT_ID),
        "point_native_corner_indices": corner_indices,
        "point_corner_weights": corner_weights,
    }
    native_arrays.update({field: np.concatenate(blocks, axis=0) for field, blocks in retained.items()})
    np.savez_compressed(native_path, **native_arrays)
    receipt_path = args.output_dir / "receipt.json"
    receipt = {
        "status": "COMPUTED_FROM_STRICT_FULL_CAPTURE",
        "capture_receipt": str(args.capture_receipt),
        "capture_receipt_sha256": sha256(args.capture_receipt),
        "capture_root": str(args.capture_root),
        "point_id": POINT_ID,
        "selection": "phase15 raw PREVP == 0 and phase05 final PREVP < 0 at each of four positive-weight corners and each of 39 levels",
        "actual_delta_channels": ["phase8_minus_phase6_QV", "phase8_minus_phase6_TK"],
        "nominal_channel": "PREVP_times_dtcld_source_term",
        "raw_qv_t_channels": ["phase06_q", "phase08_q", "phase06_t", "phase08_t"],
        "event_unit": "native corner × level × actual timestep; not independent observations",
        "source_arrays": [{"path": str(path), "sha256": sha256(path)} for path in inputs],
        "summary_csv": {"path": csv_path.name, "sha256": sha256(csv_path)},
        "native_corner_npz": {"path": native_path.name, "sha256": sha256(native_path),
                               "actual_timesteps": [1, 360], "vertical_levels": 39,
                               "positive_weight_corners": 4,
                               "phase15_values_preserved_with_presence_mask": True},
        "rows": rows,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(csv_path), "receipt": str(receipt_path), "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
