import numpy as np
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr92_qc_vertical_support import interpolation_levels  # noqa: E402


def test_log_pressure_weights_use_registry_default_coordinate():
    pressures = np.array([100000.0, 95000.0, 90000.0, 85000.0, 80000.0])
    target = np.array([87500.0])

    rows, _ = interpolation_levels(pressures, target, interp_type=2)

    row = rows[0]
    assert row["mode"] == "linear_log_pressure_interpolation"
    coefficients = row["vertical_coefficients"]
    expected_left = (np.log(87500.0) - np.log(85000.0)) / (np.log(90000.0) - np.log(85000.0))
    assert [item["met_em_pressure_index0"] for item in coefficients] == [2, 3]
    assert np.isclose(coefficients[0]["weight"], expected_left)
    assert np.isclose(sum(item["weight"] for item in coefficients), 1.0)


def test_pressure_mode_remains_explicitly_selectable():
    pressures = np.array([100000.0, 95000.0, 90000.0, 85000.0, 80000.0])
    target = np.array([87500.0])

    rows, _ = interpolation_levels(pressures, target, interp_type=1)

    assert rows[0]["mode"] == "linear_pressure_interpolation"
    assert np.isclose(rows[0]["vertical_coefficients"][0]["weight"], 0.5)
