import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "tools/pr105_paired_scores.py"
SPEC = importlib.util.spec_from_file_location("pr105_scores", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ClosedPairedScoresTests(unittest.TestCase):
    def fixture(self, root):
        supervisor_arms = {"H": "HYDRO", "A": "AMPLITUDE", "N": "STRUCTURED"}
        receipt_hashes = {arm: (str(index + 1) * 64) for index, arm in enumerate(supervisor_arms)}
        history_hashes = {arm: (str(index + 4) * 64) for index, arm in enumerate(supervisor_arms)}
        cohort = root / "cohort.json"
        cohort_rows = []
        for arm in supervisor_arms.values():
            key = next(key for key, value in supervisor_arms.items() if value == arm)
            receipt = root / f"{arm.lower()}_receipt.json"
            receipt.write_text(f'{{"arm":"{arm}"}}')
            receipt_hashes[key] = MODULE.READER.sha256(receipt)
            cohort_rows.append({"arm": arm, "status": "CLOSED", "completed_steps": 180,
                                "final_completed_step": 180, "requested_forecast_complete": True,
                                "closed_receipt": {"path": str(receipt), "sha256": receipt_hashes[key]}})
        cohort.write_text(json.dumps({"all_requested_forecasts_complete": True, "arms": cohort_rows}))
        result = root / "result.json"
        row = {"station_id": "s", "wmo_id": "1", "provider": "test", "time_hhmm": 1400,
               "lat": 35.0, "lon": 127.0, "elev_m": 0.0, "observation_c": 20.0,
               "temperature_expected_accuracy_f": 1.08,
               "model_t2_c": 21.0, "signed_model_minus_observation_c": 1.0}
        closed_arms, reader_arms = {}, {}
        for index, arm in enumerate(supervisor_arms):
            history_path = str(root / f"{arm.lower()}_history.nc")
            closed_arms[arm] = {"arm": supervisor_arms[arm], "receipt_sha256": receipt_hashes[arm],
                                "history_path": history_path, "history_sha256": history_hashes[arm],
                                "history_bytes": 100 + index}
            reader_arms[arm] = {"history_path": history_path, "history_sha256": history_hashes[arm],
                                "valid_time_utc": "2026-08-16T14:00:00Z"}
        recipe_hash = "a" * 64
        pins = {"postclosure_recipe": recipe_hash}
        for arm in supervisor_arms:
            pins[f"{arm}_receipt"] = receipt_hashes[arm]
            pins[f"{arm}_history"] = history_hashes[arm]
        result.write_text(json.dumps({"schema": "pr104_postclosure_observation_summary_v1",
                                     "pins_unchanged": True, "pins_before": pins, "pins_after": pins,
                                     "closed_arms": closed_arms,
                                     "reader_result": {"schema": "pr104_explicit_valid_time_observation_v1",
                                                       "valid_time_utc": "2026-08-16T14:00:00Z",
                                                       "arms": reader_arms,
                                                       "matched_station_records_by_arm": {arm: [row] for arm in "HAN"}}}))
        dispatch = root / "dispatch.json"
        dispatch.write_text(json.dumps({"status": "POSTPROCESS_CLOSED",
            "cohort": {"path": str(cohort), "sha256": MODULE.READER.sha256(cohort)},
            "recipes": {"observation": {"returncode": 0, "recipe_sha256_before": recipe_hash,
                                           "recipe_sha256_after": recipe_hash,
                                           "stdout_sha256": MODULE.READER.sha256(result)}}}))
        return dispatch, result, cohort

    def test_complete_provenance_reduces_all_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            dispatch, result, _ = self.fixture(Path(directory))
            output = MODULE.reduce_closed_result(dispatch, result)
            self.assertEqual(set(output["pairs"]), {"N_minus_A", "A_minus_H", "N_minus_H"})
            self.assertEqual(output["observation_skill"], "NOT_EVALUATED")
            self.assertFalse(output["pairs"]["N_minus_A"]["nonzero_signal"])

    def test_unfinished_dispatch_never_reduces_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            dispatch, result, _ = self.fixture(Path(directory))
            dispatch.write_text('{"status":"RUNNING"}')
            with patch.object(MODULE.READER, "paired_operator_difference") as reducer:
                with self.assertRaisesRegex(ValueError, "completed observation"):
                    MODULE.reduce_closed_result(dispatch, result)
                reducer.assert_not_called()

    def test_changed_result_and_incomplete_cohort_are_rejected(self):
        for failure in ("result", "cohort"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                dispatch, result, cohort = self.fixture(Path(directory))
                if failure == "result":
                    result.write_text(result.read_text() + " ")
                else:
                    cohort.write_text('{"all_requested_forecasts_complete":false}')
                    data = json.loads(dispatch.read_text())
                    data["cohort"]["sha256"] = MODULE.READER.sha256(cohort)
                    dispatch.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    MODULE.reduce_closed_result(dispatch, result)

    def test_tampered_arm_history_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            dispatch, result, _ = self.fixture(Path(directory))
            data = json.loads(result.read_text())
            data["closed_arms"]["A"]["history_sha256"] = "f" * 64
            result.write_text(json.dumps(data))
            record = json.loads(dispatch.read_text())
            record["recipes"]["observation"]["stdout_sha256"] = MODULE.READER.sha256(result)
            dispatch.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "reader history source differs from closed arm pin: A"):
                MODULE.reduce_closed_result(dispatch, result)


if __name__ == "__main__":
    unittest.main()
