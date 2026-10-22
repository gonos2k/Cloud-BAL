import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pr99_pressure_transfer", ROOT / "tools/pr99_pressure_transfer.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
sys.path.insert(0, str(ROOT / "tests"))
from test_cp06a_state_force_flux import make_state


class PressureTransferTests(unittest.TestCase):
    def test_reports_separate_uv_and_omega_corrections(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidate.nc"
            make_state(path)
            with Dataset(path, "r+") as dataset:
                for name, delta in (("u", 0.2), ("v", -0.1), ("omega", 0.03)):
                    background = np.asarray(dataset[f"background_{name}"][:])
                    dataset[f"candidate_{name}"][:] = background + delta

            report = MODULE.measure(path)
            self.assertEqual(report["changed_values"], {"u": 8, "v": 8, "omega": 8})
            self.assertGreater(report["horizontal_uv"]["l1_kg_s"], 0.0)
            self.assertGreater(report["omega"]["l1_kg_s"], 0.0)
            self.assertAlmostEqual(
                report["combined"]["signed_sum_kg_s"],
                report["horizontal_uv"]["signed_sum_kg_s"]
                + report["omega"]["signed_sum_kg_s"],
                places=10,
            )
            self.assertFalse(report["fixed_omega_wps_projection"][
                "closed_mass_wind_balance_assessed"]
            )
            self.assertLess(report["fixed_omega_wps_projection"][
                "max_split_reconstruction_error_kg_s"], 1.0e-8
            )


if __name__ == "__main__":
    unittest.main()
