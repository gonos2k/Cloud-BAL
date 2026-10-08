import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "pr73_first_violation.py"
SOURCE = ROOT / "docs/evidence/pr72_combined_native_first_reject_20261008/frozen_combined_source.F"
spec = importlib.util.spec_from_file_location("pr73_first_violation", TOOL)
validator = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(validator)


class FirstViolationTransformTests(unittest.TestCase):
    def test_transform_adds_scoped_diagnostic_and_preserves_physics_source(self):
        with tempfile.TemporaryDirectory(prefix="pr73_transform_test_") as directory:
            output = Path(directory) / "instrumented.F"
            receipt = Path(directory) / "composition.json"
            result = validator.transform(SOURCE, output, receipt)
            text = output.read_text(encoding="utf-8")
            self.assertEqual(result["input_sha256"], validator.EXPECTED_INPUT_SHA256)
            self.assertIn("KDM62D_INITIAL_PREFLIGHT", text)
            self.assertIn("|q_unit=kg kg-1|n=", text)
            self.assertIn("|n_unit=m-3", text)
            self.assertIn("|b=", text)
            self.assertIn("|b_unit=m3 kg-1|i=", text)
            self.assertIn("|call_lat_index=", text)
            self.assertIn("|j_global_mapping=unclaimed", text)
            self.assertIn("its,ite,kts,kte,lat", text)
            self.assertNotIn("qci(ii,kk,2) =", text)
            self.assertTrue(receipt.is_file())

    def test_transform_refuses_unrecognized_source(self):
        with tempfile.TemporaryDirectory(prefix="pr73_transform_test_") as directory:
            changed = Path(directory) / "changed.F"
            changed.write_text(SOURCE.read_text(encoding="utf-8") + "! changed\n")
            with self.assertRaises(SystemExit):
                validator.transform(changed, Path(directory) / "out.F")


if __name__ == "__main__":
    unittest.main()
