#!/usr/bin/env python3
"""Focused parser checks for completed PR85 whole-tile state records."""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr85_joint_stage_trace as trace


BOUNDS = (1, 2, 1, 2, 1, 1, 1, 2, 1, 1, 1, 1)


def record(magic: bytes, label: str, kind: int, rk: int,
           fields: dict[str, np.ndarray], bounds: tuple[int, ...] = BOUNDS,
           timestep: int = 1) -> bytes:
    values = bytearray(magic)
    values.extend(label.encode("ascii").ljust(32, b" "))
    values.extend(struct.pack(">15i", kind, timestep, rk, *bounds))
    names = trace.STATE_FIELDS if kind == 1 else trace.PBL_FIELDS
    for name in names:
        nx = bounds[7] - bounds[6] + 1
        ny = bounds[9] - bounds[8] + 1
        nz = bounds[11] - bounds[10] + 1
        values.extend(np.asarray(fields[name], dtype=">f4").reshape(ny, nz, nx).tobytes())
    return bytes(values)


def state_fields() -> dict[str, np.ndarray]:
    fields = {name: np.zeros((1, 1, 2), dtype=np.float32) for name in trace.STATE_FIELDS}
    fields["DEN"][:] = 1.0
    fields["Q"][:] = 0.01
    fields["QC"][:] = 1.0e-8
    fields["NC"][:] = 1.0e6
    return fields


class JointStageTraceTests(unittest.TestCase):
    def test_reader_reports_fortran_field_order_as_jki(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shape.raw"
            path.write_bytes(record(trace.STATE_MAGIC, "PRE_RK", 1, 0, state_fields()))
            result = trace.read_records(path)["records"][0]
        self.assertEqual(result["shape_jki"], [1, 1, 2])
        self.assertEqual(result["fields"]["Q"].shape, (1, 1, 2))

    def test_graupel_cone_reports_exact_and_eight_ulp_residuals(self) -> None:
        fields = state_fields()
        fields["QG"][0, 0, :] = (99.99998, 99.9999)
        fields["BG"][:] = 1.0
        result = trace._pair_stats(fields, trace._load_policy())["graupel"]["feasible_cone"]
        self.assertEqual(result["exact_outside_bound_cells"], 2)
        self.assertEqual(result["outside_beyond_8_float32_ulp_cells"], 1)
        self.assertGreater(result["maximum_exact_lower_residual"], 0.0)
        self.assertGreater(result["eight_ulp_tolerance_at_lower_bound"], 0.0)

    def test_partial_pbl_tile_is_compared_by_intersection_and_fails_coverage(self) -> None:
        fields = state_fields()
        pbl_fields = {name: np.zeros((1, 1, 1), dtype=np.float32) for name in trace.PBL_FIELDS}
        pbl_bounds = (1, 2, 1, 2, 1, 1, 2, 2, 1, 1, 1, 1)
        data = b"".join((
            record(trace.STATE_MAGIC, "PRE_RK", 1, 0, fields),
            record(trace.PBL_MAGIC, "POST_PBL_TEND", 2, 0, pbl_fields, pbl_bounds),
            *(record(trace.STATE_MAGIC, stage, 1, rk, fields) for stage, rk in (
                ("RK_STAGE_END", 1), ("RK_STAGE_END", 2), ("RK_STAGE_END", 3),
                ("PRE_KDM6", 0), ("POST_KDM6", 0))),
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stages.raw"
            path.write_bytes(data)
            report = trace.summarize(path)
        coverage = report["strict_stage_coverage"]
        self.assertFalse(coverage["full_kind2_tendency_before_rk1"])
        self.assertEqual(coverage["status"], "INCOMPLETE")
        overlap = report["kind2_tendency_records"][0]["consumer_support_comparison"]
        self.assertEqual(overlap["intersection_cell_count"], 1)
        self.assertEqual(overlap["consumer_cell_count"], 2)

    def test_completed_stage_finds_first_pair_failure_and_requires_kdm_return(self) -> None:
        pre = state_fields()
        rk1 = state_fields()
        rk1["NC"][0, 0, 0] = 0.0
        pbl = {name: np.zeros((1, 1, 2), dtype=np.float32) for name in trace.PBL_FIELDS}
        pbl["QC_TEND"][0, 0, 0] = -2.0
        data = b"".join((
            record(trace.STATE_MAGIC, "PRE_RK", 1, 0, pre),
            record(trace.PBL_MAGIC, "POST_PBL_TEND", 2, 0, pbl),
            record(trace.STATE_MAGIC, "RK_STAGE_END", 1, 1, rk1),
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stages.raw"
            path.write_bytes(data)
            report = trace.summarize(path)
        self.assertEqual(report["earliest_observed_completed_state_violation"]["stage"], "RK_STAGE_END")
        pair = report["earliest_observed_completed_state_violation"]["pair_violations"]["cloud"]
        self.assertEqual(pair["positive_mass_zero_moment"], 1)
        self.assertEqual(report["kind2_tendency_records"][0]["stats"]["QC_TEND"]["negative"], 1)
        self.assertEqual(report["strict_stage_coverage"]["status"], "INCOMPLETE")
        self.assertFalse(report["strict_stage_coverage"]["firstNC_skip_satisfies_gate"])

    def test_complete_state_sequence_requires_pre_and_post_kdm_records(self) -> None:
        fields = state_fields()
        tendencies = {name: np.zeros((1, 1, 2), dtype=np.float32) for name in trace.PBL_FIELDS}
        data = b"".join((
            record(trace.STATE_MAGIC, "PRE_RK", 1, 0, fields),
            record(trace.PBL_MAGIC, "POST_PBL_TEND", 2, 0, tendencies),
            *(record(trace.STATE_MAGIC, stage, 1, rk, fields) for stage, rk in (
                ("RK_STAGE_END", 1), ("RK_STAGE_END", 2), ("RK_STAGE_END", 3),
                ("PRE_KDM6", 0), ("POST_KDM6", 0))),
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stages.raw"
            path.write_bytes(data)
            report = trace.summarize(path)
        self.assertEqual(report["schema"], "pr85_joint_moment_stage_summary_v3")
        self.assertEqual(report["strict_stage_coverage"]["status"], "PASS")
        self.assertEqual(report["strict_completed_state_admission"]["status"], "PASS")
        self.assertEqual(report["strict_density_contract"]["status"], "PASS")
        self.assertTrue(report["strict_stage_coverage"]["pre_kdm6_present"])
        self.assertTrue(report["strict_stage_coverage"]["post_kdm6_present"])
        self.assertIsNone(report["earliest_observed_completed_state_violation"])

        # Complete observer coverage is not itself an admission pass when a
        # completed native state violates a source invariant.
        bad_fields = state_fields()
        bad_fields["QS"][0, 0, 0] = -1.0e-8
        data = b"".join((
            record(trace.STATE_MAGIC, "PRE_RK", 1, 0, fields),
            record(trace.PBL_MAGIC, "POST_PBL_TEND", 2, 0, tendencies),
            record(trace.PBL_MAGIC, "PRE_GROUPED_PHYSICS_TEND", 2, 0, tendencies),
            record(trace.STATE_MAGIC, "RK_STAGE_END", 1, 1, bad_fields),
            *(record(trace.STATE_MAGIC, stage, 1, rk, fields) for stage, rk in (
                ("RK_STAGE_END", 2), ("RK_STAGE_END", 3),
                ("PRE_KDM6", 0), ("POST_KDM6", 0))),
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "complete-but-invalid.raw"
            path.write_bytes(data)
            report = trace.summarize(path)
        self.assertEqual(report["strict_stage_coverage"]["status"], "PASS")
        self.assertEqual(report["strict_completed_state_admission"]["status"], "FAIL")
        self.assertEqual(report["strict_completed_state_admission"][
            "earliest_observed_completed_state_violation"]["stage"], "RK_STAGE_END")

    def test_grouped_physics_tendency_keeps_its_scope_and_covers_pre_rk(self) -> None:
        fields = state_fields()
        pbl_fields = {name: np.zeros((1, 1, 2), dtype=np.float32) for name in trace.PBL_FIELDS}
        grouped_fields = {name: np.zeros((1, 1, 2), dtype=np.float32) for name in trace.PBL_FIELDS}
        data = b"".join((
            record(trace.STATE_MAGIC, "PRE_RK", 1, 0, fields),
            record(trace.PBL_MAGIC, "POST_PBL_TEND", 2, 0, pbl_fields),
            record(trace.PBL_MAGIC, "PRE_GROUPED_PHYSICS_TEND", 2, 0, grouped_fields),
            *(record(trace.STATE_MAGIC, stage, 1, rk, fields) for stage, rk in (
                ("RK_STAGE_END", 1), ("RK_STAGE_END", 2), ("RK_STAGE_END", 3),
                ("PRE_KDM6", 0), ("POST_KDM6", 0))),
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grouped-tendencies.raw"
            path.write_bytes(data)
            report = trace.summarize(path)
        tendency_records = report["kind2_tendency_records"]
        self.assertEqual([item["stage"] for item in tendency_records],
                         ["POST_PBL_TEND", "PRE_GROUPED_PHYSICS_TEND"])
        self.assertEqual(tendency_records[0]["scope"],
                         "selected Shinhong common-mixing tendencies immediately after return and before FogDES")
        self.assertEqual(tendency_records[0]["unit_basis"], "native PBL tendency-array units")
        self.assertEqual(tendency_records[1]["unit_basis"], "native mu-coordinate tendency per second")
        self.assertTrue(report["strict_stage_coverage"]["full_kind2_tendency_before_rk1"])
        self.assertEqual(report["strict_stage_coverage"]["status"], "PASS")

        # The tendency observer runs in the PBL call, which may precede the
        # snapshot boundary while both still precede RK1. It is not a state.
        pbl_fields_first = {name: np.zeros((1, 1, 2), dtype=np.float32) for name in trace.PBL_FIELDS}
        data = b"".join((
            record(trace.PBL_MAGIC, "POST_PBL_TEND", 2, 0, pbl_fields_first),
            record(trace.STATE_MAGIC, "PRE_RK", 1, 0, fields),
            *(record(trace.STATE_MAGIC, stage, 1, rk, fields) for stage, rk in (
                ("RK_STAGE_END", 1), ("RK_STAGE_END", 2), ("RK_STAGE_END", 3),
                ("PRE_KDM6", 0), ("POST_KDM6", 0))),
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pbl-first.raw"
            path.write_bytes(data)
            report = trace.summarize(path)
        self.assertEqual(report["strict_stage_coverage"]["status"], "PASS")

    def test_rk1_process_and_diffusion_records_keep_distinct_scopes(self) -> None:
        fields = state_fields()
        tendencies = {name: np.zeros((1, 1, 2), dtype=np.float32) for name in trace.PBL_FIELDS}
        data = b"".join((
            record(trace.STATE_MAGIC, "PRE_RK", 1, 0, fields),
            record(trace.PBL_MAGIC, "CUMULUS_PROCESS_TEND", 2, 1, tendencies),
            record(trace.PBL_MAGIC, "PRE_HORIZONTAL_DIFFUSION", 2, 1, tendencies),
            record(trace.PBL_MAGIC, "POST_HORIZONTAL_DIFFUSION", 2, 1, tendencies),
            *(record(trace.STATE_MAGIC, stage, 1, rk, fields) for stage, rk in (
                ("RK_STAGE_END", 1), ("RK_STAGE_END", 2), ("RK_STAGE_END", 3),
                ("PRE_KDM6", 0), ("POST_KDM6", 0))),
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rk1-attribution.raw"
            path.write_bytes(data)
            report = trace.summarize(path)
        labels = [item["stage"] for item in report["kind2_tendency_records"]]
        self.assertEqual(labels, ["CUMULUS_PROCESS_TEND", "PRE_HORIZONTAL_DIFFUSION",
                                  "POST_HORIZONTAL_DIFFUSION"])
        self.assertEqual(report["kind2_tendency_records"][0]["unit_basis"],
                         trace.TENDENCY_SCOPES["CUMULUS_PROCESS_TEND"]["unit_basis"])
        # RK1 diagnostics do not masquerade as the pre-update source capture.
        self.assertFalse(report["strict_stage_coverage"]["full_kind2_tendency_before_rk1"])
        self.assertEqual(report["strict_stage_coverage"]["status"], "INCOMPLETE")

    def test_mixed_timestep_and_wrong_rk_order_fail_strict_coverage(self) -> None:
        fields = state_fields()
        tendencies = {name: np.zeros((1, 1, 2), dtype=np.float32) for name in trace.PBL_FIELDS}
        stages = [("RK_STAGE_END", 1), ("RK_STAGE_END", 2), ("RK_STAGE_END", 3),
                  ("PRE_KDM6", 0), ("POST_KDM6", 0)]
        data = b"".join((
            record(trace.STATE_MAGIC, "PRE_RK", 1, 0, fields),
            record(trace.PBL_MAGIC, "POST_PBL_TEND", 2, 0, tendencies),
            *(record(trace.STATE_MAGIC, stage, 1, rk, fields,
                     timestep=2 if stage == "PRE_KDM6" else 1)
              for stage, rk in stages),
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mixed.raw"
            path.write_bytes(data)
            report = trace.summarize(path)
        self.assertFalse(report["strict_stage_coverage"]["single_timestep"])
        self.assertFalse(report["strict_stage_coverage"]["status"] == "PASS")

        data = b"".join((
            record(trace.STATE_MAGIC, "PRE_RK", 1, 0, fields),
            record(trace.PBL_MAGIC, "POST_PBL_TEND", 2, 0, tendencies),
            *(record(trace.STATE_MAGIC, stage, 1, rk, fields)
              for stage, rk in (("RK_STAGE_END", 1), ("RK_STAGE_END", 3),
                                ("RK_STAGE_END", 2), ("PRE_KDM6", 0),
                                ("POST_KDM6", 0))),
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong-rk.raw"
            path.write_bytes(data)
            report = trace.summarize(path)
        self.assertFalse(report["strict_stage_coverage"]["rk1_rk2_rk3_complete"])
        self.assertEqual(report["strict_stage_coverage"]["status"], "INCOMPLETE")

    def test_rejects_incomplete_record_payload(self) -> None:
        data = record(trace.STATE_MAGIC, "PRE_RK", 1, 0, state_fields())[:-1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stages.raw"
            path.write_bytes(data)
            with self.assertRaisesRegex(trace.TraceError, "truncated PRE_RK BG"):
                trace.read_records(path)

    def test_v2_density_uses_authoritative_dry_density_without_vapor_division(self) -> None:
        fields = state_fields()
        fields["DEN"][:] = 0.8
        fields["Q"][:] = 0.25
        dry_v2 = trace._dry_density(fields, "AUTHORITATIVE_DRY_FROM_AL_ALB")
        historical_v1 = trace._dry_density(fields, "UNVERIFIED_LEGACY_DECLARATION")
        np.testing.assert_array_equal(dry_v2, fields["DEN"])
        np.testing.assert_allclose(historical_v1, 0.64, rtol=0, atol=1e-7)

    def test_legacy_density_records_remain_readable_but_cannot_pass_strict_gate(self) -> None:
        fields = state_fields()
        tendencies = {name: np.zeros((1, 1, 2), dtype=np.float32) for name in trace.PBL_FIELDS}
        data = b"".join((
            record(trace.LEGACY_STATE_MAGIC, "PRE_RK", 1, 0, fields),
            record(trace.PBL_MAGIC, "POST_PBL_TEND", 2, 0, tendencies),
            record(trace.PBL_MAGIC, "PRE_GROUPED_PHYSICS_TEND", 2, 0, tendencies),
            *(record(trace.LEGACY_STATE_MAGIC, stage, 1, rk, fields) for stage, rk in (
                ("RK_STAGE_END", 1), ("RK_STAGE_END", 2), ("RK_STAGE_END", 3),
                ("PRE_KDM6", 0), ("POST_KDM6", 0))),
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy-stages.raw"
            path.write_bytes(data)
            report = trace.summarize(path)
        self.assertEqual(report["strict_stage_coverage"]["status"], "PASS")
        self.assertEqual(report["strict_density_contract"]["status"],
                         "UNVERIFIED_LEGACY_DECLARATION")
        self.assertEqual(report["strict_completed_state_admission"]["status"], "INCOMPLETE")
        self.assertFalse(report["strict_completed_state_admission"]["density_contract_verified"])

    def test_tendency_only_control_is_reported_as_incomplete(self) -> None:
        fields = {name: np.zeros((1, 1, 2), dtype=np.float32) for name in trace.PBL_FIELDS}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tendency-only.raw"
            path.write_bytes(record(trace.PBL_MAGIC, "POST_PBL_TEND", 2, 0, fields))
            report = trace.summarize(path)
        self.assertEqual(report["strict_stage_coverage"]["status"], "INCOMPLETE")
        self.assertIsNone(report["kind2_tendency_records"][0]["consumer_support_comparison"])


if __name__ == "__main__":
    unittest.main()
