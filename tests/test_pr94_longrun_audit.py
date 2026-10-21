from __future__ import annotations

import gzip
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import netCDF4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr94_longrun_audit as audit  # noqa: E402


class CompactProfileTests(unittest.TestCase):
    def records(self, completed: int = 35) -> list[dict]:
        rows = []
        for step in range(1, completed + 1):
            states = (audit.EXPECTED_SEQUENCE if step <= 30 or step in audit.DETAIL_STEPS
                      else (("POST_KDM6", 0),))
            rows.extend({"timestep": step, "stage": stage, "rkstep": rk}
                        for stage, rk in states)
        return rows

    def test_accepts_full_prefix_snapshots_and_post_cadence(self):
        result = audit.validate_compact_state_profile(self.records(), list(range(1, 36)))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["retained_state_records"], 30 * 6 + 5)
        self.assertEqual(result["post_only_steps"], [31, 32, 33, 34, 35])

    def test_rejects_missing_extra_and_wrong_rk_records(self):
        rows = self.records()
        rows.remove(next(row for row in rows if row["timestep"] == 4 and row["stage"] == "RK_STAGE_END" and row["rkstep"] == 2))
        with self.assertRaises(audit.LongrunAuditError):
            audit.validate_compact_state_profile(rows, list(range(1, 36)))

        rows = self.records()
        rows.append({"timestep": 31, "stage": "PRE_RK", "rkstep": 0})
        with self.assertRaises(audit.LongrunAuditError):
            audit.validate_compact_state_profile(rows, list(range(1, 36)))

        rows = self.records(60)
        next(row for row in rows if row["timestep"] == 60 and row["stage"] == "RK_STAGE_END")["rkstep"] = 3
        with self.assertRaises(audit.LongrunAuditError):
            audit.validate_compact_state_profile(rows, list(range(1, 61)))

    def test_profile_metadata_does_not_retain_state_arrays(self):
        record = {"timestep": 1, "stage": "POST_KDM6", "rkstep": 0,
                  "fields": {"QC": object()}}
        self.assertEqual(audit._profile_metadata(record),
                         {"timestep": 1, "stage": "POST_KDM6", "rkstep": 0})


class RuntimeBindingTests(unittest.TestCase):
    def test_rejects_wrong_executable_hash(self):
        build = {"executable_sha256": "expected", "receipt_sha256": "receipt"}
        preflight = {"candidate_build": build, "output": "/missing/run"}
        receipt = {"executed_executable_sha256": "wrong",
                   "expected_executed_executable_sha256": "expected",
                   "candidate_build": build}
        with self.assertRaises(audit.LongrunAuditError):
            audit._verify_executable_binding(receipt, preflight, "expected", "manufactured")


class PrefixComparisonTests(unittest.TestCase):
    def _write_trace(self, path: Path, steps: int = 30, mutate: bool = False) -> dict:
        expanded = bytearray()
        bounds = (1, 2, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1)
        header_tail = (0,) * 3 + bounds
        with path.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
                for step in range(1, steps + 1):
                    for stage, rkstep in audit.EXPECTED_SEQUENCE:
                        magic = b"PR85QND2"
                        label = stage.encode("ascii").ljust(32, b" ")
                        header = np.asarray((1, step, rkstep, *bounds), dtype=">i4").tobytes()
                        fields = []
                        for index, _name in enumerate(audit.FIELDS):
                            values = np.asarray([step, index], dtype=">f4")
                            if mutate and step == 12 and stage == "POST_KDM6" and index == 0:
                                values[1] = np.float32(999)
                            fields.append(values.tobytes())
                        record = magic + label + header + b"".join(fields)
                        stream.write(record)
                        expanded.extend(record)
        raw_bytes = path.read_bytes()
        return {"path": path.name.removesuffix(".gz"), "sha256": hashlib.sha256(expanded).hexdigest(),
                "bytes": len(expanded), "compressed_path": path.name,
                "compressed_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "compressed_bytes": len(raw_bytes)}

    def _receipt(self, row: dict, completed: int = 30) -> dict:
        return {"snapshots": {"completed_post_kdm6_timesteps": list(range(1, completed + 1)),
                              "duplicate_post_kdm6_timesteps": []},
                "final_completed_step": completed,
                "compressed_outputs": [row],
                "generated_files": [{"path": row["path"], "sha256": row["sha256"], "bytes": row["bytes"]}]}

    def test_prefix_bytes_match_and_detect_changed_field(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline = Path(temp) / "baseline"
            compact = Path(temp) / "compact"
            (baseline / "run").mkdir(parents=True)
            (compact / "run").mkdir(parents=True)
            base_row = self._write_trace(baseline / "run" / audit.TRACE_NAME)
            good_row = self._write_trace(compact / "run" / audit.TRACE_NAME)
            good = audit.compare_first_600_seconds(baseline, self._receipt(base_row),
                                                   compact, self._receipt(good_row), "OFF")
            self.assertEqual(good["status"], "PASS")
            self.assertEqual(good["compared_state_records"], 180)

            bad_row = self._write_trace(compact / "run" / audit.TRACE_NAME, mutate=True)
            bad = audit.compare_first_600_seconds(
                baseline, self._receipt(base_row), compact,
                self._receipt(bad_row), "OFF")
            self.assertEqual(bad["status"], "FAIL")
            self.assertIn("step 12", bad["differences"][0])

    def test_partial_completed_prefix_is_reported_as_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline = Path(temp) / "baseline"
            compact = Path(temp) / "compact"
            (baseline / "run").mkdir(parents=True)
            (compact / "run").mkdir(parents=True)
            base_row = self._write_trace(baseline / "run" / audit.TRACE_NAME)
            partial_row = self._write_trace(compact / "run" / audit.TRACE_NAME, steps=3)
            result = audit.compare_first_600_seconds(
                baseline, self._receipt(base_row), compact,
                self._receipt(partial_row, completed=3), "OFF")
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(result["common_prefix_steps"], 3)
            self.assertEqual(result["compared_state_records"], 18)


class ClosedHistoryComparisonTests(unittest.TestCase):
    timestamps = audit.HISTORY_TIMES[:2]
    layouts = {
        "T": ("bottom_top", "south_north", "west_east"),
        "P": ("bottom_top", "south_north", "west_east"),
        "PB": ("bottom_top", "south_north", "west_east"),
        "PH": ("bottom_top_stag", "south_north", "west_east"),
        "PHB": ("bottom_top_stag", "south_north", "west_east"),
        "U": ("bottom_top", "south_north", "west_east_stag"),
        "V": ("bottom_top", "south_north_stag", "west_east"),
        "W": ("bottom_top_stag", "south_north", "west_east"),
        "MU": ("south_north", "west_east"),
        "MUB": ("south_north", "west_east"),
    }

    def _history(self, path: Path, *, mutate: str | None = None,
                 dtype_change: str | None = None, units_change: str | None = None,
                 include_second: bool = True, fill: str | None = None,
                 stagger_change: str | None = None,
                 dimension_change: str | None = None,
                 spatial_extent: int = 2,
                 time_indices: tuple[int, ...] | None = None) -> dict:
        times = (tuple(audit.HISTORY_TIMES[index] for index in time_indices)
                 if time_indices is not None else
                 self.timestamps if include_second else self.timestamps[:1])
        with netCDF4.Dataset(path, "w") as ds:
            ds.createDimension("Time", None)
            ds.createDimension("DateStrLen", 19)
            for dimension in {name for dims in self.layouts.values() for name in dims}:
                ds.createDimension(dimension, spatial_extent)
            time_var = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
            time_var[:] = np.asarray([[value.encode("ascii")[i:i + 1] for i in range(19)]
                                      for value in times], dtype="S1")
            for index, (name, dims) in enumerate(self.layouts.items()):
                dtype = "f8" if name == dtype_change else "f4"
                variable_dims = tuple(
                    "west_east" if name == dimension_change and axis == dims[-1] else axis
                    for axis in dims
                )
                var = ds.createVariable(name, dtype, ("Time", *variable_dims), fill_value=-9999.0)
                var.units = "changed" if name == units_change else ("K" if name == "T" else "Pa")
                var.stagger = "Y" if name == stagger_change else ("X" if name in ("U", "V", "W") else "")
                values = np.full((len(times), *(len(ds.dimensions[dim]) for dim in variable_dims)),
                                 index + 1, dtype=dtype)
                if name == mutate:
                    values[1, ...] += 1
                if name == fill:
                    values[0, ...] = -9999.0
                var[:] = values
        return {"path": path.name, "sha256": audit.frozen.sha256(path)}

    def _compare(self, temp: Path, **compact_options) -> dict:
        baseline = temp / "baseline"
        compact = temp / "compact"
        (baseline / "run").mkdir(parents=True, exist_ok=True)
        (compact / "run").mkdir(parents=True, exist_ok=True)
        base_row = self._history(baseline / "run" / ("wrfout_d01_" + self.timestamps[0]), include_second=True)
        compact_path = compact / "run" / ("wrfout_d01_" + self.timestamps[0])
        compact_row = self._history(compact_path, **compact_options)
        base_receipt = {"generated_files": [base_row]}
        compact_receipt = {"generated_files": [compact_row]}
        return audit.compare_closed_histories(baseline, base_receipt, compact,
                                              compact_receipt, "OFF")

    def test_compares_real_netcdf_fields_and_reports_missing_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._compare(Path(directory), include_second=False)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["compared_frames"], 1)
        self.assertEqual(result["missing_expected_timestamps"]["baseline"],
                         list(audit.HISTORY_TIMES[2:]))
        self.assertEqual(result["missing_expected_timestamps"]["compact"],
                         list(audit.HISTORY_TIMES[1:]))
        self.assertEqual(result["differences"], [])

    def test_rejects_changed_spatial_extent_but_allows_different_time_lengths(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._compare(Path(directory), spatial_extent=3)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("metadata", result["differences"][0])

    def test_rejects_changed_spatial_extent_between_files_in_one_arm(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            baseline, compact = temp / "baseline", temp / "compact"
            (baseline / "run").mkdir(parents=True)
            (compact / "run").mkdir(parents=True)
            base_rows = [
                self._history(baseline / "run" / ("wrfout_d01_" + audit.HISTORY_TIMES[index]),
                              spatial_extent=extent, time_indices=(index,))
                for index, extent in ((0, 2), (1, 3))
            ]
            compact_row = self._history(
                compact / "run" / ("wrfout_d01_" + audit.HISTORY_TIMES[0]),
                time_indices=(0, 1))
            result = audit.compare_closed_histories(
                baseline, {"generated_files": base_rows}, compact,
                {"generated_files": [compact_row]}, "OFF")
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("metadata changes between files", result["differences"][0])

    def test_detects_field_value_change_at_shared_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._compare(Path(directory), mutate="U")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(audit.HISTORY_TIMES[1] in item and "U" in item
                            for item in result["differences"]))

    def test_rejects_dtype_or_attribute_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._compare(Path(directory), dtype_change="T")
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("metadata", result["differences"][0])
        with tempfile.TemporaryDirectory() as directory:
            result = self._compare(Path(directory), units_change="P")
        self.assertEqual(result["status"], "FAIL")
        with tempfile.TemporaryDirectory() as directory:
            result = self._compare(Path(directory), stagger_change="U")
        self.assertEqual(result["status"], "FAIL")
        with tempfile.TemporaryDirectory() as directory:
            result = self._compare(Path(directory), dimension_change="U")
        self.assertEqual(result["status"], "FAIL")

    def test_finite_reader_rejects_declared_fill_before_compare(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._compare(Path(directory), fill="MU")
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("sentinel", result["differences"][0])


if __name__ == "__main__":
    unittest.main()
