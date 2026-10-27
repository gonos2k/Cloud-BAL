#!/usr/bin/env python3
"""Focused validation tests for the archived hourly precipitation scorer."""
from __future__ import annotations

import csv
import hashlib
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from plot_hourly_precip_scores import (  # noqa: E402
    ARCHIVED_THRESHOLDS,
    CASES,
    LEADS,
    REQUIRED_FIELDS,
    THRESHOLDS,
    add_not_evaluated_rows,
    build_summary,
    load_and_score,
    longitude_aspect_ratio,
    prepare_output_dir,
    score_first_hour_pairs,
)


START = "2026-08-16T12:00:00Z"
EXPECTED_CELLS = 3688


def fixture_rows() -> list[dict[str, object]]:
    start = datetime.strptime(START, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    rows = []
    for case in CASES:
        for lead in LEADS:
            for threshold in ARCHIVED_THRESHOLDS:
                hit, miss, false_alarm, correct_dry = 1, 2, 1, EXPECTED_CELLS - 4
                if case == "OFF" and lead == 1 and threshold == 0.1:
                    hit, miss, false_alarm, correct_dry = 0, 0, 1, EXPECTED_CELLS - 1
                denominator = hit + miss + false_alarm
                rows.append({
                    "case": case,
                    "lead_hour": lead,
                    "valid_utc": (start + timedelta(hours=lead)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "threshold_mm": threshold,
                    "valid_cells": EXPECTED_CELLS,
                    "hit": hit,
                    "miss": miss,
                    "false_alarm": false_alarm,
                    "correct_dry": correct_dry,
                    "CSI": hit / denominator,
                })
    return rows


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=REQUIRED_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


class HourlyPrecipScoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.csv_path = Path(self.temp.name) / "counts.csv"
        self.rows = fixture_rows()
        write_rows(self.csv_path, self.rows)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_longitude_plot_aspect_compensates_for_latitude(self) -> None:
        self.assertAlmostEqual(longitude_aspect_ratio(0.0), 1.0)
        self.assertAlmostEqual(longitude_aspect_ratio(60.0), 2.0)
        with self.assertRaisesRegex(ValueError, "latitude must be finite"):
            longitude_aspect_ratio(90.0)

    def test_scores_complete_fixed_contract(self) -> None:
        scored = load_and_score(self.csv_path, START, expected_cells=EXPECTED_CELLS)
        self.assertEqual(len(scored), 72)
        first = next(row for row in scored if row["case"] == "OFF" and row["lead_hour"] == 1 and row["threshold_mm"] == 0.1)
        self.assertEqual(first["window_start_utc"], START)
        self.assertEqual(first["window_end_utc"], "2026-08-16T13:00:00Z")
        self.assertIsNone(first["POD"])
        self.assertEqual(first["FAR"], 1.0)
        self.assertIsNone(first["frequency_bias"])

    def test_zero_event_scores_are_undefined(self) -> None:
        zero_event = self.rows[0]
        zero_event.update(hit=0, miss=0, false_alarm=0, correct_dry=EXPECTED_CELLS, CSI="")
        write_rows(self.csv_path, self.rows)
        scored = load_and_score(self.csv_path, START, expected_cells=EXPECTED_CELLS)
        first = next(row for row in scored if row["case"] == "OFF" and row["lead_hour"] == 1 and row["threshold_mm"] == 0.1)
        self.assertIsNone(first["CSI"])
        self.assertIsNone(first["POD"])
        self.assertIsNone(first["FAR"])
        self.assertIsNone(first["frequency_bias"])
        rows = add_not_evaluated_rows(load_and_score(self.csv_path, START, expected_cells=EXPECTED_CELLS), START)
        summary = build_summary(rows, START, self.csv_path)
        self.assertEqual(summary["scope"]["evaluated_rows"], 72)

    def test_rejects_numeric_csi_for_zero_event(self) -> None:
        self.rows[0].update(hit=0, miss=0, false_alarm=0, correct_dry=EXPECTED_CELLS, CSI=0.0)
        write_rows(self.csv_path, self.rows)
        with self.assertRaisesRegex(ValueError, "CSI must be blank"):
            load_and_score(self.csv_path, START, expected_cells=EXPECTED_CELLS)

    def test_rejects_wrong_window(self) -> None:
        self.rows[0]["valid_utc"] = "2026-08-16T14:00:00Z"
        write_rows(self.csv_path, self.rows)
        with self.assertRaisesRegex(ValueError, "valid_utc mismatch"):
            load_and_score(self.csv_path, START, expected_cells=EXPECTED_CELLS)

    def test_rejects_duplicate_row(self) -> None:
        self.rows[-1] = dict(self.rows[0])
        write_rows(self.csv_path, self.rows)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_and_score(self.csv_path, START, expected_cells=EXPECTED_CELLS)

    def test_rejects_missing_row(self) -> None:
        write_rows(self.csv_path, self.rows[:-1])
        with self.assertRaisesRegex(ValueError, "expected 72 archived rows"):
            load_and_score(self.csv_path, START, expected_cells=EXPECTED_CELLS)

    def test_rejects_bad_count_sum(self) -> None:
        self.rows[0]["correct_dry"] = 5
        write_rows(self.csv_path, self.rows)
        with self.assertRaisesRegex(ValueError, "do not sum"):
            load_and_score(self.csv_path, START, expected_cells=EXPECTED_CELLS)

    def test_rejects_noncanonical_threshold(self) -> None:
        self.rows[0]["threshold_mm"] = 0.1000001
        write_rows(self.csv_path, self.rows)
        with self.assertRaisesRegex(ValueError, "unexpected case/lead/threshold"):
            load_and_score(self.csv_path, START, expected_cells=EXPECTED_CELLS)

    def test_requires_fresh_output_directory_and_preserves_input(self) -> None:
        original = self.csv_path.read_bytes()
        output = Path(self.temp.name) / "new-output"
        prepare_output_dir(output)
        self.assertTrue(output.is_dir())
        self.assertEqual(self.csv_path.read_bytes(), original)
        (output / "sentinel").write_text("keep")
        with self.assertRaisesRegex(ValueError, "must not exist or must be empty"):
            prepare_output_dir(output)
        self.assertTrue((output / "sentinel").exists())
        self.assertEqual(self.csv_path.read_bytes(), original)

    def test_only_declared_new_threshold_leads_are_not_evaluated(self) -> None:
        rows = add_not_evaluated_rows(load_and_score(self.csv_path, START, expected_cells=EXPECTED_CELLS), START, EXPECTED_CELLS)
        self.assertEqual(len(rows), 108)
        missing = [row for row in rows if row["status"] == "NOT_EVALUATED"]
        self.assertEqual(len(missing), 36)
        self.assertTrue(all(row["threshold_mm"] in (0.5, 2.5) for row in missing))
        self.assertTrue(all(row["lead_hour"] in LEADS for row in missing))
        self.assertTrue(all(row["valid_cells"] is None for row in missing))
        self.assertTrue(all(row["CSI"] is None for row in missing))

    def test_new_first_hour_thresholds_include_values_equal_to_cutoff(self) -> None:
        pairs_path = Path(self.temp.name) / "first_hour_pairs.npz"
        fields = {case: np.zeros(EXPECTED_CELLS) for case in CASES}
        reference = np.zeros(EXPECTED_CELLS)
        reference[:4] = [0.5, 2.5, 5.0, 10.0]
        for case in CASES:
            fields[case][:4] = [0.5, 2.5, 5.0, 10.0]
        np.savez(pairs_path, **fields, reference=reference,
                 latitude=np.zeros(EXPECTED_CELLS), longitude=np.zeros(EXPECTED_CELLS),
                 flat_index_yx=np.arange(EXPECTED_CELLS))
        receipt = {
            "status": "DERIVED_RETAINED_INTERMEDIATE",
            "window_start_utc": START,
            "window_end_utc": "2026-08-16T13:00:00Z",
            "cells": EXPECTED_CELLS,
            "raw_RN1_reingested": False,
            "derived_npz": {"sha256": hashlib.sha256(pairs_path.read_bytes()).hexdigest()},
        }
        pairs_path.with_name("first_hour_pairs_receipt.json").write_text(json.dumps(receipt))

        # Replace lead-1 archival contingency counts with the corresponding array-derived counts.
        for row in self.rows:
            if row["lead_hour"] != 1 or row["threshold_mm"] not in ARCHIVED_THRESHOLDS:
                continue
            case = row["case"]
            threshold = row["threshold_mm"]
            h = int(np.count_nonzero((fields[case] >= threshold) & (reference >= threshold)))
            m = int(np.count_nonzero((fields[case] < threshold) & (reference >= threshold)))
            f = int(np.count_nonzero((fields[case] >= threshold) & (reference < threshold)))
            row.update(hit=h, miss=m, false_alarm=f, correct_dry=EXPECTED_CELLS-h-m-f,
                       CSI=h/(h+m+f) if h+m+f else "")
        write_rows(self.csv_path, self.rows)
        archive_rows = load_and_score(self.csv_path, START, expected_cells=EXPECTED_CELLS)
        additions = score_first_hour_pairs(pairs_path, archive_rows, START)
        first = next(row for row in additions if row["case"] == "OFF" and row["threshold_mm"] == 0.5)
        self.assertEqual(first["hit"], 4)  # Values exactly on a cutoff meet >= threshold.
        self.assertEqual(first["miss"], 0)
        self.assertEqual(first["false_alarm"], 0)

    def test_rejects_first_hour_pair_receipt_hash_mismatch(self) -> None:
        pairs_path = Path(self.temp.name) / "first_hour_pairs.npz"
        np.savez(pairs_path)
        receipt = {
            "status": "DERIVED_RETAINED_INTERMEDIATE",
            "window_start_utc": START,
            "window_end_utc": "2026-08-16T13:00:00Z",
            "cells": EXPECTED_CELLS,
            "raw_RN1_reingested": False,
            "derived_npz": {"sha256": "0" * 64},
        }
        pairs_path.with_name("first_hour_pairs_receipt.json").write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            score_first_hour_pairs(pairs_path, [], START)

    def test_rejects_first_hour_pair_receipt_wrong_window(self) -> None:
        pairs_path = Path(self.temp.name) / "first_hour_pairs.npz"
        np.savez(pairs_path)
        receipt = {
            "status": "DERIVED_RETAINED_INTERMEDIATE",
            "window_start_utc": "2026-08-16T11:00:00Z",
            "window_end_utc": "2026-08-16T12:00:00Z",
            "cells": EXPECTED_CELLS,
            "raw_RN1_reingested": False,
            "derived_npz": {"sha256": hashlib.sha256(pairs_path.read_bytes()).hexdigest()},
        }
        pairs_path.with_name("first_hour_pairs_receipt.json").write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "window start"):
            score_first_hour_pairs(pairs_path, [], START)


if __name__ == "__main__":
    unittest.main()
