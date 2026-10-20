from __future__ import annotations

import sys
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr92_source_store_fixture as fixture
import pr92_bulk_volume_store as bulk_store


class SourceStoreFixtureTests(unittest.TestCase):
    def test_retry_probe_uses_the_committed_storage_policy_with_local_outputs(self) -> None:
        source = bulk_store.transform_module(fixture.D1_SOURCE.read_text(),
                                             (ROOT / "src/common/cloud_bal_joint_transport.f90").read_text())
        trial = fixture._extract(source, "try_graupel_mixture_trial")
        probe = fixture._extract(source, "probe_failed_graupel_pair")
        for body in (trial, probe):
            self.assertIn("allow_bulk_absence=.TRUE.", body)
        self.assertIn("bulk_absences=probe_bulk_absences", probe)
        self.assertIn("bulk_delta=probe_bulk_delta", probe)
        self.assertNotIn("bulk_absences=bulk_volume_absences", probe)
        self.assertNotIn("bulk_delta=bulk_volume_delta", probe)
        self.assertIn("IF (valid) failed_pairs(4)=.FALSE.", probe)

    def test_extracts_helpers_from_pinned_d1_module(self) -> None:
        source = fixture.D1_SOURCE.read_text()
        self.assertEqual(fixture.sha256(source.encode()), fixture.D1_SHA256)
        self.assertIn("SUBROUTINE graupel_diffusion_point", fixture._extract(source, "graupel_diffusion_point"))
        self.assertIn("PURE LOGICAL FUNCTION strict_graupel_pair", fixture._extract(source, "strict_graupel_pair"))

    def test_identity_bounds_join_to_qg_and_qib_producer_rows(self) -> None:
        identity = {"step": 15, "rk": 2, "i": 0, "j": 1, "k": 1,
                    "producer_identity": [15, 2, -1, 1, -1, 1, 1, 1]}
        producers = {
            (15, 2, 7, 1, 0, 1, 1): {"identity": identity["producer_identity"]},
            (15, 2, 8, 1, 0, 1, 1): {"identity": identity["producer_identity"]},
        }
        self.assertEqual(fixture._producer_for_identity(producers, identity, 7)[0], (15, 2, 7, 1, 0, 1, 1))
        self.assertEqual(fixture._producer_for_identity(producers, identity, 8)[0], (15, 2, 8, 1, 0, 1, 1))

    def test_combines_7_off_and_12_cpl_cases_even_with_coordinate_overlap(self) -> None:
        off = {"arm": "OFF", "status": "LEGACY_REPLAY_PENDING",
               "source_chain_closure": True, "stage6_bulk_closure": True,
               "all_store_cases_closed": False, "legacy_replay_status": "PENDING",
               "certifier_store_count": 1,
               "store_failure_coordinates": ([{"arm": "OFF", "context": "FULL", "coordinate": [1]} for _ in range(7)] +
                                             [{"arm": "OFF", "context": "CERTIFIER", "coordinate": [2]}])}
        cpl = {"arm": "CPL", "status": "LEGACY_REPLAY_PENDING",
               "source_chain_closure": True, "stage6_bulk_closure": True,
               "all_store_cases_closed": False, "legacy_replay_status": "PENDING",
               "certifier_store_count": 1,
               "store_failure_coordinates": ([{"arm": "CPL", "context": "FULL", "coordinate": [1]} for _ in range(12)] +
                                             [{"arm": "CPL", "context": "CERTIFIER", "coordinate": [2]}])}
        combined = fixture.combine_arm_reports(off, cpl)
        self.assertEqual(combined["full_store_record_count"], 19)
        self.assertEqual(combined["certifier_record_count"], 2)
        self.assertEqual(combined["status"], "LEGACY_REPLAY_PENDING")

    def test_replay_output_rejects_unknown_and_duplicate_rows(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown"):
            fixture._parse_replay_stdout("UNEXPECTED 1\n", {}, [], [], "OFF")
        row = "PRODUCER_REPLAY 1 T 0000000000000000 0000000000000000 1 1 7 1 0 0 1"
        with self.assertRaisesRegex(ValueError, "duplicate producer"):
            fixture._parse_replay_stdout(f"{row}\n{row}\n", {(1,): {}}, [], [], "OFF")

    def test_generated_harness_compiles_and_calls_both_store_cores(self) -> None:
        producer = {"step": 1, "rk": 1, "channel": 7, "im": 1, "i": 0, "j": 0, "k": 1,
                    "stencil": {dy: ["00000000"] * 9 for dy in (-1, 0, 1)},
                    "metrics32_bits": ["3F800000"] * 10,
                    "scale32_bits": ["00000000", "3F800000", "3F800000", "3F800000"],
                    "before32_bits": "00000000", "after32_bits": "00000000",
                    "diffusion64_bits": "0000000000000000"}
        store = {"context": "FULL", "step": 1, "rk": 1, "i": 0, "j": 0, "k": 1,
                 "cell": 1, "failure_stage": 0,
                 "candidate_bits64": [struct.pack(">d", value).hex().upper() for value in
                     (100.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 100.0, 900.0, 1.0, 1.0, 100.0, 1.0)],
                 "r32_bits": [struct.pack(">f", value).hex().upper() for value in
                     (1.0, 1.0, 1.0, 1.0, 100.0, 1.0)]}
        identity = {"step": 1, "rk": 1, "i": 0, "j": 0, "k": 1, "cell": 1,
                    "producer_identity": [1, 1, 7, 1, 0, 0, 1],
                    "r64_bits": ["0000000000000000"] * 12, "r64": [0.0] * 12,
                    "r32_bits": ["00000000"] * 8,
                    "stencil": {dy: ["00000000"] * 12 for dy in (-1, 0, 1)},
                    "metrics32_bits": ["3F800000"] * 10,
                    "face_coeff64_bits": ["0000000000000000"] * 16,
                    "cache_delta64_bits": ["0000000000000000"] * 2}
        data = fixture._data_module({(1, 1, 7, 1, 0, 0, 1): producer}, [store], [identity])
        sources = fixture._core_sources(fixture.POLICY_CORE.read_text())
        sources["d1_helpers.f90"] = fixture._adapter(fixture.D1_SOURCE.read_text())
        sources["captures.f90"] = data
        sources["fixture.f90"] = fixture._harness()
        compiled = fixture.store_replay.run_source_profile("O0", sources, executable="fixture_test")
        self.assertIn("PRODUCER_REPLAY", compiled["stdout"])
        self.assertIn("IDENTITY_REPLAY", compiled["stdout"])
        self.assertIn("STORE_REPLAY", compiled["stdout"])


if __name__ == "__main__":
    unittest.main()
