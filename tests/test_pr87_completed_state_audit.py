from __future__ import annotations

import gzip
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr87_completed_state_audit as audit_module
from pr85_joint_stage_trace import STATE_FIELDS


def state_record_values(stage: str, timestep: int, rkstep: int,
                        values: dict[str, float] | None = None) -> bytes:
    header = struct.pack(
        ">15i", 1, timestep, rkstep,
        1, 1, 1, 1, 1, 1,
        1, 1, 1, 1, 1, 1,
    )
    fields = []
    record_values = {"DEN": 1.0}
    record_values.update(values or {})
    for name in STATE_FIELDS:
        encoded = np.array([record_values.get(name, 0.0)], dtype=">f4")
        fields.append(encoded.tobytes())
    return b"PR85QND2" + stage.encode("ascii").ljust(32) + header + b"".join(fields)


def state_record(stage: str, timestep: int, rkstep: int, negative_q: bool = False) -> bytes:
    return state_record_values(stage, timestep, rkstep, {"Q": -1.0} if negative_q else None)


def timestep_records(timestep: int, second_rkstep: int = 2) -> bytes:
    stages = (("PRE_RK", 0), ("RK_STAGE_END", 1), ("RK_STAGE_END", second_rkstep),
              ("RK_STAGE_END", 3), ("PRE_KDM6", 0), ("POST_KDM6", 0))
    return b"".join(state_record(stage, timestep, rkstep) for stage, rkstep in stages)


class CompletedStateAuditTests(unittest.TestCase):
    def test_passes_repeated_complete_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "two_steps.raw.gz"
            with gzip.open(path, "wb") as stream:
                stream.write(timestep_records(1))
                stream.write(timestep_records(2))
            report = audit_module.audit(path)

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["trace_timesteps"], [1, 2])
        self.assertTrue(report["timestep_ids_contiguous_from_one"])
        self.assertEqual(report["completed_post_kdm6_timestep_count"], 2)
        self.assertEqual([row["state_record_count"] for row in report["timestep_audits"]], [6, 6])

    def test_audits_each_completed_timestep_and_marks_partial_tail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stages.raw.gz"
            with gzip.open(path, "wb") as stream:
                stream.write(timestep_records(1))
                stream.write(state_record("PRE_RK", 2, 0, negative_q=True))
                stream.write(state_record("RK_STAGE_END", 2, 1))
            report = audit_module.audit(path)

        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["trace_timestep_count"], 2)
        self.assertEqual(report["completed_post_kdm6_timestep_count"], 1)
        self.assertEqual(report["state_record_count"], 8)
        first, partial = report["timestep_audits"]
        self.assertEqual(first["status"], "PASS")
        self.assertEqual(first["state_stage_sequence"], list(audit_module.STATE_SEQUENCE))
        self.assertTrue(first["density_contract_verified"])
        self.assertEqual(partial["status"], "INCOMPLETE")
        self.assertEqual(partial["state_record_count"], 2)
        self.assertEqual(partial["first_recorded_state_violation"]["stage"], "PRE_RK")
        self.assertEqual(partial["first_recorded_state_violation"]["fields"]["Q"]["negative"], 1)
        self.assertTrue(all(not stage["violations"][key]
                            for stage in first["completed_state_summaries"]
                            for key in ("fields", "pairs", "number_conversion")))

    def test_rejects_malformed_rkstep_sequence_even_when_stage_names_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "malformed.raw"
            path.write_bytes(timestep_records(1, second_rkstep=3))
            report = audit_module.audit(path)

        timestep = report["timestep_audits"][0]
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertTrue(timestep["required_state_sequence_complete"])
        self.assertFalse(timestep["required_rkstep_sequence_complete"])
        self.assertTrue(timestep["observed_post_kdm6"])
        self.assertFalse(timestep["completed_post_kdm6"])
        self.assertEqual(report["completed_post_kdm6_timestep_count"], 0)

    def test_requires_contiguous_timestep_ids_from_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gap.raw"
            path.write_bytes(timestep_records(1) + timestep_records(3))
            report = audit_module.audit(path)

        self.assertEqual(report["trace_timesteps"], [1, 3])
        self.assertFalse(report["timestep_ids_contiguous_from_one"])
        self.assertEqual(report["status"], "INCOMPLETE")

    def test_strict_source_bounds_reject_values_inside_legacy_ulp_band(self) -> None:
        lower_cloud = np.float32(
            np.float64(np.float32(523.59881591796875)) /
            np.float64(np.float32(500000.0)) ** np.float64(3.0))
        cloud_q = lower_cloud
        for _ in range(4):
            cloud_q = np.nextafter(cloud_q, np.float32(0.0), dtype=np.float32)
        lower_rain = np.float32(
            np.float64(np.float32(12566.37109375)) /
            np.float64(np.float32(35000.0)) ** np.float64(3.0))
        rain_q = lower_rain
        for _ in range(4):
            rain_q = np.nextafter(rain_q, np.float32(0.0), dtype=np.float32)
        graupel_q = np.float32(100.0)
        for _ in range(4):
            graupel_q = np.nextafter(graupel_q, np.float32(0.0), dtype=np.float32)

        fields = {name: np.array([0.0], dtype=np.float32) for name in STATE_FIELDS}
        fields["DEN"][:] = 1.0
        fields["QC"][:] = cloud_q
        fields["NC"][:] = 1.0
        fields["QR"][:] = rain_q
        fields["NR"][:] = 1.0
        fields["QG"][:] = graupel_q
        fields["BG"][:] = 1.0

        old_pairs = audit_module.pr85._pair_stats(fields, audit_module.pr85._load_policy())
        self.assertEqual(old_pairs["cloud"]["feasible_cone"]["outside_beyond_8_float32_ulp_cells"], 0)
        self.assertEqual(old_pairs["rain"]["feasible_cone"]["outside_beyond_8_float32_ulp_cells"], 0)
        self.assertEqual(old_pairs["graupel"]["feasible_cone"]["outside_beyond_8_float32_ulp_cells"], 0)

        checks = audit_module._strict_source_checks(fields)
        self.assertEqual(checks["cloud"]["counts"]["specific_ratio_outside_exact_bounds"], 1)
        self.assertEqual(checks["rain"]["counts"]["specific_ratio_outside_exact_bounds"], 1)
        self.assertEqual(checks["graupel_exact_stored"]["counts"]["ratio_outside_exact_bounds"], 1)

    def test_reports_real32_volume_rounding_crossing_separately(self) -> None:
        fields = {name: np.array([0.0], dtype=np.float32) for name in STATE_FIELDS}
        fields["DEN"][:] = np.float32(1.7689435)
        fields["QC"][:] = np.float32(3.1689594e-19)
        fields["NC"][:] = np.float32(7.5653326e-05)
        checks = audit_module._strict_source_checks(fields)["cloud"]["counts"]
        self.assertEqual(checks["specific_ratio_outside_exact_bounds"], 0)
        self.assertEqual(checks["real64_volume_ratio_outside_exact_bounds"], 0)
        self.assertEqual(checks["real32_density_times_number_volume_ratio_outside_exact_bounds"], 1)

    def test_strict_mode_reports_predictor_qv_but_gates_completed_endpoints(self) -> None:
        # PRE_RK and RK1 predictors can carry transient negative QV; completed
        # RK3 and KDM6 endpoints still have to pass.
        stages = [("PRE_RK", 0), ("RK_STAGE_END", 1), ("RK_STAGE_END", 2),
                  ("RK_STAGE_END", 3), ("PRE_KDM6", 0), ("POST_KDM6", 0)]
        parts = []
        for stage, rkstep in stages:
            values = {"Q": -1.0} if (stage, rkstep) in (("PRE_RK", 0), ("RK_STAGE_END", 1)) else None
            parts.append(state_record_values(stage, 1, rkstep, values))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictor.raw"
            path.write_bytes(b"".join(parts))
            report = audit_module.audit(path, strict_source_coefficients=True)
        timestep = report["timestep_audits"][0]
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(timestep["intermediate_predictor_qv_negative_records"], [
            {"stage": "PRE_RK", "rkstep": 0, "negative_cells": 1},
            {"stage": "RK_STAGE_END", "rkstep": 1, "negative_cells": 1}])
        self.assertFalse(timestep["completed_state_summaries"][0]["strict_endpoint_gate_applies"])
        self.assertEqual(timestep["completed_state_summaries"][1]["violations"]["fields"]["Q"]["negative"], 1)
        self.assertTrue(timestep["completed_state_summaries"][1]["strict_endpoint_gate_applies"] is False)

    def test_strict_mode_fails_an_exact_source_violation_at_completed_endpoint(self) -> None:
        lower_cloud = np.float32(
            np.float64(np.float32(523.59881591796875)) /
            np.float64(np.float32(500000.0)) ** np.float64(3.0))
        cloud_q = lower_cloud
        for _ in range(4):
            cloud_q = np.nextafter(cloud_q, np.float32(0.0), dtype=np.float32)
        parts = []
        stages = (("PRE_RK", 0), ("RK_STAGE_END", 1), ("RK_STAGE_END", 2),
                  ("RK_STAGE_END", 3), ("PRE_KDM6", 0), ("POST_KDM6", 0))
        for stage, rkstep in stages:
            values = {"QC": float(cloud_q), "NC": 1.0} if stage == "POST_KDM6" else None
            parts.append(state_record_values(stage, 1, rkstep, values))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strict-endpoint.raw"
            path.write_bytes(b"".join(parts))
            report = audit_module.audit(path, strict_source_coefficients=True)
        self.assertEqual(report["status"], "FAIL")
        timestep = report["timestep_audits"][0]
        self.assertEqual(timestep["first_recorded_state_violation"]["stage"], "POST_KDM6")
        self.assertEqual(
            timestep["first_recorded_state_violation"]["strict_source_coefficients"]["cloud"][
                "specific_ratio_outside_exact_bounds"], 1)


if __name__ == "__main__":
    unittest.main()
