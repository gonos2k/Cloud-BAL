import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr92_mixture_witness_replay as witness


class MixtureWitnessReplayTests(unittest.TestCase):
    def test_pinned_helper_source_and_extraction(self):
        source = witness.SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), witness.SOURCE_SHA256)
        module = witness.adapter(source.decode())
        self.assertIn("FUNCTION strict_graupel_pair", module)
        self.assertIn("SUBROUTINE store_graupel_mixture", module)
        self.assertIn("end module c15_mixture_adapter", module)

    def test_unknown_or_truncated_witness_rows_are_rejected(self):
        cases = (
            "PR92_MIXTURE_UNKNOWN 15 1\n",
            "PR92_MIXTURE_TRIAL 15 1 127 5 22 1 1\n",
            "PR92_MIXTURE_TRIAL 15 1 127 5 22 1 1\nPR92_MIXTURE_END\n",
            "PR92_MIXTURE_TRIAL 15 1 127 5 22 1 1\n"
            "PR92_MIXTURE_TERMS32 " + " ".join(["00000000"] * 14) + "\n",
            "PR92_MIXTURE_TRIAL 15 1 127 5 22 1 1\n"
            "PR92_MIXTURE_WEIGHTS64 " + " ".join(["0000000000000000"] * 7) + "\n"
            "PR92_MIXTURE_WEIGHTS64 " + " ".join(["0000000000000000"] * 7) + "\n",
        )
        for content in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "witness.raw"
                path.write_text(content)
                with self.assertRaises(ValueError):
                    witness.parse_witness(path)

    def test_witness_rows_outside_target_contract_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "witness.raw"
            path.write_text("PR92_MIXTURE_TRIAL 14 1 127 5 22 1 1\n")
            with self.assertRaisesRegex(ValueError, "outside the pinned"):
                witness.parse_witness(path)

    def test_invalid_candidate_can_replay_exact_valid_mixture_store(self):
        candidate_q = "3FF0000000000000"
        candidate_b = "3FD0000000000000"
        delta_q = delta_b = "0000000000000000"
        record = {"coordinate": [15, 1, 127, 5, 22], "cell": 4,
                  "source_first_pair": True,
                  "weights64_bits": ["0" * 16] * 7,
                  "terms32_bits": ["0" * 8] * 14,
                  "values64_bits": [candidate_q, candidate_b, delta_q, delta_b] + ["0" * 16] * 7,
                  "values32_bits": ["3F800000", "3F000000"] + ["0" * 8] * 6}
        stdout = ("MIXTURE_REPLAY 1 T F T 3F800000 3F000000 "
                  f"{delta_q} {delta_b} {candidate_q} {candidate_b} {delta_q} {delta_b}")
        rows = witness.parse_output(stdout, [record], {
            tuple(record["coordinate"]): {"cell": 4, "failure_stage": 2,
                                          "candidate_bits64": [candidate_q, candidate_b]}})
        self.assertFalse(rows[0]["candidate_strict"])
        self.assertTrue(rows[0]["stored_strict"])
        self.assertTrue(rows[0]["helper_replay_exact"])

    def test_cli_summary_uses_stage2_coverage_field(self):
        result = {"status": "UNRESOLVED", "local_trial_count": 1,
                  "d1_full_stage2_coordinate_coverage_complete": False,
                  "all_local_trials_replay_exactly": True,
                  "transaction_commit_status": "NOT_CAPTURED"}
        payload = witness.summary_payload(result, "OFF", Path("replay.json"))
        self.assertIn("d1_stage2_covered", payload)
        self.assertFalse(payload["d1_stage2_covered"])


if __name__ == "__main__":
    unittest.main()
