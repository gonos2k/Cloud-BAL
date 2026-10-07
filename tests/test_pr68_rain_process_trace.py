import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr68_rain_process_trace import (
    COLD_RATE_FIELDS,
    REAL_FIELDS,
    TraceError,
    WARM_RATE_FIELDS,
    _check_file_hash,
    audit_capture,
    failure_coordinates,
    read_capture,
    _run_executable_hash,
)


COLD_EVENTS = (0, 1, 2, 3, 4, 5, 6, 7, 12, 13, 14, 15)
COORDS = [[index + 1, 7, 13] for index in range(25)]


def _capture_lines(coords=COORDS, events=COLD_EVENTS):
    lines = []
    for i, j, k in coords:
        for event in events:
            fields = {name: 0.0 for name in REAL_FIELDS}
            fields.update(qr=1.0e-5, nr=0.25, temperature_k=270.0,
                          qcrmin=1.0e-8, nrmin=0.5, dtcld=1.0)
            if event == 4:
                fields.update(ngacr=1.0, limiter_value=0.5, limiter_source=1.0,
                              qr_trial=1.0e-5,
                              nr_trial=-0.75)
            elif event == 5:
                fields.update(ngacr=0.5, limiter_value=0.5, limiter_source=1.0,
                              qr_trial=1.0e-5,
                              nr_trial=-0.25)
            elif event >= 6:
                fields.update(nr=0.0, qr_trial=1.0e-5, nr_trial=-0.25)
            ints = (event, i, j, k, 1, 2, 0)
            lines.append("PR68R001 " + " ".join(map(str, ints)) + " " +
                         " ".join(f"{fields[name]:.16E}" for name in REAL_FIELDS))
    return lines


def _warm_capture_lines():
    output = []
    event_map = {4: 8, 5: 9, 6: 10, 7: 11}
    for line in _capture_lines():
        parts = line.split()
        event = int(parts[1])
        fields = dict(zip(REAL_FIELDS, map(float, parts[8:]), strict=True))
        parts[1] = str(event_map.get(event, event))
        fields["temperature_k"] = 280.0
        fields["ngacr"] = 0.0
        if event in (4, 5):
            fields.update(nrcol=2.0 if event == 4 else 0.5,
                          limiter_value=0.5, limiter_source=2.0,
                          qr_trial=1.0e-5,
                          nr_trial=-1.75 if event == 4 else -0.25)
        rebuilt = parts[:8] + [f"{fields[name]:.16E}" for name in REAL_FIELDS]
        output.append(" ".join(rebuilt))
    return output


def _write_fixture(root: Path, lines):
    targets = root / "targets.json"
    targets.write_text(json.dumps({
        "schema": "pr68_kdm6_failure_targets_v1", "count": 25,
        "coordinates_ijk": COORDS,
    }))
    capture = root / "pr68_kdm6_rain.raw"
    capture.write_text("\n".join(lines) + "\n")
    output_names = [capture.name, "kdm6_first_call_pre.raw", "kdm6_first_call_post.raw"]
    (root / output_names[1]).write_bytes(b"pre state")
    (root / output_names[2]).write_bytes(b"post state")
    outputs = [{
        "path": name,
        "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
        "nlink": 1,
    } for name in output_names]
    summaries = []
    for name, entries, exe in (("observer.json", outputs, "6" * 64),
                               ("control.json", outputs[1:], "5" * 64)):
        path = root / name
        path.write_text(json.dumps({
            "run_root": str(root), "returncode": 0, "input_integrity": "PASS",
            "output_isolation": "PASS", "executable_sha256": exe, "outputs": entries,
        }))
        summaries.append(path)
    return capture, targets, *summaries


class RainTraceTests(unittest.TestCase):
    def test_failure_coordinates_use_j_k_i_array_order_and_global_starts(self):
        mask = np.zeros((2, 3, 4), dtype=bool)
        mask[1, 2, 3] = True
        bounds = {"jts": 7, "jte": 8, "kts": 11, "kte": 13, "its": 19, "ite": 22}
        self.assertEqual(failure_coordinates(mask, bounds), [[22, 8, 13]])

    def test_capture_rejects_nonfinite_and_selects_only_active_branch_rates(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.raw"
            fields = [0.0] * len(REAL_FIELDS)
            fields[9] = 1.0
            path.write_text("PR68R001 4 22 8 13 1 2 0 " + " ".join(map(str, fields)) + "\n")
            record = read_capture(path)[0]
            self.assertEqual(record["supported_rate_fields"], list(COLD_RATE_FIELDS))
            path.write_text("PR68R001 8 22 8 13 1 2 0 " + " ".join(map(str, fields)) + "\n")
            self.assertEqual(read_capture(path)[0]["supported_rate_fields"], list(WARM_RATE_FIELDS))
            fields[0] = float("nan")
            path.write_text("PR68R001 4 22 8 13 1 2 0 " + " ".join(map(str, fields)) + "\n")
            with self.assertRaises(TraceError):
                read_capture(path)

    def test_audit_reconstructs_source_trials_and_checkpoints(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capture, targets, observer, control = _write_fixture(root, _capture_lines())
            report = audit_capture(
                capture, targets, observer, control,
                selected_source_sha256="1" * 64, observer_source_sha256="2" * 64,
                control_object_sha256="3" * 64, observer_object_sha256="4" * 64,
                control_executable_sha256="5" * 64, observer_executable_sha256="6" * 64,
            )
            self.assertEqual(report["target_count"], 25)
            self.assertEqual(report["branch_counts"], {"cold": 25, "warm": 0})
            self.assertEqual(report["first_bad_event_counts"]["after_cold_process_update"], 25)
            self.assertEqual(report["accepted_number_trial_vs_reserve"]["negative_count"], 25)
            self.assertIn("terminal_kdm62d_return", report["cells"][0]["process_limiter"]["later_checkpoints"])

    def test_audit_reconstructs_warm_branch_from_captured_temperature(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capture, targets, observer, control = _write_fixture(root, _warm_capture_lines())
            report = audit_capture(
                capture, targets, observer, control,
                selected_source_sha256="1" * 64, observer_source_sha256="2" * 64,
                control_object_sha256="3" * 64, observer_object_sha256="4" * 64,
                control_executable_sha256="5" * 64, observer_executable_sha256="6" * 64,
            )
            self.assertEqual(report["branch_counts"], {"cold": 0, "warm": 25})
            self.assertEqual(report["first_bad_event_counts"]["after_warm_process_update"], 25)
            self.assertEqual(report["accepted_number_trial_vs_reserve"]["below_nrmin_count"], 25)

    def test_audit_rejects_wrong_branch_label_missing_end_and_out_of_manifest_cell(self):
        for mutation in ("warm_label", "temperature_branch", "bad_limiter_source",
                         "missing_terminal", "outside_target"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                lines = _capture_lines()
                rows = [line.split() for line in lines]
                if mutation == "warm_label":
                    for row in rows:
                        if row[0] == "PR68R001" and row[1] == "4":
                            row[1] = "8"
                            break
                elif mutation == "temperature_branch":
                    for row in rows:
                        if row[1] == "4" and row[2] == "1":
                            row[8 + REAL_FIELDS.index("temperature_k")] = "2.8000000000000000E+02"
                            break
                elif mutation == "bad_limiter_source":
                    for row in rows:
                        if row[1] == "4" and row[2] == "1":
                            row[8 + REAL_FIELDS.index("limiter_source")] = "2.0000000000000000E+00"
                            break
                elif mutation == "missing_terminal":
                    rows = [row for row in rows if not (row[1] == "15" and row[2] == "1")]
                else:
                    for row in rows:
                        if row[1] == "0" and row[2] == "1":
                            row[2] = "99"
                            break
                capture, targets, observer, control = _write_fixture(
                    root, [" ".join(row) for row in rows])
                with self.assertRaises(TraceError):
                    audit_capture(
                        capture, targets, observer, control,
                        selected_source_sha256="1" * 64, observer_source_sha256="2" * 64,
                        control_object_sha256="3" * 64, observer_object_sha256="4" * 64,
                        control_executable_sha256="5" * 64, observer_executable_sha256="6" * 64,
                    )

    def test_hash_binding_rejects_wrong_artifact_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.f90"
            path.write_text("source")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            _check_file_hash(path, digest, "source")
            with self.assertRaises(TraceError):
                _check_file_hash(path, "0" * 64, "source")

    def test_executable_identity_can_come_from_run_input_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "wrf.exe"
            executable.write_bytes(b"binary")
            digest = hashlib.sha256(executable.read_bytes()).hexdigest()
            summary = {"run_root": str(root), "inputs": [{
                "path": str(executable), "sha256_before": digest, "sha256_after": digest,
            }]}
            self.assertEqual(_run_executable_hash(summary, root / "summary.json"), digest)
    def test_executable_identity_rehashes_nested_build_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "wrf.exe"
            executable.write_bytes(b"native executable")
            digest = hashlib.sha256(executable.read_bytes()).hexdigest()
            summary = {"executable": {
                "source": str(executable), "sha256_before": digest,
                "sha256_after": digest, "nlink": 1,
            }}
            self.assertEqual(_run_executable_hash(summary, root / "summary.json"), digest)

    def test_audit_rehashes_both_matched_native_outputs_on_disk(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capture, targets, observer, control = _write_fixture(root, _capture_lines())
            (root / "kdm6_first_call_pre.raw").write_bytes(b"altered after receipt")
            with self.assertRaisesRegex(TraceError, "not uniquely bound"):
                audit_capture(
                    capture, targets, observer, control,
                    selected_source_sha256="1" * 64, observer_source_sha256="2" * 64,
                    control_object_sha256="3" * 64, observer_object_sha256="4" * 64,
                    control_executable_sha256="5" * 64, observer_executable_sha256="6" * 64,
                )


if __name__ == "__main__":
    unittest.main()
