from __future__ import annotations

import sys
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr67_kdm6_process_budget import CaptureError, _verify_receipt
from pr68_carrier_budget_replay import (ReplayError, decompose_carriers,
                                        validate_receipt_inputs, validate_runtime_provenance,
                                        validate_same_call)


class CarrierBudgetReplayTests(unittest.TestCase):
    def test_reconciles_cell_carrier_terms_and_global_reduction(self) -> None:
        result = decompose_carriers(
            hybrid_global_delta=-5.0, native_global_delta=-5.1,
            hybrid_cell_delta=-4.9, native_cell_delta=-5.0,
            precipitation_kg=5.05, reported_residual_kg=0.05,
        )
        self.assertAlmostEqual(result["native_cell_residual_kg"], 0.05)
        self.assertAlmostEqual(result["carrier_choice_term_kg"], 0.1)
        self.assertAlmostEqual(result["hybrid_global_reduction_correction_kg"], -0.1)
        self.assertTrue(result["reconciliation_within_bound"])
        self.assertLessEqual(abs(result["reconciliation_error_kg"]),
                             result["reconciliation_roundoff_bound_kg"])

    def test_rejects_nonfinite_or_unreconciled_operands(self) -> None:
        with self.assertRaisesRegex(ReplayError, "finite"):
            decompose_carriers(np.nan, 0.0, 0.0, 0.0, 0.0, 0.0)
        with self.assertRaisesRegex(ReplayError, "roundoff bound"):
            decompose_carriers(0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        with self.assertRaisesRegex(ReplayError, "overflowed"):
            decompose_carriers(1.0e308, 0.0, 0.0, 0.0, 0.0, 1.0e308)

    def test_rejects_mismatched_time_and_changed_native_carrier(self) -> None:
        fields = {"DEN": np.ones((1, 1, 2), dtype=np.float32),
                  "DELZ": np.ones((1, 1, 2), dtype=np.float32)}
        pre = {"stage": 1, "itimestep": 1, "bounds": {"kts": 1}, "params": {},
               "fields": fields}
        post = {"stage": 2, "itimestep": 2, "bounds": {"kts": 1}, "params": {},
                "fields": fields}
        with self.assertRaisesRegex(ReplayError, "same supported call"):
            validate_same_call(pre, post, np.ones((1, 1, 2)), np.ones((1, 1, 2)))
        post["itimestep"] = 1
        post["bounds"] = {"kts": 2}
        with self.assertRaisesRegex(ReplayError, "same supported call"):
            validate_same_call(pre, post, np.ones((1, 1, 2)), np.ones((1, 1, 2)))
        post["bounds"] = pre["bounds"]
        with self.assertRaisesRegex(ReplayError, "differs from the native carrier"):
            validate_same_call(pre, post, np.full((1, 1, 2), 2.0), np.ones((1, 1, 2)))

    def test_runtime_executable_receipt_binding_rejects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "wrf.exe"
            executable.write_bytes(b"captured executable")
            source = root / "module_mp_kdm6.F"
            source.write_bytes(b"retained generated source")
            object_path = root / "module_mp_kdm6.o"
            object_path.write_bytes(b"selected combined object")
            manifest_path = root / "runtime_reference_manifest.json"
            manifest_path.write_text(json.dumps({
                "source_observer_sha256": "a" * 64,
                "observer_object_sha256": "b" * 64,
                "observer_executable_sha256": "c" * 64,
            }), encoding="utf-8")
            executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
            receipt_path = root / "run-isolation.json"
            receipt_path.write_text(json.dumps({
                "run_root": str(root), "returncode": 0, "input_integrity": "PASS",
                "output_isolation": "PASS", "inputs": [{"path": str(executable),
                    "sha256_before": executable_hash, "sha256_after": executable_hash}],
            }), encoding="utf-8")
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            object_hash = hashlib.sha256(object_path.read_bytes()).hexdigest()
            build_path = root / "build_provenance.json"
            build_path.write_text(json.dumps({"selected_artifacts": {
                "generated_combined_research_source": {"sha256": source_hash},
                "combined_kdm_object": {"sha256": object_hash, "path": str(object_path)}},
                "runs": {"combined": {"executable": {"sha256": executable_hash}}}}), encoding="utf-8")
            build_hash = hashlib.sha256(build_path.read_bytes()).hexdigest()
            evidence_path = root / "manifest.json"
            evidence_path.write_text(json.dumps({"build_provenance_file": build_path.name,
                "build_provenance_sha256": build_hash, "research_objects": {
                    "combined_generated_source_sha256": source_hash,
                    "combined_object_sha256": object_hash,
                    "combined_executable_sha256": executable_hash}}), encoding="utf-8")
            provenance = validate_runtime_provenance(receipt_path, manifest_path, source, evidence_path)
            self.assertEqual(provenance["selected_combined_source_object_executable"]["binding"],
                             "MATCHES_IMMUTABLE_PR67_COMBINED_EVIDENCE")
            self.assertFalse(provenance["reference_manifest_executable_matches_receipt"])
            executable.write_bytes(b"mutated executable")
            with self.assertRaisesRegex(ReplayError, "does not match"):
                validate_runtime_provenance(receipt_path, manifest_path, source, evidence_path)

    def test_selected_control_variant_cannot_bind_combined_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "wrf.exe"
            executable.write_bytes(b"combined executable")
            source = root / "combined.f90"
            source.write_bytes(b"combined generated source")
            obj = root / "combined.o"
            obj.write_bytes(b"combined selected object")
            h = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({"run_root": str(root), "returncode": 0,
                "input_integrity": "PASS", "output_isolation": "PASS",
                "inputs": [{"path": str(executable),
                "sha256_before": h(executable), "sha256_after": h(executable)}]}), encoding="utf-8")
            old_manifest = root / "runtime.json"
            old_manifest.write_text(json.dumps({"source_observer_sha256": "a" * 64,
                "observer_object_sha256": "b" * 64, "observer_executable_sha256": "c" * 64}),
                encoding="utf-8")
            build = root / "build.json"
            build.write_text(json.dumps({"selected_artifacts": {
                "generated_combined_research_source": {"sha256": h(source)},
                "combined_kdm_object": {"sha256": h(obj), "path": str(obj)}},
                "runs": {"combined": {"executable": {"sha256": h(executable)}}}}),
                encoding="utf-8")
            evidence = root / "manifest.json"
            evidence.write_text(json.dumps({"build_provenance_file": build.name,
                "build_provenance_sha256": h(build), "research_objects": {
                    "combined_generated_source_sha256": "d" * 64,
                    "combined_object_sha256": h(obj),
                    "combined_executable_sha256": h(executable)}}), encoding="utf-8")
            with self.assertRaisesRegex(ReplayError, "does not match evidence"):
                validate_runtime_provenance(receipt, old_manifest, source, evidence)

    def test_mutated_capture_fails_its_isolation_hash_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture_paths = [root / name for name in ("process.raw", "geometry.raw", "pre.raw", "post.raw")]
            for path in capture_paths:
                path.write_bytes(b"immutable capture")
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps({
                "returncode": 0, "input_integrity": "PASS", "output_isolation": "PASS",
                "run_root": str(root),
                "outputs": [{"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "nlink": 1} for path in capture_paths],
            }), encoding="utf-8")
            _verify_receipt(tuple(capture_paths), receipt_path)
            capture_paths[0].write_bytes(b"mutated capture")
            with self.assertRaisesRegex(CaptureError, "not hash-bound"):
                _verify_receipt(tuple(capture_paths), receipt_path)

    def test_pass_status_cannot_hide_changed_declared_input_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            declared = root / "input.dat"
            declared.write_bytes(b"input bytes")
            original = hashlib.sha256(declared.read_bytes()).hexdigest()
            receipt = {"returncode": 0, "input_integrity": "PASS", "output_isolation": "PASS",
                       "inputs": [{"path": str(declared), "sha256_before": original,
                                   "sha256_after": "0" * 64}]}
            with self.assertRaisesRegex(ReplayError, "malformed or changed"):
                validate_receipt_inputs(receipt, root)


if __name__ == "__main__":
    unittest.main()
