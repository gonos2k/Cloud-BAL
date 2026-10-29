import csv
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/cp02_thermo_response.py"
SPEC = importlib.util.spec_from_file_location("cp02_thermo_response", SCRIPT)
thermo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(thermo)


class ThermoResponseTests(unittest.TestCase):
    def test_actual_capture_and_initial_selection_generate_weighted_profiles(self):
        with tempfile.TemporaryDirectory(prefix="cp02-thermo-test-") as temp:
            output = Path(temp) / "analysis"
            summary = thermo.analyze(output_dir=output)
            self.assertEqual(summary["status"], "PASS_SCOPED_CAPTURE_AND_INITIAL_SELECTION")
            with (output / "profiles.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 2 * 3 * 39 * (3 + 7 + 4 * 9))
            profiles = [row for row in rows if row["point"] == "P05" and row["level_k1"] == "8"]
            lookup = {(row["arm"], row["state"], row["field"]): float(row["weighted_value"])
                      for row in profiles}
            self.assertAlmostEqual(lookup[("HYDRO", "call1_entry", "qr")], 2.718877e-4, delta=1e-9)
            self.assertEqual(lookup[("HYDRO", "call1_return", "qr")], 0.0)
            self.assertAlmostEqual(lookup[("LIQUID", "call1_entry", "qr")], 2.710023e-4, delta=1e-9)
            self.assertAlmostEqual(lookup[("LIQUID", "call1_return", "qr")], 2.615346e-4, delta=1e-9)
            checkpoints = summary["P05_k8_HYDRO_LIQUID_call1_weighted_profiles"]
            for field in ("q", "qc", "th"):
                self.assertNotEqual(checkpoints["HYDRO"]["call1_entry"][field],
                                    checkpoints["LIQUID"]["call1_entry"][field])
            self.assertIn(("HYDRO", "call1_entry", "q"), lookup)
            self.assertIn(("HYDRO", "call1_entry", "qc"), lookup)
            self.assertIn(("HYDRO", "call1_entry", "th"), lookup)
            for field in ("T", "THM", "P", "PB"):
                self.assertIn(("HYDRO", "initial_wrfinput", field), lookup)
            self.assertNotEqual(lookup[("HYDRO", "initial_wrfinput", "T")],
                                lookup[("HYDRO", "initial_wrfinput", "THM")])
            self.assertEqual(summary["intercall_newly_positive_qr"]["HYDRO"]["sample_count"], 624)
            hydro_transition = summary["intercall_newly_positive_qr"]["HYDRO"]["newly_positive_qr_amplitude"]
            self.assertEqual(set(hydro_transition), {"count", "min", "q25", "median", "q75", "max"})
            liquid_call2 = summary["mass_positive_nr_zero_amplitude_by_call"]["LIQUID"]["call2_entry"]
            self.assertGreater(liquid_call2["qr_positive_nr_exact_zero_count"], 0)
            self.assertAlmostEqual(liquid_call2["qr_amplitude"]["max"], 4.49e-4, delta=2e-6)
            liquid_post = summary["mass_positive_nr_zero_amplitude_by_call"]["LIQUID"]["call2_return"]
            self.assertEqual(liquid_post["qr_positive_nr_exact_zero_count"], 63)
            self.assertAlmostEqual(liquid_post["qr_amplitude"]["max"], 4.49e-4, delta=2e-6)
            self.assertTrue(any(row.get("corner_raw_hex") for row in rows
                                if row["state"] == "call2_entry"))

    def test_bad_initial_csv_fails_closed_before_output(self):
        with tempfile.TemporaryDirectory(prefix="cp02-thermo-bad-csv-") as temp:
            temp = Path(temp)
            bad_csv = temp / "selected_initial_fields.csv"
            shutil.copyfile(thermo.DEFAULT_INITIAL, bad_csv)
            raw = bad_csv.read_text(encoding="utf-8")
            bad_csv.write_text(raw.replace("0.018309244886040688", "0.018309244886040689", 1),
                               encoding="utf-8")
            output = temp / "must_not_exist"
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                thermo.analyze(output_dir=output, initial_path=bad_csv)
            self.assertFalse(output.exists())

    def test_dangling_output_symlink_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix="cp02-thermo-output-link-") as temp:
            temp = Path(temp)
            output = temp / "output"
            target = temp / "missing-target"
            output.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "output path already exists"):
                thermo.analyze(output_dir=output)
            self.assertTrue(output.is_symlink())
            self.assertEqual(output.readlink(), target)
            self.assertFalse(target.exists())

    def test_bad_binary_initial_csv_fails_closed_before_output(self):
        with tempfile.TemporaryDirectory(prefix="cp02-thermo-bad-binary-") as temp:
            temp = Path(temp)
            bad_csv = temp / "initial_thermo.csv"
            shutil.copyfile(thermo.DEFAULT_BINARY_INITIAL, bad_csv)
            bad_csv.write_text(bad_csv.read_text(encoding="utf-8").replace(
                "0.018309244886040688", "0.018309244886040689", 1), encoding="utf-8")
            output = temp / "must_not_exist"
            with self.assertRaisesRegex(ValueError, "frozen hash"):
                thermo.analyze(output_dir=output, binary_initial_path=bad_csv)
            self.assertFalse(output.exists())

    def test_binary_initial_weights_are_checked_against_selection(self):
        with tempfile.TemporaryDirectory(prefix="cp02-thermo-bad-weight-") as temp:
            temp = Path(temp)
            bad_csv = temp / "initial_thermo.csv"
            shutil.copyfile(thermo.DEFAULT_BINARY_INITIAL, bad_csv)
            bad_csv.write_text(bad_csv.read_text(encoding="utf-8").replace(
                "0.2477743869405342", "0.5", 1), encoding="utf-8")
            csv_hash = thermo.file_sha256(bad_csv)
            receipt = json.loads(thermo.DEFAULT_BINARY_RECEIPT.read_text(encoding="utf-8"))
            receipt["extraction"]["output_sha256"] = csv_hash
            bad_receipt = temp / "initial_thermo_receipt.json"
            bad_receipt.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
            receipt_hash = thermo.file_sha256(bad_receipt)
            validator = thermo.load_validator()
            selected = thermo.read_selection(thermo.DEFAULT_SELECTION, validator)
            initial = thermo.load_initial(thermo.DEFAULT_INITIAL, thermo.DEFAULT_SELECTION, selected)
            with patch.object(thermo, "BINARY_INITIAL_SHA256", csv_hash), \
                    patch.object(thermo, "BINARY_RECEIPT_SHA256", receipt_hash):
                with self.assertRaisesRegex(ValueError, "weight does not match selection"):
                    thermo.load_binary_initial(bad_csv, bad_receipt, thermo.DEFAULT_SELECTION,
                                               selected, initial)

    def test_binary_initial_coordinates_are_checked_against_selection(self):
        with tempfile.TemporaryDirectory(prefix="cp02-thermo-bad-coordinate-") as temp:
            temp = Path(temp)
            bad_csv = temp / "initial_thermo.csv"
            shutil.copyfile(thermo.DEFAULT_BINARY_INITIAL, bad_csv)
            bad_csv.write_text(bad_csv.read_text(encoding="utf-8").replace(
                "163,73,1,0.018309244886040688", "164,73,1,0.018309244886040688", 1),
                encoding="utf-8")
            csv_hash = thermo.file_sha256(bad_csv)
            receipt = json.loads(thermo.DEFAULT_BINARY_RECEIPT.read_text(encoding="utf-8"))
            receipt["extraction"]["output_sha256"] = csv_hash
            bad_receipt = temp / "initial_thermo_receipt.json"
            bad_receipt.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
            receipt_hash = thermo.file_sha256(bad_receipt)
            validator = thermo.load_validator()
            selected = thermo.read_selection(thermo.DEFAULT_SELECTION, validator)
            initial = thermo.load_initial(thermo.DEFAULT_INITIAL, thermo.DEFAULT_SELECTION, selected)
            with patch.object(thermo, "BINARY_INITIAL_SHA256", csv_hash), \
                    patch.object(thermo, "BINARY_RECEIPT_SHA256", receipt_hash):
                with self.assertRaisesRegex(ValueError, "coordinate is not bound"):
                    thermo.load_binary_initial(bad_csv, bad_receipt, thermo.DEFAULT_SELECTION,
                                               selected, initial)

    def test_newly_positive_requires_prior_nonpositive_and_current_positive(self):
        rows = {
            ("OFF", "P01_00", 1): {
                "call1_return": {"qr": 0.0, "nr": 0.0},
                "call2_entry": {"qr": 4.0e-4, "nr": 0.0},
            },
            ("OFF", "P01_00", 2): {
                "call1_return": {"qr": -1.0e-5, "nr": 2.0},
                "call2_entry": {"qr": 1.0e-4, "nr": 1.0},
            },
            ("OFF", "P01_00", 3): {
                "call1_return": {"qr": 1.0e-5, "nr": 0.0},
                "call2_entry": {"qr": 2.0e-5, "nr": 0.0},
            },
            ("OFF", "P01_00", 4): {
                "call1_return": {"qr": 0.0, "nr": 0.0},
                "call2_entry": {"qr": 0.0, "nr": 0.0},
            },
        }
        result = thermo.transition_summary(rows, expected_samples=4, arms=("OFF",))["OFF"]
        self.assertEqual(result["newly_positive_qr_count"], 2)
        self.assertEqual(result["newly_positive_qr_with_nr_exact_zero_count"], 1)
        self.assertEqual(result["newly_positive_qr_amplitude_where_nr_zero"]["max"], 4.0e-4)


if __name__ == "__main__":
    unittest.main()
